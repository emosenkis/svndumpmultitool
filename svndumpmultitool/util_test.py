# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Tests for util."""

from __future__ import absolute_import

import subprocess
import unittest

import mock
from svndumpmultitool import util


class PopenTest(unittest.TestCase):

  @mock.patch('subprocess.Popen')
  @mock.patch.object(util, 'LOGGER')
  def testPopen(self, logger, popen):
    # Dummy command
    cmd = ('foo', 'bar', 'baz')

    # Invoke Popen
    foo = util.Popen(*cmd, foo='foo', bar='bar')

    # Must log a message
    self.assertEquals(logger.debug.call_count, 1)
    # Must call subprocess.Popen
    popen.assert_called_once_with(cmd,
                                  stdout=subprocess.PIPE,
                                  bufsize=10240,
                                  foo='foo',
                                  bar='bar')

    # Must set .cmd on the return value
    self.assertEquals(foo.cmd, cmd)


class CheckExitCodeTest(unittest.TestCase):

  CMD = ('foo', 'bar', 'baz')

  def CreateMockSub(self, code):
    sub = mock.Mock()
    sub.cmd = self.CMD
    sub.attach_mock(mock.Mock(return_value=code), 'wait')
    return sub

  @mock.patch.object(util, 'LOGGER')
  def testSuccess(self, logger):
    sub = self.CreateMockSub(0)
    code = util.CheckExitCode(sub)
    self.assertEquals(sub.wait.call_count, 1)
    self.assertEquals(code, 0)
    self.assertEquals(logger.debug.call_count, 1)
    self.assertRegexpMatches(logger.debug.call_args[0][0], r'^Finished')

  @mock.patch.object(util, 'LOGGER')
  def testSuccessWhenFailureIsAllowed(self, logger):
    sub = self.CreateMockSub(0)
    code = util.CheckExitCode(sub, allow_failure=True)
    self.assertEquals(sub.wait.call_count, 1)
    self.assertEquals(code, 0)
    self.assertEquals(logger.debug.call_count, 1)
    self.assertRegexpMatches(logger.debug.call_args[0][0], r'^Finished')

  def testFailureWhenFailureIsNotAllowed(self):
    sub = self.CreateMockSub(1)
    with self.assertRaises(subprocess.CalledProcessError):
      util.CheckExitCode(sub)
    self.assertEquals(sub.wait.call_count, 1)

  @mock.patch.object(util, 'LOGGER')
  def testFailureWhenFailureIsAllowed(self, logger):
    sub = self.CreateMockSub(-1)
    code = util.CheckExitCode(sub, allow_failure=True)
    self.assertEquals(sub.wait.call_count, 1)
    self.assertEquals(code, -1)
    self.assertEquals(logger.debug.call_count, 1)
    self.assertRegexpMatches(logger.debug.call_args[0][0], r'returned non-zero')


class FileURLTest(unittest.TestCase):

  REPO = '/path/to/my repo'
  REPO_QUOTED = '/path/to/my%20repo'
  PATH = 'some/sub dir'
  PATH_QUOTED = 'some/sub%20dir'
  REV = 10

  def testRepoOnlyQuote(self):
    expect = 'file://%s' % self.REPO_QUOTED
    result = util.FileURL(self.REPO, None, None)
    self.assertEqual(expect, result)

  def testRepoOnlyNoQuote(self):
    expect = 'file://%s' % self.REPO
    result = util.FileURL(self.REPO, None, None, quote=False)
    self.assertEqual(expect, result)

  def testRepoAndPathQuote(self):
    expect = 'file://%s/%s' % (self.REPO_QUOTED, self.PATH_QUOTED)
    result = util.FileURL(self.REPO, self.PATH, None)
    self.assertEqual(expect, result)

  def testRepoAndPathNoQuote(self):
    expect = 'file://%s/%s' % (self.REPO, self.PATH)
    result = util.FileURL(self.REPO, self.PATH, None, quote=False)
    self.assertEqual(expect, result)

  def testRepoPathAndRevQuote(self):
    expect = 'file://%s/%s@%s' % (self.REPO_QUOTED, self.PATH_QUOTED, self.REV)
    result = util.FileURL(self.REPO, self.PATH, self.REV)
    self.assertEqual(expect, result)

  def testRepoAndRevQuote(self):
    expect = 'file://%s@%s' % (self.REPO_QUOTED, self.REV)
    result = util.FileURL(self.REPO, None, self.REV)
    self.assertEqual(expect, result)


class PathFilterTest(unittest.TestCase):
  def setUp(self):
    self.ip = util.PathFilter(['/foo/bar', 'zo+/bar/'])

  def testEmptyPath(self):
    """"Empty path should always be a PARENT."""
    self.assertEquals(self.ip.CheckPath(''), self.ip.PARENT)

  def testParent(self):
    self.assertEquals(self.ip.CheckPath('foo'), self.ip.PARENT)
    self.assertEquals(self.ip.CheckPath('zoo'), self.ip.PARENT)

  def testRoot(self):
    self.assertEquals(self.ip.CheckPath('foo/bar'), self.ip.YES)
    self.assertEquals(self.ip.CheckPath('zoo/bar'), self.ip.YES)

  def testChild(self):
    self.assertEquals(self.ip.CheckPath('foo/bar/baz'), self.ip.YES)
    self.assertEquals(self.ip.CheckPath('zooooooooo/bar/baz'), self.ip.YES)

  def testNoMatch(self):
    self.assertEquals(self.ip.CheckPath('goo/bar'), self.ip.NO)
    self.assertEquals(self.ip.CheckPath('fooz/bar'), self.ip.NO)
    self.assertEquals(self.ip.CheckPath('foo/barz'), self.ip.NO)
    self.assertEquals(self.ip.CheckPath('zoooom/bar'), self.ip.NO)

  def testNoIncludes(self):
    """No includes means include everything."""
    ip = util.PathFilter([])
    self.assertEquals(ip.CheckPath(''), ip.YES)
    self.assertEquals(ip.CheckPath('foo'), ip.YES)
    self.assertEquals(ip.CheckPath('foo/bar'), ip.YES)


if __name__ == '__main__':
  unittest.main()
