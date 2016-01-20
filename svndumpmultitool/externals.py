# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Parse SVN externals descriptions."""

from __future__ import absolute_import

import logging
import re
import subprocess

from svndumpmultitool import util

LOGGER = logging.getLogger(__name__)


class Error(Exception):
  """Parent class for this module's errors."""


class ParseError(Error):
  """Unable to parse an externals description."""


class UnknownRepo(ParseError):
  """Unable to match an externals URL to a local repository."""


class ExternalsDescription(object):
  """A line-item from an svn:externals property.

  See __init__ for documentation of public attributes.
  """

  def __init__(self, dstpath, srcrepo, srcrev, srcpath, srcpeg):
    """Create a new ExternalsDescription.

    Args:
      dstpath: relative path in the repository where the external is pinned
      srcrepo: absolute filesystem path of the source repository
      srcrev: source operative revision number - positive int, 'HEAD', or None
              (same as 'HEAD')
      srcpath: path within the source repository
      srcpeg: peg revision number - same format as srcrev (srcpeg is not
              currently used for anything since local SVN commands and the SVN
              API have no concept of a peg revision)
    """
    if srcrev is None:
      # operative revision defaults to peg revision
      srcrev = srcpeg
    self.dstpath = dstpath
    self.srcrepo = srcrepo
    self.srcpath = srcpath
    self.srcrev = _SanitizeRev(srcrev)
    self.srcpeg = _SanitizeRev(srcpeg)

  def SourceExists(self):
    """Tests whether the srcpath exists at srcrev in srcrepo."""
    cmd = [
        'svn',
        'ls',  # svn info can be really slow for old revs
        util.FileURL(self.srcrepo, self.srcpath, self.srcrev),
        ]

    svn_ls = util.Popen(*cmd, stderr=subprocess.PIPE)

    # We don't care about output, only exit code
    svn_ls.stdout.read()
    svn_ls.stdout.close()
    svn_ls.stderr.read()
    svn_ls.stderr.close()

    if util.CheckExitCode(svn_ls, allow_failure=True):
      LOGGER.warning('%s points to a non-existent location', self)
      return False
    else:
      return True

  def __repr__(self):
    return 'ExternalsDescription(%r, %r, %r, %r, %r)' % (
        self.dstpath,
        self.srcrepo,
        self.srcrev,
        self.srcpath,
        self.srcpeg,
        )

  def __eq__(self, other):
    return (isinstance(other, type(self))
            and self.dstpath == other.dstpath
            and self.srcrepo == other.srcrepo
            and self.srcrev == other.srcrev
            and self.srcpath == other.srcpath
            and self.srcpeg == other.srcpeg)


def _SanitizeRev(rev):
  """Coerces a value into a revision number or None.

  Args:
    rev: a revision number (str, int, or None)

  Returns:
    rev converted to an int or None

  Raises:
    ValueError: if the revision cannot be parsed or is negative

  'HEAD' is converted to None.
  """
  if isinstance(rev, basestring):
    if rev.upper() == 'HEAD':
      rev = None
    else:
      rev = int(rev)
  if rev is not None and rev < 0:
    raise ValueError('Revision cannot be negative')
  return rev


def Diff(old, new, include_peg=False):
  """Determines which externals have been added, changed, and removed.

  Args:
    old: a dict of {str: ExternalsDescription} where each key is equal to the
         dstpath attribute of its value
    new: like old
    include_peg: whether the peg revision should be considered when comparing

  Returns:
    a 3-tuple:
    added, a list of ExternalsDescriptions that are new
    changed, a list of pairs of ExternalsDescriptions (old, new) that have
             been modified
    deleted, a list of ExternalsDescriptions that were deleted

  Externals that are the same in both sets are not included in this function's
  output.

  For these purposes, any externals that moved from one source repo to another
  are considered to have been deleted and then added.

  Peg revisions are ignored by default, since the command-line tools used for
  reconstructing data do not support pegs.
  """
  added = []
  changed = []
  deleted = []
  for dstpath, new_descr in new.iteritems():
    if dstpath in old:
      old_descr = old[dstpath]
      if old_descr.srcrepo != new_descr.srcrepo:
        # Can't do a diff between two different repos
        deleted.append(old_descr)
        added.append(new_descr)
      elif (old_descr.srcpath != new_descr.srcpath
            or old_descr.srcrev != new_descr.srcrev
            # We can't actually use pegs, so ignore them by default
            or (include_peg and old_descr.srcpeg != new_descr.srcpeg)):
        changed.append((old_descr, new_descr))
      # If neither of the above conditions are met, the old and new
      # descriptions are identical and need not be processed further.
    else:
      added.append(new_descr)
  for dstpath, old_descr in old.iteritems():
    if dstpath not in new:
      deleted.append(old_descr)
  return added, changed, deleted


def _FindExternalPath(url, externals_map):
  """Converts a URL to a repo root path and a path within the repo.

  Args:
    url: a URL to a point inside a (possible remote) repository
    externals_map: dict mapping URL prefixes to local repo root paths
                   (read from a file passed to --externals-map)

  Returns:
    repo: the root directory of the repository
    path: the path within the repository
  Raises:
    ParseError: if no repo in the externals map matches the URL
  """
  path = None
  for prefix, repo in externals_map.iteritems():
    if url == prefix:
      path = ''
      return repo, path
    elif url.startswith(prefix + '/'):
      path = url[len(prefix) + 1:]
      return repo, path
  raise UnknownRepo('Failed to map %s to a local repo' % url)


def _ParseNewStyleExternal(dir_token, url_token, rev_token,
                           main_repo, parent_dir, externals_map):
  """Create an ExternalsDescription using new-style semantics.

  Args:
    dir_token: the token from the description that describes where the external
               will be pinned
    url_token: the token from the description that describes where to find the
               external - may use one of the new-style relative URL syntaxes
    rev_token: the token from the description that gives the operative revision
               or None
    main_repo: the absolute local path of the repo that contains this externals
               description (must not have a trailing slash).
    parent_dir: the directory of the repo on which this externals description is
                defined
    externals_map: an externals map (see _FindExternalPath)

  Returns:
    an ExternalsDescription

  Raises:
    ParseError: if parsing failed

  SVN 1.5+ allows several varieties of relative URLs.
  Excerpt from http://svnbook.red-bean.com/en/1.7/svn.advanced.externals.html:

  ../
    Relative to the URL of the directory on which the svn:externals property is
    set

  ^/
    Relative to the root of the repository in which the svn:externals property
    is versioned

  //
    Relative to the scheme of the URL of the directory on which the
    svn:externals property is set

  /
    Relative to the root URL of the server on which the svn:externals property
    is versioned

  ^/../REPO-NAME
    Relative to a sibling repository beneath the same SVNParentPath location as
    the repository in which the svn:externals is defined.
  """
  if '@' in url_token:
    url, peg = url_token.split('@', 1)
  else:
    url = url_token
    peg = None
  repo = None
  path = None
  if url.startswith('/'):
    raise ParseError('Scheme-relative and server-relative externals URLs are'
                     ' not implemented')
  elif url.startswith('../'):
    # relative to the directory on which the property is set
    path = parent_dir + '/' + url[3:]
    repo = main_repo
  elif url.startswith('^/'):
    # relative to the root of the repository
    path = url[2:]
    repo = main_repo
    # If it stays in the same repo, it's easy. Otherwise, we need to
    # canonicalize the path and use the externals_map to figure out where
    # the root of the referenced repo is
    if path.startswith('../'):
      while path.startswith('../'):
        path = path[3:]
        if repo == '/':
          # Already reached file system root - can't go any higher
          raise ParseError('Tried to go above filesystem root while'
                           ' canonicalizing externals url')
        elif repo.rfind('/') == 0:
          # Special case so '/foo' -> '/' instead of '/foo' -> ''
          repo = '/'
        else:
          # Normal case '/foo/bar' -> '/foo'
          repo = repo[0:repo.rfind('/')]
      # Use the externals map to accurately split the repo location from
      # the path.
      url = util.FileURL(repo, path, None)
      repo = None
  if repo is None:
    repo, path = _FindExternalPath(url, externals_map)
  try:
    return ExternalsDescription(dir_token, repo, rev_token, path, peg)
  except ValueError as e:
    # If the rev or peg was unparseable, skip it
    raise ParseError(str(e))


def _ParseOldStyleExternal(dir_token, url_token, rev_token, externals_map):
  repo, path = _FindExternalPath(url_token, externals_map)
  try:
    # Old style externals descriptions treat the argument to -r as both the peg
    # and operative revision.
    return ExternalsDescription(dir_token, repo, rev_token, path, rev_token)
  except ValueError as e:
    # If the rev or peg was unparseable, skip it
    raise ParseError(str(e))


def _MakeLineParser(dir_idx, url_idx, rev_idx=None, rev_as_flag=False,
                    new_style_format=False):
  """Generate a parser for an externals description of a particular format.

  Args:
    dir_idx: the index of the token that contains the path at which the external
             will be pinned
    url_idx: the index of the token that contains the URL to which the external
             refers
    rev_idx: the index of the token that contains the revision number if the
             format includes one
    rev_as_flag: True if the revision number token is of the form '-r123', False
                 if it is just '123'. Ignored if rev_idx is not provided
    new_style_format: True if the format is one of the three new formats that
                      allow relative URLs, False otherwise

  Returns:
    a function that accepts a list of tokens and returns an ExternalsDescription

  Raises:
    ParseError: if parsing fails

  Because the six different externals description formats define the target
  director, URL, and (optional) revision flag at different positions in the
  description, this helper is used to make separate parsers for each format. It
  can then delegate to _ParseNewStyleExternal and _ParseOldStyleExternal to
  handle the more significant semantic differences between the different
  formats.
  """
  def _Parse(tokens, main_repo, parent_dir, externals_map):
    dir_token = tokens[dir_idx]
    url_token = tokens[url_idx]
    if rev_idx is None:
      rev_token = None
    else:
      rev_token = tokens[rev_idx]
    if rev_as_flag:  # Strip off '-r'
      rev_token = rev_token[2:]
    if new_style_format:
      return _ParseNewStyleExternal(dir_token, url_token, rev_token,
                                    main_repo, parent_dir, externals_map)
    else:
      return _ParseOldStyleExternal(dir_token, url_token, rev_token,
                                    externals_map)
  return _Parse


# Create parsers for each of the six formats accepted by SVN, keyed to the
# pseudo-syntax of each format.
FORMAT_PARSERS = {
    # Format 1
    'DIR URL': _MakeLineParser(dir_idx=0, url_idx=1),
    # Format 2
    'DIR -r N URL': _MakeLineParser(dir_idx=0, url_idx=3, rev_idx=2),
    # Format 3
    'DIR -rN URL': _MakeLineParser(dir_idx=0, url_idx=2, rev_idx=1,
                                   rev_as_flag=True),
    # For the purposes of formats 4-6, 'DIR' is treated as if it might actually
    # be a URL because those formats allow relative URLs, which can be
    # indistinguishable from local paths (i.e. they may not contain '://').
    # Format 4
    'URL DIR': _MakeLineParser(dir_idx=1, url_idx=0, new_style_format=True),
    # Default to format 4 if neither token contains '://'
    'DIR DIR': _MakeLineParser(dir_idx=1, url_idx=0, new_style_format=True),
    # Format 5
    '-r N URL DIR': _MakeLineParser(dir_idx=3, url_idx=2, rev_idx=1,
                                    new_style_format=True),
    '-r N DIR DIR': _MakeLineParser(dir_idx=3, url_idx=2, rev_idx=1,
                                    new_style_format=True),
    # Format 6
    '-rN URL DIR': _MakeLineParser(dir_idx=2, url_idx=1, rev_idx=0,
                                   rev_as_flag=True, new_style_format=True),
    '-rN DIR DIR': _MakeLineParser(dir_idx=2, url_idx=1, rev_idx=0,
                                   rev_as_flag=True, new_style_format=True),
}


def _TokenType(token):
  """Classify one word from an external description.

  Args:
    token: a single word (string) of an externals description

  Returns:
    '-r', 'N', '-rN', 'URL', or 'DIR'

  Helper for _GetLineParser.
  """
  if token == '-r':
    return '-r'
  elif token.isdigit() or token.upper() == 'HEAD':
    return 'N'
  elif re.match(r'\A-r(\d+|HEAD)\Z', token, flags=re.IGNORECASE):
    return '-rN'
  elif '://' in token:
    return 'URL'
  else:
    return 'DIR'


def _GetLineParser(tokens):
  """Given a tokenized external description, find the correct parser.

  Args:
    tokens: a list of tokens (strings) created by splitting an externals
            description on whitespace

  Returns:
    a function capable of parsing tokens into an externals description

  Raises:
    ParseError: if no parser matches the format that tokens takes

  First, it uses _TokenType to help construct a format string similar to those
  used in the SVN docs to describe the different formats (see ParseLine). Then
  it looks up that format in FORMAT_PARSERS to get the right parser for that
  format.
  """
  format_string = ' '.join(_TokenType(token) for token in tokens)
  try:
    return FORMAT_PARSERS[format_string]
  except KeyError:
    raise ParseError('Unrecognized format "%s"' % format_string)


def ParseLine(main_repo, main_repo_rev, parent_dir, line, externals_map):
  """Parses one line of an svn:externals property.

  Args:
    main_repo: the absolute path to the repository where svn:externals is set
               (must not have a trailing /)
    main_repo_rev: the revision in main_repo that description exists at
    parent_dir: the directory to which the svn:externals property applies
    line: the line from the svn:externals property
    externals_map: a dict mapping repository URLs to local paths

  Returns:
    an ExternalsDescription

  Raises:
    ParseError: if parsing fails

  Excerpt from http://svn.apache.org/repos/asf/subversion/tags/1.7.8
               /subversion/libsvn_wc/externals.c

  There are six different formats of externals:

  1) DIR URL
  2) DIR -r N URL
  3) DIR -rN  URL
  4) URL DIR
  5) -r N URL DIR
  6) -rN URL DIR

  The last three allow peg revisions in the URL.

  With relative URLs and no '-rN' or '-r N', there is no way to
  distinguish between 'DIR URL' and 'URL DIR' when URL is a
  relative URL like /svn/repos/trunk, so this case is taken as
  case 4).

  Note: old syntax (DIR before URL) treats N as the peg and
  operative revisions, no @peg allowed. New syntax treats N as
  the operative revision and @peg defaults to HEAD if not given.
  """
  tokens = line.split()
  # Construct a string describing the types of tokens in the description
  # (similar to the way the different formats are described above).
  parser = _GetLineParser(tokens)
  ed = parser(tokens, main_repo, parent_dir, externals_map)
  # If we're dealing with the main repo, we know what HEAD resolves to. We
  # have to subtract one revision, though, since a revision can't copy from
  # itself.
  if ed.srcrepo == main_repo:
    if ed.srcrev is None:
      ed.srcrev = main_repo_rev - 1
    if ed.srcpeg is None:
      ed.srcpeg = main_repo_rev - 1
  return ed


def Parse(main_repo, main_repo_rev, parent_dir, description,
          externals_map):
  """Parses svn:externals property into ExternalsDescriptions.

  Args:
    main_repo: the absolute path to the repository where svn:externals is set
               (must not have a trailing /)
    main_repo_rev: the revision in main_repo that description exists at
    parent_dir: the directory to which the svn:externals property applies
    description: the svn:externals property value
    externals_map: a dict mapping repository URLs to local paths

  Returns:
    a dict mapping path to ExternalsDescription pegged at that path
  """
  if externals_map is None:
    externals_map = {}
  descriptions = {}
  # TODO: also return a modified version of the svn:externals
  # property that excludes lines being returned as ExternalsDescriptions.
  for line in description.split('\n'):
    line = line.strip()
    if not line or line.startswith('#'):
      continue
    try:
      ed = ParseLine(main_repo, main_repo_rev, parent_dir, line, externals_map)
    except ParseError as e:
      LOGGER.warning('%s: %s', e, line)
      continue
    if ed.SourceExists():
      descriptions[ed.dstpath] = ed
  return descriptions


def FromRev(repo, rev, path, externals_map):
  """Get parsed svn:externals property for a given repo, rev, path.

  Args:
    repo: the absolute path to the target repository (must not have a trailing
          /)
    rev: the revision in repo that description exists at
    path: the directory on which the svn:externals property is set
    externals_map: a dict mapping repository URLs to local paths

  Returns:
    a dict mapping path to ExternalsDescription pegged at that path
  """
  svnlook_pg = util.Popen('svnlook',
                          'propget',
                          '-r%s' % rev,
                          repo,
                          'svn:externals',
                          path)
  with svnlook_pg.stdout as propstream:
    value = propstream.read()
  # If the property doesn't exist and causes an error, that's ok
  util.CheckExitCode(svnlook_pg, allow_failure=True)
  return Parse(repo, rev, path, value, externals_map)
