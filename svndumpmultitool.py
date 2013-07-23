#!/usr/bin/python2.7

# Copyright 2013 Google Inc. All Rights Reserved.
#
# Based on svndumpfilter2, which is copyright 2004-2009 Simon Tatham, with
# portions copyright Eric Kidd. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""svndumpmultitool.
====================

Tool for filtering, fixing, breaking, and munging SVN dump files.

This script takes an SVN dump file on stdin, applies various filtering
operations to the history represented by the dump file, and prints the resulting
dump file to stdout. A number of different filtering operations are available,
each enabled by command-line flag. Multiple operations can be used at the same
time. If run without any operations enabled, the script will validate the dump
file's structure and output the same dump file to stdout.

Dependencies
------------
- Python v2.7.x
- Subversion v1.6 or higher
- Subversion API SWIG bindings for Python (NOT the pysvn library)
- mock (to run the tests)

Operations
----------
Path filtering (``--include``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Each argument to ``--include`` is a regular expression. Only paths that
match one or more ``--include`` regexps will be included in the output. A path
whose ancestor directory matches a regexp will also be included. A path that
could be the ancestor directory for a path that matches the regexp will be
included as a directory without properties, even if originally it was a file
or it had properties.

The regular expressions accepted by ``--include`` are based on standard Python
regular expressions, but have one major difference: they are broken into
/-separated pieces and applied to one /-separated path segment at a time.
See [1]_ for detailed examples of how this works.

It is usually necessary to provide ``--repo`` when using ``--include``. See [2]_
for details.

See Limitations_ and `--drop-empty-revs`_ below.

Examples::

  --include=foo
  Includes: foo, foo/bar
  Excludes: trunk/foo

  --include=branches/v.*/foo
  Includes: branches/v1/foo, branches/v2/foo/bar
  Excludes: branches/foo, branches/v1/x/foo, branches/bar
  Includes as directory w/out properties: branches

Externals (``--externals-map``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If the ``--externals-map`` argument is provided, the filter will attempt to
alter the history such that whenever SVN externals [3]_ are included using the
svn:externals property, the contents referenced therein are fetched from
their source repository and inserted in the output stream as if they had
been physically included in the main repository from the beginning.

In order to internalize SVN externals, a local copy of each referenced
repository is required, as well as a mapping from the URLs used to reference
it to the local path at which it resides. A file providing this mapping must
be passed as the value of ``--externals-map``. Only externals using URLs
included in the map will be internalized.

See Limitations_ below.

Example::

  --externals-map=/path/to/my/externals.map

Revision cancellation (``--truncate-rev``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The value for ``--truncate-rev`` should be a revision number. All changes to the
repository that occurred in that revision will be dropped (commit messages
are retained). This is extremely dangerous because future revisions will
still expect the revision to have taken effect. There are a few cases when
it is safe to use ``--truncate-rev``:

1. If used on a pair of revisions that cancel each other out (e.g.
   ``--truncate-rev=108 --truncate-rev=109``, where r108 deletes trunk, r109
   copies trunk from r107).
2. If used on a revision that modifies files/directories, but does not add
   or remove them.

--truncate-rev may be given more than once to truncate multiple revisions.

See also `--drop-empty-revs`_.

Property deletion (``--delete-property``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The SVN property given as the value for ``--delete-property`` will be stripped
from all paths. ``--delete-property`` can be specified more than once to delete
multiple properties.

Examples::

  --delete-property=svn:keywords (to turn off keyword expansion)
  --delete-property=svn:special (to convert symlinks to regular files
    containing 'link <link-target>')

Handling of empty revisions (``--drop-empty-revs``, ``--renumber-revs``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
There are two cases that can result in revisions that perform no actions on
the repository:

1. All paths originally affected by the revision are excluded by the path
   filters.
2. ``--truncate-rev`` was used to explicitly cancel all actions from the
   revision.

By default, these empty revisions are included in the output dump stream. If
``--drop-empty-revs`` is used, empty revisions are instead dropped from the
output. If ``--renumber-revs`` is used in addition to ``--drop-empty-revs``, the
following revisions will be renumbered to eliminate the gap left by the
deleted revision.

See Limitations_ below.

Limitations
-----------
Dump file format:
  'delta' dumps are not fully supported.

Externals:
  - If an externals definition imports the external into a subdirectory, that
    subdirectory will not be automatically created.
  - Currently, the svn:externals property is not modified or deleted when
    externals are internalized.

Revision renumbering:
  The revision mapping used by ``--renumber-revs`` to ensure that copy
  operations point to the correct source is not propagated across multiple
  invocations of the script. This makes it unsuitable for use on incremental
  dumps.

Testing:
  Unit testing is approximately 80% complete. End-to-end testing has not been
  started yet.

Use as a library
----------------
svndumpmultitool can be used as a library for manipulating SVN dump files. The
main entry point for this is the Lump class, which handles parsing and
serializing data in the SVN dump file format. For a simple example, see the
included svndumpgrab script.

--------------------------------------------------------------------------------

.. [1] Examples of /-separated regexp matching:

   The regexp ``branches/v.*/web`` is used for all the examples.

   - The path ``branches/v1/web`` would be checked in three steps:

     1. ``branches`` matches ``branches``
     2. ``v1`` matches ``v.*``
     3. ``web`` matches ``web``
     4. It's a match!

   - The path ``branches/v1/web/index.html`` would be checked in the same three
     steps. After step 3, all parts of the regexp have been satisfied so it's
     considered a match.

   - The path ``branches/v1/test/web`` would be checked in three steps:

     1. ``branches`` matches ``branches``
     2. ``v1`` matches ``v.*``
     3. ``test`` *does not match* ``web``
     4. No match.

     Note that ``v.*`` is not allowed to match ``v1/test`` because it is matched
     against only one path segment.

   - The path ``test/branches/v1/web`` would be checked in one step:

     1. ``test`` *does not match* ``branches``
     2. No match.

     Note that, unlike a standard regular expression, matching only occurs at
     the beginning of the path.

   - The path ``branches/v1`` would be checked in two steps:

     1. ``branches`` matches ``branches``
     2. ``v1`` matches ``v.*``
     3. Partial match. Include as directory.

.. [2] The Subversion (SVN) revision control system offers very few options for
   modifying the history once it has been committed. The one official tool for
   making retroactive modifications is the svndumpfilter tool, which operates
   on SVN dump files, which encode the history of a repository into a stream
   format. Unfortunately, besides only being able to do rudimentary path-based
   filtering, svndumpfilter is unable to correctly handle copy operations.

   Rather than recording copy operations in a way that includes all of the data
   being copied, SVN saves space by only recording the source and destination
   of the copy operation. However, svndumpfilter only examines the destination
   of copy operations, not the source. This means that if the copy destination
   is included in the path filter, but the copy source is not, the copy
   operation will still be output unchanged. When the operation is then loaded,
   SVN will be unable to find the files to copy because they were excluded from
   the filter, so loading the file will fail.

   To fix this problem, svndumpmultitool checks sources of copy operations
   against the path filter and, when the copy source is excluded, it fetches
   the contents of the copy source from the repository (``--repo``) and
   generates add operations from those contents to simulate the copy operation.

.. [3] http://svnbook.red-bean.com/en/1.7/svn.advanced.externals.html

.. _`--drop-empty-revs`:
  `Handling of empty revisions (--drop-empty-revs, --renumber-revs)`_
"""

import argparse
import collections
import logging
import md5
import os
import re
import subprocess
import sys
import urllib

from svn import core as svn_core
from svn import fs as svn_fs
from svn import repos as svn_repos

LOGGER = logging.getLogger('svndumpmultitool' if __name__ == '__main__'
                           else __name__)


def Popen(*cmd, **kwargs):
  """Log command, execute it, and pipe in stdout with buffering."""
  LOGGER.debug('Executing %s', cmd)
  sub = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10240, **kwargs)
  sub.cmd = cmd
  return sub


def CheckExitCode(sub, allow_failure=False):
  """Log command completion and exit code and return the exit code.

  Args:
    sub: a subprocess created with Popen
    allow_failure: if True, return non-zero exit codes instead of raising

  Returns:
    the subprocess's exit code

  Raises:
    subprocess.CalledProcessError: if exit code is non-zero
  """
  # TODO(emosenkis): if this starts getting complicated, use a library instead
  code = sub.wait()
  if code == 0:
    LOGGER.debug('Finished %s', sub.cmd)
  elif allow_failure:
    LOGGER.debug('%s returned non-zero exit status %s', sub.cmd, code)
  else:
    raise subprocess.CalledProcessError(returncode=code, cmd=sub.cmd)
  return code


class ExternalsDescription(object):
  """A line-item from an svn:externals property."""

  def __init__(self, dstpath, srcrepo, srcrev, srcpath, srcpeg):
    if srcrev is None:
      # operative revision defaults to peg revision
      srcrev = srcpeg
    self.dstpath = dstpath
    self.srcrepo = srcrepo
    self.srcpath = srcpath
    self.srcrev = self._SanitizeRev(srcrev)
    self.srcpeg = self._SanitizeRev(srcpeg)

  @staticmethod
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

  def SourceExists(self):
    """Tests whether the srcpath exists at srcrev in srcrepo."""
    rev = '' if self.srcrev is None else '@%s' % self.srcrev

    cmd = [
        'svn',
        'ls',  # svn info can be really slow for old revs
        'file://%s/%s%s' % (self.srcrepo, self.srcpath, rev),
        ]

    svn_ls = Popen(*cmd, stderr=subprocess.PIPE)

    # We don't care about output, only exit code
    svn_ls.stdout.read()
    svn_ls.stdout.close()
    svn_ls.stderr.read()
    svn_ls.stderr.close()

    if CheckExitCode(svn_ls, allow_failure=True):
      LOGGER.warning('%s points to a non-existent location', self)
      return False
    else:
      return True

  @staticmethod
  def Diff(old, new, include_peg=False):
    """Determines which externals have been added, changed, and removed.

    Args:
      old: a dict of dstpath: ExternalsDescription
      new: a dict of dstpath: ExternalsDescription
      include_peg: whether the peg revision should be considered when comparing

    Returns:
      a 3-tuple:
      added, a list of ExternalsDescriptions that are new
      changed, a list of pairs of ExternalsDescriptions (old, new) that have
               been modified
      deleted, a list of paths that externals were pinned to previously but not
               anymore

    Externals that are the same in both sets are not included in this function's
    output.

    For these purposes, any externals that moved from one source repo to another
    are considered to have been deleted and the added.

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
          deleted.append(dstpath)
          added.append(new_descr)
        elif (old_descr.srcpath != new_descr.srcpath
              or old_descr.srcrev != new_descr.srcrev
              # We can't actually use pegs, so ignore them by default
              or (include_peg and old_descr.srcpeg != new_descr.srcpeg)):
          changed.append((old_descr, new_descr))
      else:
        added.append(new_descr)
    for dstpath in old:
      if dstpath not in new:
        deleted.append(dstpath)
    return added, changed, deleted

  def __repr__(self):
    return 'ExternalsDescription(%s, %s, %s, %s, %s)' % (
        repr(self.dstpath),
        repr(self.srcrepo),
        repr(self.srcrev),
        repr(self.srcpath),
        repr(self.srcpeg),
        )

  def __eq__(self, other):
    return (
        isinstance(other, ExternalsDescription)
        and self.__dict__ == other.__dict__
        )

  @classmethod
  def Parse(cls, main_repo, main_repo_rev, parent_dir, description,
            externals_map):
    """Parses svn:externals property into ExternalsDescriptions.

    Args:
      main_repo: the path to the repository where svn:externals is set
      main_repo_rev: the revision in main_repo that description exists at
      parent_dir: the directory to which the svn:externals property applies
      description: the svn:externals property value
      externals_map: a dict mapping repository URLs to local paths

    Returns:
      a dict mapping path to ExternalsDescription pegged at that path
    """
    if externals_map is None:
      externals_map = {}
    descriptions = collections.OrderedDict()
    # TODO(emosenkis): also return a modified version of the svn:externals
    # property that excludes lines being returned as ExternalsDescriptions.
    for line in description.split('\n'):
      line = line.strip()
      if not line or line.startswith('#'):
        continue
      ed = cls.ParseLine(main_repo, main_repo_rev, parent_dir, line,
                         externals_map)
      if ed and ed.SourceExists():
        descriptions[ed.dstpath] = ed
    return descriptions

  @classmethod
  def ParseLine(cls, main_repo, main_repo_rev, parent_dir, line, externals_map):
    """Parses one line of an svn:externals property.

    Args:
      main_repo: the path to the repository where svn:externals is set
      main_repo_rev: the revision in main_repo that description exists at
      parent_dir: the directory to which the svn:externals property applies
      line: the line from the svn:externals property
      externals_map: a dict mapping repository URLs to local paths

    Returns:
      an ExternalsDescription or None if the line cannot be parsed

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
    the operative revision, @peg defaults to HEAD if not given.
    """
    # TODO(emosenkis): Refactor this into several smaller functions.
    parts = line.split()
    if len(parts) < 2 or len(parts) > 4:
      LOGGER.warning('Unparseable svn:external: %s', line)
      return
    if len(parts) == 2:  # Format 1 or 4 (no -r)
      rev = None
      if '://' in parts[1]:  # Format 1
        dstpath, url = parts
        peg = None
        new_format = False
      else:  # Format 4 (default to this as mentioned above)
        url, dstpath = parts
        new_format = True
    else:  # Format 2, 3, 5, or 6
      if parts[0].startswith('-r'):
        if len(parts) == 4:  # Format 5
          rev, url, dstpath = parts[1:]
          new_format = True
        else:  # Format 6
          rev = parts[0][2:]
          url, dstpath = parts[1:]
          new_format = True
      elif len(parts) == 4:  # Format 2
        dstpath = parts[0]
        rev = parts[2]
        url = parts[3]
        peg = rev
        new_format = False
      else:  # Format 3
        dstpath = parts[0]
        rev = parts[1][2:]
        url = parts[2]
        peg = rev
        new_format = False
    repo = None
    # Handle new format relative URLs
    if new_format:
      if '@' in url:
        url, peg = url.split('@', 1)
      else:
        peg = None
      if url.startswith('/'):
        LOGGER.warning('Don\'t know how to handle scheme-relative or '
                       'server-relative externals URLs: %s', line)
        return
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
              LOGGER.warning('Tried to go above filesystem root while '
                             'canonicalizing externals url in %s', line)
              return
            elif repo.rfind('/') == 0:
              # Special case so '/foo' -> '/' instead of '/foo' -> ''
              repo = '/'
            else:
              # Normal case '/foo/bar' -> '/foo'
              repo = repo[0:repo.rfind('/')]
          url = 'file://%s/%s' % (repo, path)
          repo = None  # trigger using the externals map
    # If repo hasn't been determined, look it up in the externals map
    if repo is None:
      repo, path = cls.FindExternalPath(url, externals_map)
      if repo is None:
        LOGGER.warning('Failed to map %s to a local repo in %s', url, line)
        return

    # Finally, create an ExternalsDescription and store it for return
    try:
      ed = cls(dstpath, repo, rev, path, peg)
    except ValueError as e:
      # If the rev or peg was unparseable, skip it
      LOGGER.warning('Failed to parse %s: %s', line, e)
      return

    # If we're dealing with the main repo, we know what HEAD resolves to. We
    # have to subtract one revision, though, since you can't copy from the
    # current revision that's in the midst of being checked in.
    if ed.srcrepo == main_repo:
      if ed.srcrev is None:
        ed.srcrev = main_repo_rev - 1
      if ed.srcpeg is None:
        ed.srcpeg = main_repo_rev - 1
    return ed

  @classmethod
  def FindExternalPath(cls, url, externals_map):
    """Converts a URL to a repo root path and a path within the repo.

    Args:
      url: a URL to a point inside a (possible remote) repository
      externals_map: dict mapping URL prefixes to local repo root paths
                     (read from a file passed to --externals-map)

    Returns:
      repo: the root directory of the repository
      path: the path within the repository
      None for both if no repo in the externals map matches the URL
    """
    path = None
    for prefix, repo in externals_map.iteritems():
      if url == prefix:
        path = ''
        break
      elif url.startswith(prefix + '/'):
        path = url[len(prefix) + 1:]
        break
    if path is None:
      # Don't return the last repo we iterated over if nothing matched
      repo = None
    return repo, path

  @classmethod
  def FromRev(cls, repo, rev, path, externals_map):
    """Get parsed svn:externals property for a given repo, rev, path."""
    svnlook_pg = Popen('svnlook',
                       'propget',
                       '-r%s' % rev,
                       repo,
                       'svn:externals',
                       path)
    with svnlook_pg.stdout as propstream:
      value = propstream.read()
    # If the property doesn't exist and causes an error, that's ok
    CheckExitCode(svnlook_pg, allow_failure=True)
    return cls.Parse(repo, rev, path, value, externals_map)


class InterestingPaths(object):
  """Decides whether a pathname is included by a set of regexps.

  Ok, I lied. This class actually accepts a list of regexp patterns, but then
  splits them on /'s in order to combine the power of regular expressions with
  the structure of file systems. Each regular expression is matched against one
  path component. Each regular expression is also required to match the entire
  component.

  Unfortunately, filesystems introduce an extra bit of complexity to
  include/exclude rules: included paths must implicitly include their parent
  directories without automatically including their siblings. Therefore, ternary
  logic is used instead of simple True/False. Values are NO (excluded), YES
  (included) and PARENT (not explicitly included, but it might contain children
  that are included)

  Examples:
    pattern: foo/bar
      foo/bar/baz: YES
      foo/baz: NO
      foo: PARENT
    pattern: fo+/bop
      fooooo: PARENT
      food: NO
      foooooooooo/boppity: NO
      fooooo/bop: YES
      foo/bop/de/bop: YES
  """
  # TODO(emosenkis): Consider using the enum package for this (part of standard
  # library as of Python 3.4).
  # Not included
  NO = 0
  # Could potentially be the parent directory of an included path
  PARENT = 1
  # Directly included
  YES = 2

  # TODO(emosenkis) add convenience functions IsIncluded, IsExcluded,
  # IsParentOfIncluded
  def __init__(self, includes):
    self.includes = []
    # Split include paths on directory separators and compile as regexps
    for include in includes:
      if include.endswith('/'):
        include = include[:-1]
      if include.startswith('/'):
        include = include[1:]
      self.includes.append([re.compile(r'\A' + regex + r'\Z')
                            for regex in include.split('/')])

  def Interesting(self, path):
    """Check if a path is included, excluded, or a potential parent of included.

    Args:
      path: a path

    Returns:
      YES, NO, or PARENT, as described above

    The path is normalized and split on /'s. Then each included path regexp is
    tried in succession. Path components are matched against the corresponding
    regexp components. The path is only considered to match a path regexp if all
    of its components match their corresponding regexp components.
    - If all components match and the path was long enough to use all components
      of the path regexp (or more), YES is returned.
    - If all components match, but the path ran out of components with path
      regexp components left over, the path is tentatively a PARENT unless one
      of the remaining path regexps causes it to be marked as a YES.
    - If no path regexp matches the path, NO is returned.
    """
    # No includes means everything is included
    if not self.includes:
      return self.YES
    path = os.path.normpath(path)
    # Normpath converts the empty string to .
    if path == '.':
      path = ''
    parts = filter(None, path.split('/'))
    result = self.NO
    for include in self.includes:
      match_me = True
      # Pair up path components with regexps (zip takes care of mismatched
      # lengths for free)
      for part, regex in zip(parts, include):
        if not regex.match(part):
          match_me = False
          break
      if match_me:
        # If the path matched the whole include path or more, it's a YES so stop
        # looking
        if len(parts) >= len(include):
          result = self.YES
          break
        # If the path ended but matched however much of the include it could,
        # it's a PARENT of an interesting path, but keep checking to see if it's
        # a YES for another pattern
        else:
          result = self.PARENT
    return result


class Lump(object):
  """A lump of RFC822-ish headers-plus-data from an SVN dump file."""
  # TODO(emosenkis): consider using the enum package for this
  DUMP = 0
  COPY = 1
  EXTERNALS = 2

  def __init__(self, path=None, action=None, kind=None, source=DUMP):
    self.headers = collections.OrderedDict()
    self.text = None
    self.props = None
    self.source = source
    if path is not None:
      self.headers['Node-path'] = path
    if action is not None:
      self.headers['Node-action'] = action
    if kind is not None:
      self.headers['Node-kind'] = kind

  def DeleteHeader(self, key):
    """Delete a header if it exists."""
    try:
      del self.headers[key]
    except KeyError:
      pass

  def _ParseProps(self, proptext):
    """Parses the given property string into self.props."""
    # TODO(emosenkis) use StringIO to clean this up
    self.props = collections.OrderedDict()
    index = 0
    while True:
      if proptext[index:index+2] == 'K ':
        wantval = True
      elif proptext[index:index+2] == 'D ':
        wantval = False
      elif proptext[index:index+9] == 'PROPS-END':
        break
      else:
        raise ValueError('Unrecognised record in props section: %s'
                         % proptext[index:])
      nlpos = proptext.find('\n', index)
      assert nlpos > 0
      namelen = int(proptext[index+2:nlpos])
      assert proptext[nlpos+1+namelen] == '\n'
      name = proptext[nlpos+1:nlpos+1+namelen]
      index = nlpos+2+namelen
      if wantval:
        assert proptext[index:index+2] == 'V '
        nlpos = proptext.find('\n', index)
        assert nlpos > 0
        proplen = int(proptext[index+2:nlpos])
        assert proptext[nlpos+1+proplen] == '\n'
        prop = proptext[nlpos+1:nlpos+1+proplen]
        index = nlpos+2+proplen
      else:
        prop = None
      self.props[name] = prop
    assert index + 10 == len(proptext), ('Trailing characters after PROPS-END:'
                                         ' "%s"' % proptext[index:])

  def SetProperty(self, key, val):
    """Set a property, creating self.props if it was None."""
    if self.props is None:
      self.props = collections.OrderedDict()
    self.props[key] = val

  def DeleteProperty(self, key):
    """Delete a property if it exists."""
    if self.props and key in self.props:
      del self.props[key]

  def _GeneratePropText(self):
    """Create a property block from self.props or empty string if it is None."""
    if self.props is None:
      return ''
    proptext = ''
    for key, val in self.props.iteritems():
      if val is None:
        proptext += 'D %d\n%s\n' % (len(key), key)
      else:
        proptext += 'K %d\n%s\nV %d\n%s\n' % (len(key), key, len(str(val)), val)
    proptext += 'PROPS-END\n'
    return proptext

  def _FixHeaders(self, proptext, revmap):
    """Recompute headers that depend on other headers or text content.

    Args:
      proptext: the property block in string form
      revmap: a dict mapping old revision number to new revision number

    Revision remapping also happens here, but probably it should happen in
    FilterRev() instead because _FixHeaders should be idempotent.

    SVN supports both MD5 and SHA1 checksums. MD5 is good enough to check for
    corruption, we're not worried about sabotage, it is slightly faster than
    SHA1, and compatible with older SVN repositories that don't have SHA1
    support.  We never modify the content, so we don't need to recompute the
    header if it already exists.
    """
    if proptext:
      self.headers['Prop-content-length'] = str(len(proptext))
    else:
      self.DeleteHeader('Prop-content-length')
    # Delete or add Text-content headers as necessary.
    if self.text is None:
      # Remove text-related headers since there is no text.
      self.DeleteHeader('Text-content-length')
      self.DeleteHeader('Text-content-md5')
      self.DeleteHeader('Text-content-sha1')
      self.DeleteHeader('Text-delta')
    else:
      self.headers['Text-content-length'] = str(len(self.text))

      # For Text-delta: true, the md5 is for the entire file, so never compute
      # the md5 of the delta.
      if ('Text-content-md5' not in self.headers
          and self.headers.get('Text-delta') != 'true'):
        m = md5.new()
        m.update(self.text)
        self.headers['Text-content-md5'] = m.hexdigest()
    # Generate overall Content-length header
    if proptext or self.text is not None:
      try:
        textlen = len(self.text)
      except TypeError:
        textlen = 0
      self.headers['Content-length'] = str(len(proptext) + textlen)
    else:
      self.DeleteHeader('Content-length')
    # Adjust the revision numbers as needed.
    # TODO(emosenkis) revmap needs to be persisted across executions of this
    # script or else copies from old revisions will refer to the wrong revision
    # See help for flag --drop-empty-revs for current restrictions.
    if revmap:
      for header in ['Revision-number', 'Node-copyfrom-rev']:
        if header in self.headers:
          old_rev = int(self.headers[header])
          self.headers[header] = str(revmap[old_rev])

  @classmethod
  def _ReadRFC822Headers(cls, stream):
    lump = cls()
    while True:
      line = stream.readline()
      # Empty string indicates EOF
      if not line:
        if lump.headers:
          raise EOFError('Reached EOF while reading headers')
        else:
          # EOF is ok if no headers are found first
          return None
      if line == '\n':
        if lump.headers:
          break  # newline after headers ends them
        else:
          continue  # newline before headers is simply ignored
      line = line.rstrip('\n')
      key, val = line.split(': ', 1)
      lump.headers[key] = val
    return lump

  @classmethod
  def Read(cls, stream):
    """Read a lump from the given file-like object.

    Args:
      stream: a readable file-like object

    Returns:
      a Lump read from stream or None if EOF is reached
    """
    lump = cls._ReadRFC822Headers(stream)
    if lump is None:
      return None
    pcl = int(lump.headers.get('Prop-content-length', '0'))
    if pcl > 0:
      # TODO(emosenkis): reexamine whether calling a private instance method
      # is the best way to do this
      lump._ParseProps(stream.read(pcl))
    if 'Text-content-length' in lump.headers:
      tcl = int(lump.headers['Text-content-length'])
      lump.text = stream.read(tcl)
    return lump

  def Write(self, stream, revmap):
    """Write a lump to the given file-like object.

    Args:
      stream: a writeable file-like object
      revmap: a dict mapping old revision number to new revision number

    This calls _FixHeaders to ensure that the lump's headers are consistent
    with its content (revision remapping also currently occurs there).
    """
    proptext = self._GeneratePropText()
    self._FixHeaders(proptext, revmap)
    for key, val in self.headers.iteritems():
      stream.write('%s: %s\n' % (key, val))
    stream.write('\n')
    stream.write(proptext)
    if self.text is not None:
      stream.write(self.text)
      stream.write('\n')
    if ('Prop-content-length' in self.headers
        or 'Text-content-length' in self.headers
        or 'Content-length' in self.headers):
      stream.write('\n')

  def DoesNotAffectExternals(self):
    """Can a Lump be determined to NOT affect svn:externals in any way?

    Returns:
      True if the Lump can be proven to not have any effect on the svn:externals
      property, False if this cannot be proven

    In most cases, it's quite obvious whether svn:externals is affected because
    the svn:externals property will be set on the Lump. However, the
    svn:externals property can be deleted merely by omitting it from the
    properties block. Therefore any properties block that does not contain
    svn:externals is a candidate for affecting externals. The exception to this
    is if the Prop-delta header is set to 'true'. In that case, property
    deletion is done explicitly so it can be ruled out if the svn:externals
    property is absent.
    """
    if self.headers['Node-action'] == 'delete':
      # Since delete actions are recursive, any existing svn:externals will be
      # deleted anyway.
      return True
    elif self.headers['Node-kind'] != 'dir':
      # Only directories can have externals.
      return True
    elif self.props is None:
      # Without a properties block, externals cannot be affected.
      return True
    elif 'svn:externals' in self.props:
      return False
    elif self.headers['Node-action'] == 'add':
      # Add actions explicitly declare their properties.
      return True
    elif self.headers.get('Prop-delta') == 'true':
      # If the svn:externals property is being deleted and the Prop-delta
      # headers is set to 'true', the svn:externals property will be set to
      # None, which would be caugh in the previous case. Therefore if Prop-delta
      # is set to 'true', we can rule out any modification of svn:externals.
      return True
    else:
      # There is no indication that svn:externals *is* being modified, but we
      # can't rule out the case where it is being deleted by omission from the
      # properties block (therefore we have to check the svn:externals property
      # of the previous revision to see if it used to be there).
      return False


def GrabLumpsForPath(srcrepo, srcrev, srcpath, dstpath, lump_source):
  """Generate lumps adding the contents of a given repo/rev/path.

  Args:
    srcrepo: path to the source repository
    srcrev: revision number
    srcpath: path within the source repository
    dstpath: destination path in the repository being filtered
    lump_source: the source attribute of the Lumps generated

  Returns:
    a list of Lumps

  Raises:
    RuntimeError: if svnrdump seems to have failed

  This is the fundamental feature of a working svndumpfilter replacement. In the
  upstream svndumpfilter, copyfrom operations that reference paths that are
  excluded by filtering cannot be resolved. To fix that, each svndumpfilter
  replacement must find a way to turn that copy operation into a series of add
  operations.

  svndumpfilter2 originally did this by calling the svnlook utility
  to list the directory structure, grab file contents, list property names, and
  grab property values. This resulted in calling svnlook once per tree, twice
  per file, and once per property.

  For a time, we tried instead making a single call to svnrdump which, unlike
  svnadmin dump (which is used by svndumpfilter3 with disastrous results for
  performance) can output a dump file containing only the desired subdirectory.
  The dump file is parsed into lumps, the paths have the destination path
  prepended, and the lumps are inserted into the dump.

  Unfortunately, svnrdump always produces format 3 dumps which use deltas. Even
  though it was only used for a single non-incremental revision, every file's
  contents were in the form of a delta. Since some tools (such as p4convert-svn)
  do not support deltas, svnrdump was done away with, replaced by the SVN SWIG
  bindings.

  It turns out that this same functionality is critical to 'internalizing' SVN
  externals. By generating lumps that add all of the files and directories in
  the repo/rev/path referenced by an svn:external property, the history can be
  made to look as though the actual files had been there all along, not just a
  reference to them. Further filtering of these generated lumps must be done in
  the case of externals to delete externals when they are removed and modify the
  filesystem when the revision is changed, rather than deleting and reading it
  every time (see ExternalsDescription.FromRev, ExternalsDescription.Diff,
  DiffPaths).
  """
  srcrepo = svn_core.svn_path_canonicalize(srcrepo)
  repo_ptr = svn_repos.open(srcrepo)
  fs = svn_repos.fs(repo_ptr)
  root = svn_fs.revision_root(fs, srcrev)
  output = []
  # Perform a depth-first search
  stack = [srcpath]
  while stack:
    path = stack.pop()
    if srcpath:
      relative_path = path[len(srcpath):]
      node_path = dstpath + relative_path
    else:
      node_path = (dstpath + '/' + path) if path else dstpath
    if svn_fs.is_dir(root, path):
      lump = Lump(action='add', kind='dir', path=node_path, source=lump_source)
      # Add children to the stack
      prefix = (path + '/') if path else ''
      for name in svn_fs.dir_entries(root, path).keys():
        stack.append(prefix + name)
    else:
      lump = Lump(action='add', kind='file', path=node_path, source=lump_source)
      # Fetch file content
      stream = svn_fs.file_contents(root, path)
      lump.text = _ReadSVNStream(stream)
      checksum = svn_fs.file_md5_checksum(root, path)
      lump.headers['Text-content-md5'] = checksum.encode('hex_codec')
    # Fetch properties
    props = svn_fs.node_proplist(root, path)
    lump.props = {key: str(value) for key, value in props.iteritems()}
    output.append(lump)
  return output


def _ReadSVNStream(stream):
  out = ''
  while True:
    data = svn_core.svn_stream_read(stream, 16384)
    if not data:
      break
    out += data
  return out


def ExtractNodeKind(srcrepo, srcrev, srcpath):
  """Checks if a path is a file or a dir."""
  svnlook_fs = Popen('svnlook',
                     'filesize',
                     srcrepo,
                     '-r%s' % srcrev,
                     srcpath,
                     stderr=subprocess.PIPE)

  with svnlook_fs.stdout, svnlook_fs.stderr:
    # Consume the output and errors, if any
    svnlook_fs.stdout.read()
    svnlook_fs.stderr.read()
  # If the command returns zero it's a file, else it's a dir
  if CheckExitCode(svnlook_fs, allow_failure=True):
    return 'dir'
  else:
    return 'file'


def ExtractNodeKinds(srcrepo, srcrev, srcpath):
  """Creates a mapping of path to kind (dir or file).

  Args:
    srcrepo: repository path
    srcrev: revision number
    srcpath: path within repository

  Returns:
    a dict whose keys are the paths of all files and directories under the
    given path and whose values are 'dir' for directories and 'file' for files

  This information is necessary to construct new Lumps relating to paths in the
  repository to fill the Node-kind header. Unfortunately, this information does
  not seem to be available from Subversion any other way.
  """
  nodes = {}
  cmd = [
      'svnlook',
      'tree',
      '--full-paths',
      '-r%s' % srcrev,
      srcrepo,
      srcpath,
      ]
  svnlook_tree = Popen(*cmd)
  with svnlook_tree.stdout as path_stream:
    for path in path_stream:
      path = path.rstrip('\n')
      # Ignore blank lines
      if not path:
        continue
      # Special case the root path
      if path == srcpath + '/':
        nodes[''] = 'dir'
        continue
      elif path == srcpath:
        nodes[''] = 'file'
        continue
      # Strip off the root path + /
      path = path[len(srcpath) + 1:].rstrip('\n')
      # Check for trailing /
      if path.endswith('/'):
        nodes[path[:-1]] = 'dir'
      else:
        nodes[path] = 'file'
  CheckExitCode(svnlook_tree)
  return nodes


def DiffPaths(repo, oldpath, oldrev, newpath, newrev):
  """Figure out what changed between two revisions of a directory."""
  # This prefix will be stripped off the beginning of each path. The portion
  # after file:// must be %-quoted, but file:// would turn into file%3A// if
  # quoted. We strip the unquoted version, so here we just take the length so we
  # know how much to strip off.
  prefix_len = len('file://%s/%s/' % (repo, oldpath))
  contents_ops = {' ': None, 'A': 'add', 'M': 'modify', 'D': 'delete'}
  props_ops = {' ': None, 'M': 'modify'}
  svn_diff = Popen('svn',
                   'diff',
                   '--summarize',
                   '--old=file://%s/%s@%s' % (urllib.quote(repo),
                                              urllib.quote(oldpath),
                                              oldrev),
                   '--new=file://%s/%s@%s' % (urllib.quote(repo),
                                              urllib.quote(newpath),
                                              newrev))
  with svn_diff.stdout as diff_stream:
    deleted = {}
    changes = {}
    for line in diff_stream:
      line = line.rstrip('\n')

      # TODO(emosenkis): subclass Exception
      if line[0] not in contents_ops:
        raise ValueError('Unknown contents operation "%s" in svn diff'
                         % line[0])
      if line[1] not in props_ops:
        raise ValueError('Unknown properties operation "%s" in svn diff'
                         % line[0])

      contents_op = contents_ops[line[0]]
      props_op = props_ops[line[1]]

      # Find the correct starting point
      path = line[line.find('file://'):]
      # Unquote %-quoted characters
      path = urllib.unquote(path)
      # Chop off the prefix and trailing slash (if there is no trailing slash,
      # it will return an empty string like we want in that case)
      path = path[prefix_len:]

      # Split out deleted so we can do recursive deletes as one operation
      if contents_op == 'delete':
        deleted[path] = (contents_op, props_op)
      else:
        changes[path] = (contents_op, props_op)

  CheckExitCode(svn_diff)

  # Ignore children of directories being deleted
  for path in deleted:
    if '/' in path:
      parent = path[0:path.rfind('/')]
      # Ignore paths whose parent dir got deleted
      if parent in deleted:
        continue
    # Merge non-redundant deletes back into changes
    changes[path] = deleted[path]
  return changes


# Higher-level class that makes use of the above to filter dump
# file fragments a whole revision at a time.
class Filter(object):
  """Filter SVN dumps one revision at a time."""

  def __init__(self,
               repo,
               paths,
               input_stream=sys.stdin,
               output_stream=sys.stdout,
               drop_empty_revs=True,
               revmap=None,
               externals_map=None,
               delete_properties=None,
               truncate_revs=None):
    self.repo = repo
    self.paths = paths
    self.input_stream = input_stream
    self.output_stream = output_stream
    self.drop_empty_revs = drop_empty_revs
    self.revmap = revmap
    self.externals_map = externals_map
    self.delete_properties = delete_properties
    self.truncate_revs = set(truncate_revs) if truncate_revs else set()

  def Filter(self):
    """Filter an entire dump file."""
    # Pass the dump-file header through unchanged
    lump = Lump.Read(self.input_stream)
    while 'Revision-number' not in lump.headers:
      lump.Write(self.output_stream, self.revmap)
      lump = Lump.Read(self.input_stream)

    revhdr = lump

    current_output_rev = 0
    while revhdr is not None:
      # Read revision header.
      assert 'Revision-number' in revhdr.headers
      contents = []
      # Read revision contents.
      while True:
        lump = Lump.Read(self.input_stream)
        if lump is None or 'Revision-number' in lump.headers:
          newrevhdr = lump
          break
        contents.append(lump)

      revision_number = int(revhdr.headers['Revision-number'])

      # Alter the contents of the revision.
      contents = self.FilterRev(revhdr, contents)

      # Determine whether we should output this revision.  We only
      # update the current_output_rev if we're actually going to write
      # something.
      should_write = contents or not self.drop_empty_revs
      if should_write:
        current_output_rev += 1

      # Update our revmap with information about this revision.  Note that
      # if this revision won't be written, current_output_rev still points
      # to the last version we dumped.
      if self.drop_empty_revs and self.revmap is not None:
        self.revmap[revision_number] = current_output_rev

      # Write out this revision, if that's what we've decided to do.
      if should_write:
        revhdr.Write(self.output_stream, self.revmap)
        for lump in contents:
          lump.Write(self.output_stream, self.revmap)

      # And loop round again.
      revhdr = newrevhdr

  def FilterRev(self, revhdr, contents):
    """Filter all lumps in a revision."""
    revision_number = int(revhdr.headers['Revision-number'])
    LOGGER.debug('Filtering r%s', revision_number)

    if revision_number in self.truncate_revs:
      LOGGER.warning('Truncating known bad revision r%s', revision_number)
      return []

    new_contents = []
    for lump in contents:
      new_contents.extend(self._FilterLump(revision_number, lump))

    if self.delete_properties:
      for lump in new_contents:
        for prop in self.delete_properties:
          lump.DeleteProperty(prop)

    self._FlattenMultipleActions(revision_number, new_contents)

    return new_contents

  def _FilterLump(self, revision_number, lump):
    """Filter a single lump by path; import dangling copies and externals.

    Args:
      revision_number: the number of the revision that the Lump belongs to
      lump: a Lump

    Returns:
      a list of zero or more Lumps

    An InterestingPaths is used to filter out excluded paths. Paths determined
    to be potential PARENTs of included paths are forced to be propertyless
    directories in case they do end up having included contents added to them.
    Add and delete operations are permitted on PARENTs, but change operations
    are discarded as they are not allowed to have properties or contents to
    change.

    _FixCopyFrom is called to fix copy operations that refer to excluded paths
    _InternalizeExternals is called if an externals map exists and the
    svn:externals property is set on the given Lump.
    """
    path = lump.headers['Node-path']

    interest = self.paths.Interesting(path)

    if interest is InterestingPaths.NO:
      return []  # boooring
    elif interest is InterestingPaths.PARENT:
      # Parent dirs of interesting paths are coerced to be propertyless
      # directories
      if lump.headers['Node-action'] == 'change':
        return []  # Parents can only be added or deleted
      elif lump.headers['Node-action'] in ('add', 'replace'):
        if lump.headers['Node-kind'] == 'file':
          # Files are turned into directories
          lump = Lump(path=path, kind='dir', action=lump.headers['Node-action'])
        else:
          # Directories have their properties removed
          lump.props = None
      else:
        assert lump.headers['Node-action'] == 'delete'

    if 'Node-copyfrom-path' in lump.headers:
      copyless_lumps = self._FixCopyFrom(lump)
    else:
      copyless_lumps = (lump,)

    output = []
    for copyless_lump in copyless_lumps:
      # Internalizing externals is enabled if externals_map is populated
      if not self.externals_map or copyless_lump.DoesNotAffectExternals():
        # Externals are not affected or internalizing externals is not enabled
        output.append(copyless_lump)
      else:
        output.extend(
            self._InternalizeExternals(revision_number, copyless_lump))
    return output

  def _FixCopyFrom(self, lump):
    """Replace copies from excluded paths with adds.

    Args:
     lump: a Lump that represents a copy operation

    Returns:
      a list of one or more Lumps

    For a longer discussion, see GrabLumpsForPath.
    """
    # Is the copy valid given our path filters?
    srcrev = int(lump.headers['Node-copyfrom-rev'])
    srcpath = lump.headers['Node-copyfrom-path']
    dstpath = lump.headers['Node-path']

    if self.paths.Interesting(srcpath) is InterestingPaths.YES:
      # Copy is valid, leave it as is.
      return (lump,)

    if (self.paths.Interesting(dstpath) is InterestingPaths.PARENT
        and srcpath == dstpath):
      # When copying into a parent path, it is usually necessary to use
      # _FilterPaths to determine which parts of the copy source should be
      # copied and which should not. However, if the copy source directory is
      # the same as the destination, it is safe to allow the copy operation to
      # remain as-is because the source will have already been filtered
      # correctly.
      return (lump,)

    # Copy from a boring path to an interesting one, meaning we must extract the
    # subtree and convert it into lumps.
    output = []
    if self.paths.Interesting(dstpath) is InterestingPaths.YES:
      # The entire destination path is included, grab it all!
      output.extend(GrabLumpsForPath(self.repo, srcrev, srcpath, dstpath,
                                     Lump.COPY))
    else:
      # The destination itself is not included, but some included paths may
      # be created by this copy operation
      empty_dirs, recursive_dirs = self._FilterPaths(srcrev, srcpath, dstpath)
      for dir_name in empty_dirs:
        dir_name = (dstpath + '/' + dir_name) if dir_name else dstpath
        output.append(Lump(kind='dir', action='add', path=dir_name,
                           source=Lump.COPY))
      for dir_name in recursive_dirs:
        output.extend(GrabLumpsForPath(self.repo,
                                       srcrev,
                                       srcpath + '/' + dir_name,
                                       dstpath + '/' + dir_name,
                                       Lump.COPY))
    if lump.text is not None:
      # This was a copyfrom _plus_ some sort of
      # delta or new contents, which means that
      # having done the copy we now also need a
      # change record providing the new contents.
      lump.headers['Node-action'] = 'change'
      del lump.headers['Node-copyfrom-rev']
      del lump.headers['Node-copyfrom-path']
      lump.DeleteHeader('Text-copy-source-md5')
      lump.DeleteHeader('Text-copy-source-sha1')
      output.append(lump)
    return output

  def _InternalizeExternals(self, revision_number, lump):
    """Use the externals map to replace externals with real files.

    Args:
      revision_number: the number of the revision being operated on
      lump: a Lump with an svn:externals property to be fixed

    Returns:
      a list of Lumps including the original lump passed in and any lumps
      generated in order to pull in externals

    Triggered by --externals-map
    """
    # Always include the input lump in output
    output = [lump]
    # Get the root of the externals
    path = lump.headers['Node-path']
    # Parse the new value of svn:externals
    if lump.props.get('svn:externals'):
      # The property is set
      # TODO(emosenkis): change svn:externals to exclude the externals being
      # internalized.
      new_externals = ExternalsDescription.Parse(
          self.repo, revision_number, path,
          lump.props['svn:externals'], self.externals_map)
    else:
      # The property is absent or it is set to None, signifying it is being
      # deleted with Props-delta: true. Therefore we must check if the previous
      # revision has any externals that we should delete.
      new_externals = {}
    # Get the previous value of svn:externals
    prev_rev = revision_number - 1
    prev_externals = ExternalsDescription.FromRev(self.repo, prev_rev, path,
                                                  self.externals_map)
    # Check how the externals descriptions have changed since last revision
    added, changed, deleted = ExternalsDescription.Diff(prev_externals,
                                                        new_externals)
    LOGGER.debug('Changed externals for %s\n'
                 'from: %s\n'
                 'to: %s\n'
                 'Added: %s\n'
                 'Changed: %s\n'
                 'Deleted: %s',
                 path,
                 prev_externals,
                 new_externals,
                 added,
                 changed,
                 deleted)
    # First do changes because they might be converted into (delete, add)
    for old, new in changed:
      # Check whether processing as a change is possible and optimal
      if (old.srcrev is None
          or (new.srcrepo == self.repo and
              self.paths.Interesting(new.srcpath) is InterestingPaths.YES)):
        # - We can't do a diff if we don't know the old revision.
        # - If this external points inside the same repository to a path that is
        #   included by the filters, it's faster to just do a new copy operation
        #   than to update the contents.
        deleted.append(old.dstpath)
        added.append(new)
        continue
      if new.srcrev is None:
        LOGGER.warning('Can\'t guess rev # for external repo %s', new)
        continue
      output.extend(self._ApplyExternalsChange(path, old, new))
    # Delete former externals paths
    for dstpath in deleted:
      # TODO(emosenkis): if dstpath contains '/', introspect the source
      # repository to see if the intermediary directory exists. If not, delete
      # it instead.
      output.append(Lump(
          path=path + '/' + dstpath, action='delete', source=Lump.EXTERNALS))
    # Add new externals
    for description in added:
      # TODO(emosenkis): if dstpath contains '/', introspect the source
      # repository to see if the intermediary directory exists (if not, add a
      # Lump to create it).
      if (description.srcrepo == self.repo and
          self.paths.Interesting(description.srcpath) is InterestingPaths.YES):
        # External is in the same repo - do it as a copy
        # We don't support external files
        copy_lump = Lump(path=path +'/' + description.dstpath,
                         kind='dir',
                         action='add',
                         source=Lump.EXTERNALS)
        copy_lump.headers['Node-copyfrom-path'] = description.srcpath
        copy_lump.headers['Node-copyfrom-rev'] = description.srcrev
        output.append(copy_lump)
      else:
        # External is not in the same repo - pull it in manually
        if description.srcrev is None:
          LOGGER.warning('Can\'t guess rev # for externals repo %s',
                         description)
          continue
        output.extend(
            GrabLumpsForPath(description.srcrepo,
                             description.srcrev,
                             description.srcpath,
                             path + '/' + description.dstpath,
                             Lump.EXTERNALS))
    return output

  def _ApplyExternalsChange(self, path, old, new):
    """Create Lumps to simulate the change from old to new ExternalsDescription.

    Args:
      path: the path on which the svn:externals property is set
      old: the ExternalsDescription from the previous revision
      new: an ExternalsDescription from the new revision

    Returns:
      a list of zero or more Lumps that convert the contents of the path
      referenced by old into the contents of the path referenced by new

    Raises:
      RuntimeError: if unsupported operations are shown in the svn diff output

    This is only possible if both descriptions refer to the same repository.

    DiffPaths is called to find out which paths have changed, whether their
    properties, contents, or both have changed, and whether each path is a file
    or a directory. Lumps are generated to perform all deletes, then
    GrabLumpsForPath is called to get lumps creating the new state. The
    resulting lumps are filtered through the list of changes, changing the
    action from add to change and deleting the properties or text content blocks
    if only the other is being changed. Lumps for paths listed as adds are
    passed through unchanged and lumps not mentioned as deleted, changed, or
    added are dropped.
    """
    # Sanity check
    assert old.srcrepo == new.srcrepo
    output = []

    # Get a list of changes between the old and new revisions
    paths_changed = DiffPaths(new.srcrepo,
                              old.srcpath,
                              old.srcrev,
                              new.srcpath,
                              new.srcrev)

    # If nothing changed, we're done
    if not paths_changed:
      return output

    # First do deletes
    for chpath in paths_changed:
      contents_op, props_op = paths_changed[chpath]
      if contents_op == 'delete':
        # Sanity check
        assert props_op is None
        output.append(Lump(
            path='%s/%s/%s' % (path, new.dstpath, chpath),
            action='delete',
            source=Lump.EXTERNALS))

    # Grab lumps to create the new version
    add_lumps = GrabLumpsForPath(new.srcrepo,
                                 new.srcrev,
                                 new.srcpath,
                                 path + '/' + new.dstpath,
                                 Lump.EXTERNALS)

    # Filter the lumps to create a change instead of an add
    for add_lump in add_lumps:
      lump_path = add_lump.headers['Node-path']
      # Strip off the dstpath
      lump_path = lump_path[len(path) + len(new.dstpath) + 2:]
      # Check if the path changed
      if lump_path not in paths_changed:
        # Ignore paths that haven't changed
        continue

      # Find out what changed
      contents_op, props_op = paths_changed[lump_path]

      # Handle contents_op
      if contents_op == 'add':
        # If it's an add, pass through unchanged
        pass
      elif contents_op == 'modify':
        add_lump.headers['Node-action'] = 'change'
      elif contents_op is None:
        # Drop text contents - they haven't changed
        add_lump.text = None
      else:
        raise RuntimeError('Unexpected contents operation %s in svn diff'
                           % contents_op)

      # Handle props_op
      if props_op is None and contents_op != 'add':
        # Drop props - they haven't changed
        add_lump.props = None

      # This lump has lived to see another day...
      output.append(add_lump)
    return output

  def _FilterPaths(self, srcrev, srcpath, dstpath):
    """Determine paths to import, either recursively or as empty directories.

    Args:
      srcrev: source revision
      srcpath: source path
      dstpath: destination path

    Returns:
      empty_dirs: a list of dirs to create empty
      recursive_dirs: a list of dirs to copy recursively

    Sometimes, a directory that is included by one of the path filters is
    created by a copy operation on a parent directory that is not included by
    the filters:

      included: trunk/foo

      svn rm trunk
      svn copy branches/bar trunk

    When that copy operation is processed, this function is called to determine
    which paths from branches/bar should be created as empty directories, which
    should be copied recursively, and which should be discarded in order to get
    the correct contents of trunk/foo after the copy.
    """
    empty_dirs = []
    recursive_dirs = []
    # Get a list of paths
    paths = ExtractNodeKinds(self.repo, srcrev, srcpath)
    # Sort to ensure directories come before their children
    for path in sorted(paths):
      full_path = dstpath + '/' + path if path else dstpath
      interest = self.paths.Interesting(full_path)
      if interest is InterestingPaths.PARENT:
        empty_dirs.append(path)
      elif interest is InterestingPaths.YES:
        include_me = True
        for parent_dir in recursive_dirs:
          if path.startswith(parent_dir + '/'):
            include_me = False
            break
        if include_me:
          recursive_dirs.append(path)
    return empty_dirs, recursive_dirs

  def _FlattenMultipleActions(self, revision_number, contents):
    """Fix multiple actions for a single path in one revision.

    Args:
      revision_number: the number of the revision in question
      contents: a list of all the Lumps in the revision (edited in-place)

    Raises:
      ValueError: if an unexpected sequence of actions is found or an (add,
                  change) pair includes a Text-delta change.

    There are several cases that can arise which would cause there to be
    multiple actions for a single path in one revision:
    - The original dump file contained a (delete, add) pair which makes changes
      and breaks the history of a file. This can be left alone.
    - A copy from a path not included by the filter includes modifications,
      resulting in an (add, change) pair. The change is merged into the add.
      This can also occur if a copy from a path not included by the filter is
      followed by a change to a subpath.
    - A copy from a path not included by the filter is followed by another copy
      on a subpath resulting in an (add, add) pair. The first add can be dropped
      in favor of the second.
    - A real directory is deleted in the same revision that an external is added
      at the same path. Subversion doesn't know to treat the external like a
      real path so it might list the addition of the external before the
      deletion of its destination path. In that case, the delete is moved to be
      before the add.
    - A copy from a path not included by the filter is followed by a delete on a
      subpath resulting in an (add, delete) pair. Both can be dropped since they
      cancel each other.
    - Any other case is not expected and will raise an exception.

    +--------------------------------------------------------------------------+
    |         2nd action|    delete   |     add    |    change   |   replace   |
    |    1st action     |             |            |             |             |
    |--------------------------------------------------------------------------|
    |       delete      |      !      |  replace   |      !      |      !      |
    |--------------------------------------------------------------------------|
    |        add        |    None*    |    2nd     |     add     |      !      |
    |--------------------------------------------------------------------------|
    |       change      |      !      |     !      |    change   |      !      |
    |--------------------------------------------------------------------------|
    |      replace      |      !      |     !      |    replace  |      !      |
    |--------------------------------------------------------------------------|
    | Result                    | Meaning                                      |
    |--------------------------------------------------------------------------|
    | replace/add/change/delete | merge into a single action of that type      |
    |--------------------------------------------------------------------------|
    | 1st/2nd                   | only the 1st or 2nd action survives          |
    |--------------------------------------------------------------------------|
    | None                      | both actions are purged                      |
    |--------------------------------------------------------------------------|
    | !                         | an exception is raised                       |
    +--------------------------------------------------------------------------+

    * (add, delete) is converted to (delete, add) by pulling the delete action
      earlier if the add's source is EXTERNALS and the delete's source is DUMP
      in order to handle the case where a normal directory is converted into an
      external by deleting the real directory and setting the parent's
      svn:externals property in the same revision (so Subversion does not know
      that the delete must preceed the property change).
    """
    paths = collections.defaultdict(list)
    for lump in contents:
      path = lump.headers['Node-path']
      paths[path].append(lump)
    for path, lumps in paths.iteritems():
      while len(lumps) > 1:
        data = self._ActionPairFlattener(self.repo, revision_number, contents,
                                         path, lumps)
        data.Flatten()

  class _ActionPairFlattener(object):
    """Helper for _FlattenMultipleActions."""

    def __init__(self, repo, revision_number, contents, path, lumps):
      """Create an ActionPairFlattener.

      Args:
        repo: the source repo of the dump file being filtered
        revision_number: the revision currently being filtered
        contents: a list of all Lumps in the current revision
        path: the path whose actions are to be flattened
        lumps: a list of all Lumps in the current revision for path

      self.first and self.second are set to the first two items in lumps for
      convenience.
      """
      self.repo = repo
      self.revision_number = revision_number
      self.contents = contents
      self.path = path
      self.lumps = lumps
      self.first = lumps[0]
      self.second = lumps[1]

    def Flatten(self):
      """Merge the first two Lumps together.

      This function delegates to a number of helpers to do the action merge,
      depending on the types of the two actions. Each helper must be careful to
      make the appropriate changes to self.contents and self.lumps:
      - self.contents is the actual list of Lumps that will be output for the
        current revision. If a Lump is deleted or the order is changed, that
        modification must be made to self.contents.
      - self.lumps is the list of all Lumps for the same path. If a Lump is
        deleted or the order is changed, that modification must also be made to
        self.lumps so that merging can proceed in the correct order, and without
        trying to merge the same two Lumps again.

      Raises:
        ValueError: if an action pair is encountered for which no merge strategy
                    is defined
      """
      actions = (self.first.headers['Node-action'],
                 self.second.headers['Node-action'])
      if actions == ('add', 'add'):
        self.DropExtraneousAdd()
      elif (actions[0] in ('add', 'change', 'replace')
            and actions[1] == 'change'):
        self.MergeChange(actions[0])
      elif actions == ('add', 'delete'):
        if (self.first.source is Lump.EXTERNALS
            and self.second.source is Lump.DUMP):
          # A real path is being replaced with an external. Subversion doesn't
          # know that the external needs to go after the delete, so we have to
          # move the delete before the add.
          self.MoveDeleteToBeforeAdd()
        else:
          self.DropAddDeletePair()
      elif actions == ('delete', 'add'):
        # Collapse delete followed by add into replace.
        self.ConvertDeleteAndAddIntoReplace()
      else:
        # Catch-all for cases we shouldn't ever encounter and/or wouldn't
        # know how to resolve: (change, add), (change, change),
        # (change, delete), (delete, change), (delete, delete)
        raise ValueError('Found (%s, %s) for path %s in r%s'
                         % (actions[0], actions[1], self.path,
                            self.revision_number))

    def DropExtraneousAdd(self):
      LOGGER.warning('Found (add,add) - deleting first for path %s in r%s',
                     self.path, self.revision_number)
      self.contents.remove(self.first)
      self.lumps.remove(self.first)

    def MergeChange(self, first_action):
      """Apply a change action to an add|change|replace for the same path."""
      LOGGER.warning('Found (%s, change) - merging for path %s in r%s',
                     first_action, self.path, self.revision_number)
      if self.second.text is not None:
        if self.second.headers.get('Text-delta', 'false') == 'true':
          raise ValueError('Cannot merge (%s, change) when Text-delta is set '
                           ' to true for path %s in r%s'
                           % (first_action, self.path, self.revision_number))
        self.first.text = self.second.text
        self.first.DeleteHeader('Text-delta')
        new_md5 = self.second.headers.get('Text-content-md5')
        if new_md5:
          self.first.headers['Text-content-md5'] = new_md5
        else:
          self.first.DeleteHeader('Text-content-md5')
      if self.second.props is not None:
        if self.first.props is None:
          self.first.props = self.second.props
        elif self.second.headers.get('Prop-delta', 'false') == 'true':
          self.first.props.update(self.second.props)
          if self.first.headers.get('Prop-delta', 'false') != 'true':
            # Actually delete properties, don't set them to None
            for key, value in self.first.props.items():
              if value is None:
                del self.first.props[key]
        else:
          self.first.props = self.second.props
      self.contents.remove(self.second)
      self.lumps.remove(self.second)

    def MoveDeleteToBeforeAdd(self):
      """Move a delete action to before an add for the same path."""
      LOGGER.warning('Found externals-related add followed by regular delete -'
                     ' moving the delete before the add for path %s in r%s',
                     self.path, self.revision_number)
      # Remove the delete lump, then insert it before the add.
      self.contents.remove(self.second)
      index = self.contents.index(self.first)
      self.contents.insert(index, self.second)
      # Reprocess this as (delete, add) by putting them back on the deque
      # in the new order. self.first and self.second are convenience copies of
      # self.lumps[0] and self.lumps[1] so we can rearrange them easily.
      self.lumps[0] = self.second
      self.lumps[1] = self.first

    def DropAddDeletePair(self):
      LOGGER.warning('Found (add, delete) - dropping both for path %s in r%s',
                     self.path, self.revision_number)
      self.contents.remove(self.first)
      self.contents.remove(self.second)
      self.lumps.remove(self.first)
      self.lumps.remove(self.second)

    def ConvertDeleteAndAddIntoReplace(self):
      LOGGER.warning('Converting (del, add) to replace for path %s in r%s',
                     self.path, self.revision_number)
      self.second.headers['Node-action'] = 'replace'
      self.contents.remove(self.first)
      self.lumps.remove(self.first)


def main(argv):
  # Parse command-line arguments.
  parser = argparse.ArgumentParser(epilog=__doc__,
                                   formatter_class=(
                                       argparse.RawDescriptionHelpFormatter))
  parser.add_argument('--include',
                      action='append',
                      default=[],
                      metavar='REGEXP',
                      help='Only include paths that match this regular'
                      ' expression (may be used multiple times).')
  parser.add_argument('--repo',
                      metavar='PATH',
                      help='Path of the SVN repo that produced the dump file.')
  parser.add_argument('--externals-map',
                      type=file,
                      metavar='FILE',
                      help='File mapping URLs used to reference externals to'
                      ' path of local copy of referenced repository. Format is'
                      ' one local path per line:  PATH [URL [URL ...]].')
  parser.add_argument('--delete-property',
                      action='append',
                      metavar='PROPNAME',
                      help='Delete an SVN property (such as svn:keywords) from'
                      ' all paths (may be used multiple times).')
  parser.add_argument('--truncate-rev',
                      action='append',
                      type=int,
                      metavar='REVNUM',
                      help='Drop all changes made in a particular revision, but'
                      ' keep the commit message (DANGEROUS). If combined with'
                      ' --drop-empty-revs, the revision wil be deleted entirely'
                      ' (EVEN MORE DANGEROUS) (may be used multiple times).')
  parser.add_argument('--drop-empty-revs',
                      action='store_true',
                      help='Delete empty revisions caused by path filtering or'
                      ' --truncate-rev (default is to output empty revisions'
                      ' with date, commit message, and author intact).')
  # TODO(emosenkis): make this accept an optional file argument that the revmap
  # will be loaded from if it exists, then serialized to upon completion.
  parser.add_argument('--renumber-revs',
                      action='store_true',
                      help='Renumber revisions to be sequential after'
                      ' --drop-empty-revs or damaged data caused gaps in'
                      ' revision numbers. This should only be used when'
                      ' filtering the entire history at once, e.g. not using'
                      ' the -r option of svnadmin dump or svnrdump.')
  parser.add_argument('--debug', action='store_true',
                      help='Log verbosely to stderr.')

  options = parser.parse_args(argv)

  if options.debug:
    logging.basicConfig(level=logging.DEBUG)

  # We use this table to map input revisions to output revisions.
  if options.renumber_revs:
    revmap = {}
  else:
    revmap = None

  # Load the externals map if given
  if options.externals_map:
    externals_map = {}
    for line in options.externals_map:
      if line.startswith('#'):
        continue
      parts = line.split()
      # By default, each path is mapped to its own file:// URL
      externals_map['file://' + urllib.quote(parts[0])] = parts[0]
      # Add any user-specified mappings (these may replace the default file://
      # mapping or add aliases using file://, http[s]://, svn+ssh://, etc.
      # %-encoding can be used in the file for URLs that contain whitespace
      # (or other weird characters)
      for url in parts[1:]:
        externals_map[urllib.unquote(url)] = parts[0]
    options.externals_map.close()
    LOGGER.debug('Found externals definitions:\n%s',
                 '\n'.join(
                     ['%s -> %s' % (url, path)
                      for url, path in sorted(externals_map.iteritems())]))
  else:
    externals_map = None

  # Create a Filter
  filt = Filter(options.repo,
                InterestingPaths(options.include),
                drop_empty_revs=options.drop_empty_revs,
                revmap=revmap,
                externals_map=externals_map,
                delete_properties=options.delete_property,
                truncate_revs=options.truncate_rev)

  filt.Filter()


if __name__ == '__main__':
  main(sys.argv[1:])

# vim: ts=2 sw=2 tw=80
