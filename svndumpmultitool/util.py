# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Helper functions for svndumpmultitool."""

from __future__ import absolute_import

import logging
import os
import re
import subprocess
import urllib

LOGGER = logging.getLogger(__name__)


def Popen(*cmd, **kwargs):
  """Log command, execute it, and pipe in stdout with buffering.

  Args:
    *cmd: command to run (each command-line argument as a separate argument)
    **kwargs: passed through to subprocess.Popen

  Returns:
    output of subprocess.Popen with additional cmd attribute set to *cmd

  If stdout or bufsize kwargs are not provided, they will default to
  subprocess.PIPE and 10240, respectively. Specify None or 0 to get
  subprocess.Popen's default behavior.

  See subprocess.Popen for details.
  """
  LOGGER.debug('Executing %s', cmd)
  kwargs.setdefault('stdout', subprocess.PIPE)
  kwargs.setdefault('bufsize', 10240)
  sub = subprocess.Popen(cmd, **kwargs)
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
  code = sub.wait()
  if code == 0:
    LOGGER.debug('Finished %s', sub.cmd)
  elif allow_failure:
    LOGGER.debug('%s returned non-zero exit status %s', sub.cmd, code)
  else:
    raise subprocess.CalledProcessError(returncode=code, cmd=sub.cmd)
  return code


def FileURL(repo, path, rev, quote=True):
  """Create a file:// URL to an SVN repo.

  Args:
    repo: the absolute path of the SVN repository root
    path: the path within the SVN repository or None
    rev: the revision number or None
    quote: if True, urllib.quote will be applied to repo and path

  Returns:
    a file:// URL representing the given repo, path, and revision, possibly
    quoted
  """
  if quote:
    repo = urllib.quote(repo)
  url = 'file://' + repo
  if path:
    if quote:
      path = urllib.quote(path)
    url += '/' + path
  if rev is not None:
    url += '@' + str(rev)
  return url


class PathFilter(object):
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
  that are included).

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
  # Not included
  NO = 0
  # Could potentially be the parent directory of an included path
  PARENT = 1
  # Directly included
  YES = 2

  def __init__(self, includes):
    """Create a new PathFilter.

    Args:
      includes: an iterable of regexp patterns (strings)

    See PathFilter for details.

    Note: if includes is empty, the resulting PathFilter will include all paths.
    """
    self._includes = []
    # Split include paths on directory separators and compile as regexps
    for include in includes:
      include = include.strip('/')
      self._includes.append([re.compile(r'\A%s\Z' % regex)
                             for regex in include.split('/')])

  def CheckPath(self, path):
    """Check if a path is included, excluded, or a potential parent of included.

    Args:
      path: a path

    Returns:
      YES, NO, or PARENT, as described below

    The path is normalized and split on /'s. Then each included path regexp is
    tried in succession. Path components are matched against the corresponding
    regexp components. The path is only considered to match a path regexp if all
    of its components match their corresponding regexp components.
    - If no regexps were passed when this PathFilter was initialized, YES is
      returned.
    - If all components match and the path was long enough to use all components
      of the path regexp (or more), YES is returned.
    - If all components match, but the path ran out of components with path
      regexp components left over, the path is tentatively a PARENT unless one
      of the remaining path regexps causes it to be marked as a YES.
    - If no path regexp matches the path, NO is returned.
    """
    # No includes means everything is included
    if not self._includes:
      return self.YES
    path = os.path.normpath(path)
    # Normpath converts the empty string to .
    if path == '.':
      path = ''
    parts = filter(None, path.split('/'))
    result = self.NO
    for include in self._includes:
      match_me = True
      # Compare each path segment with its corresponding regexp.
      # - If there are more path segments than regexps, ignore the extras
      #   (effectively checking the path's parent directory, which is good
      #   enough because if the parent is included, so is the child).
      # - If there are more regexps than path segments, again ignore the extras,
      #   but count matches as PARENT because this path may have children that
      #   are and/or that are not included.
      # - zip() ignores extras on either side automatically, but we have to
      #   compare the lengths if there's a match to see if it's a full match or
      #   just a PARENT.
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

  def IsIncluded(self, path):
    return self.CheckPath(path) is self.YES

  def IsParentOfIncluded(self, path):
    return self.CheckPath(path) is self.PARENT

  def IsExcluded(self, path):
    return self.CheckPath(path) is self.NO
