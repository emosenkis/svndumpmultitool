# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Tests for svn_util."""

from __future__ import absolute_import

import subprocess
import unittest

import mock

from svndumpmultitool import svn_util
from svndumpmultitool import test_utils

# Static data
MAIN_REPO = '/svn/zoo'
MAIN_REPO_REV = 5


@mock.patch('subprocess.Popen', new=test_utils.MockPopen)
class ExtractNodeKindsTest(unittest.TestCase):
  def testDir(self):
    with test_utils.MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'tree', '--full-paths', '-r%s' % MAIN_REPO_REV,
                MAIN_REPO, 'foo'),
        'stdout': ('foo/\n'
                   'foo/dir1/\n'
                   'foo/dir1/file1\n'
                   'foo/dir1/file2\n'
                   'foo/dir2/\n'
                   'foo/file3\n\n'),
        }):
      result = svn_util.ExtractNodeKinds(MAIN_REPO, MAIN_REPO_REV, 'foo')
    expected = {
        '': 'dir',
        'dir1': 'dir',
        'dir1/file1': 'file',
        'dir1/file2': 'file',
        'dir2': 'dir',
        'file3': 'file'
        }
    self.assertEqual(result, expected)

  def testFile(self):
    with test_utils.MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'tree', '--full-paths', '-r%s' % MAIN_REPO_REV,
                MAIN_REPO, 'foo'),
        'stdout': 'foo\n'
        }):
      result = svn_util.ExtractNodeKinds(MAIN_REPO, MAIN_REPO_REV, 'foo')
    self.assertEqual(result, {'': 'file'})

  def testFails(self):
    with self.assertRaises(subprocess.CalledProcessError):
      with test_utils.MockPopen.ExpectCommands({
          'cmd': ('svnlook', 'tree', '--full-paths', '-r%s' % MAIN_REPO_REV,
                  MAIN_REPO, 'foo'),
          'stdout': 'foo\n',
          'returncode': 1
          }):
        svn_util.ExtractNodeKinds(MAIN_REPO, MAIN_REPO_REV, 'foo')


@mock.patch('subprocess.Popen', new=test_utils.MockPopen)
class DiffTest(unittest.TestCase):
  def testNormal(self):
    with test_utils.MockPopen.ExpectCommands({
        'cmd': ('svn', 'diff', '--summarize',
                '--old=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV - 1),
                '--new=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV)),
        'stdout': ('A   file://' + MAIN_REPO + '/foo/added\n'
                   'M   file://' + MAIN_REPO + '/foo/contents-changed\n'
                   ' M  file://' + MAIN_REPO + '/foo/props-changed\n'
                   'MM  file://' + MAIN_REPO + '/foo/both-changed\n'
                   'D   file://' + MAIN_REPO + '/foo/deleted-dir\n'
                   'D   file://' + MAIN_REPO + '/foo/deleted-dir/file\n'
                   'D   file://' + MAIN_REPO + '/foo/dir/deleted\n')
        }):
      results = svn_util.Diff(MAIN_REPO,
                              'foo', MAIN_REPO_REV - 1,
                              'foo', MAIN_REPO_REV)
    expected = {
        'added': ('add', None),
        'contents-changed': ('modify', None),
        'props-changed': (None, 'modify'),
        'both-changed': ('modify', 'modify'),
        'deleted-dir': ('delete', None),
        'dir/deleted': ('delete', None),
        }
    self.assertEqual(results, expected)

  def testBadContentsOp(self):
    with test_utils.MockPopen.ExpectCommands({
        'cmd': ('svn', 'diff', '--summarize',
                '--old=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV - 1),
                '--new=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV)),
        'stdout': 'X  file://' + MAIN_REPO + '/foo/unknown\n'
        }), self.assertRaises(svn_util.UnknownDiff):
      svn_util.Diff(MAIN_REPO,
                    'foo', MAIN_REPO_REV - 1,
                    'foo', MAIN_REPO_REV)

  def testBadPropsOp(self):
    with test_utils.MockPopen.ExpectCommands({
        'cmd': ('svn', 'diff', '--summarize',
                '--old=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV - 1),
                '--new=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV)),
        'stdout': ' X file://' + MAIN_REPO + '/foo/unknown\n'
        }), self.assertRaises(svn_util.UnknownDiff):
      svn_util.Diff(MAIN_REPO,
                    'foo', MAIN_REPO_REV - 1,
                    'foo', MAIN_REPO_REV)


if __name__ == '__main__':
  unittest.main()
