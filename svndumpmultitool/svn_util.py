# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Utility functions that call out to SVN command-line tools."""

from __future__ import absolute_import

import logging
import urllib

from svndumpmultitool import util

LOGGER = logging.getLogger(__name__)


class Error(Exception):
  """Parent class for this module's errors."""


class UnknownDiff(Error):
  """svn diff includes an unrecognized action."""


def ExtractNodeKinds(srcrepo, srcrev, srcpath):
  """Creates a mapping of path to kind (dir or file).

  Args:
    srcrepo: repository path
    srcrev: revision number
    srcpath: path within repository

  Returns:
    a dict whose keys are the paths of all files and directories under the
    given path and whose values are 'dir' for directories and 'file' for files

  This information is necessary to construct new Records relating to paths in
  the repository to fill the Node-kind header. Unfortunately, this information
  does not seem to be available from Subversion any other way.
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
  svnlook_tree = util.Popen(*cmd)
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
  util.CheckExitCode(svnlook_tree)
  return nodes


def Diff(repo, oldpath, oldrev, newpath, newrev):
  """Figure out what changed between two revisions of a directory.

  Args:
    repo: absolute path of the SVN repo
    oldpath: path within the repository to diff from
    oldrev: revision number to diff from
    newpath: path within the repository to diff to
    newrev: revision number to diff to

  Returns:
    a dict of {str: (str, str)}.
    The keys are paths relative to input paths that have changed.
    The first part of the value is the type of change that was done to the
    contents of the path ('add', 'modify', 'delete', or None).
    The second part of the value is the type of change that was done to the
    properties of the path ('modify' or None).

  Raises:
    UnknownDiff: if an operation is encountered that is not recognized

  If a parent and child path are both deleted, only the parent will be included
  in the output. Only paths for which the contents or properties have changed
  will be returned.
  """
  # This prefix will be stripped off the beginning of each path. The portion
  # after file:// must be %-quoted, but file:// would turn into file%3A// if
  # quoted. We strip the unquoted version, so here we just take the length so we
  # know how much to strip off.
  prefix_len = 1 + len(  # Add 1 for trailing /
      util.FileURL(repo, oldpath, None, quote=False))
  contents_ops = {' ': None, 'A': 'add', 'M': 'modify', 'D': 'delete'}
  props_ops = {' ': None, 'M': 'modify'}
  svn_diff = util.Popen('svn',
                        'diff',
                        '--summarize',
                        '--old=' + util.FileURL(repo, oldpath, oldrev),
                        '--new=' + util.FileURL(repo, newpath, newrev))
  deleted = {}
  changes = {}
  with svn_diff.stdout as diff_stream:
    for line in diff_stream:
      line = line.rstrip('\n')

      if line[0] not in contents_ops:
        raise UnknownDiff('Unknown contents operation "%s" in svn diff'
                          % line[0])
      if line[1] not in props_ops:
        raise UnknownDiff('Unknown properties operation "%s" in svn diff'
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

  util.CheckExitCode(svn_diff)

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
