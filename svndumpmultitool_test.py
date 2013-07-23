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

"""Tests for svndumpmultitool."""


import collections
import contextlib
import io
import StringIO
import subprocess
import unittest

import mock
import svndumpmultitool

# Static data
MAIN_REPO = '/svn/zoo'
MAIN_REPO_REV = 5
PARENT_DIR = 'trunk/proj'
EXTERNALS_MAP = {
    'http://svn.foo.com/foo': '/svn/foo',
    'file:///svn/foo': '/svn/foo',
    'svn+ssh://svn.foo.com/bar': '/svn/bar',
    'file:///svn/bar': '/svn/bar',
    'http://svn.foo.com/zoo': '/svn/zoo',
    'file:///svn/zoo': '/svn/zoo',
    }


class MockPopen(object):
  """Mock class for replacing subprocess.Popen.

  Example:
    @mock.patch('svndumpmultitool.subprocess.Popen', new=MockPopen)
    def testDeleteEverything(self):
      with MockPopen.ExpectCommands({
          'cmd': ('rm', '-rf', '/'),
          'stdout': 'Now erasing your files...done'
          }):
        mymodule.DeleteEverything()
  """

  _expected_commands = None
  _finished_commands = None
  _in_test = False

  def __init__(self, cmd, stdout=None, stderr=None, bufsize=None):
    """Called when code under test instantiates Popen."""
    # Make sure 'with MockPopen.ExpectCommands():' is being used.
    assert self._in_test, ('MockPopen instantiated without '
                           "'with MockPopen.ExpectCommands():'")

    try:
      # Find out what command is expected next and how it should behave.
      expected = self._expected_commands.pop()
    except IndexError:
      raise AssertionError('No commands expected but got %s' % cmd)

    assert cmd == expected['cmd'], ('Expected command %s, got %s'
                                    % (expected['cmd'], cmd))
    self._cmd = expected['cmd']

    # If Popen was called with stdout or stderr set to subprocess.PIPE, the code
    # expects to read from the subprocess's stdout or stderr. MockPopen provides
    # these by wrapping the strings provided by the test with BytesIO.
    if stdout is subprocess.PIPE:
      try:
        self.stdout = self._AssertingStream(expected['stdout'])
      except IndexError:
        raise AssertionError('Popen was called with stdout=subprocess.PIPE but'
                             ' test did not provide stdout')
    else:
      self.stdout = None
      assert 'stdout' not in expected, ('Test provided stdout but Popen was'
                                        ' called without'
                                        ' stdout=subprocess.PIPE')
    if stderr is subprocess.PIPE:
      try:
        self.stderr = self._AssertingStream(expected['stderr'])
      except IndexError:
        raise AssertionError('Popen was called with stderr=subprocess.PIPE but'
                             ' test did not provide stderr')
    else:
      self.stderr = None
      assert 'stderr' not in expected, ('Test provided stderr but Popen was'
                                        ' called without'
                                        ' stderr=subprocess.PIPE')
    self._returncode = expected.get('returncode', 0)

    self._finished_commands.append(self)

  @classmethod
  @contextlib.contextmanager
  def ExpectCommands(cls, *cmds):
    """Run test code, mocking out use of subprocess.Popen with MockPopen.

    Args:
      *cmds: the commands expected by the test to be run, in the forms of dicts
             with the following fields:
             'cmd': the exact command Popen will be called with
             'stdout': a string that will be converted to a stream and returned
                       as the stdout of the subprocess
             'stderr': like stdout
             'returncode': the code that the subprocess will return when wait()
                          is called

             stdout and stderr must be provided if and only if the code being
             tested requests them to be piped by passing subprocess.PIPE as the
             stdout and/or stderr keyword arguments to Popen.

    Yields:
      nothing; yield is used by the contextmanager decorator to turn a function
      into a context manager.


    See MockPopen for an example.
    """
    assert not cls._in_test, 'MockPopen.ExpectCommands can not be nested.'
    cls._expected_commands = list(reversed(cmds))
    cls._finished_commands = []
    cls._in_test = True
    try:
      yield  # Test runs here
      cls._AssertAllCommandsWereRunProperly()
    finally:
      cls._in_test = False
      cls._expected_commands = None
      cls._finished_commands = None

  def wait(self):
    return self._returncode

  @classmethod
  def _AssertAllCommandsWereRunProperly(cls):
    """Asserts that must be run after the test code.

    Verifies that each command's output streams were closed and all expected
    commands were run.
    """
    # stdout and stderr must be closed
    for cmd in cls._finished_commands:
      assert not cmd.stdout or cmd.stdout.closed, ('stdout was not closed for'
                                                   ' command: %s' % (cmd._cmd,))
      assert not cmd.stderr or cmd.stderr.closed, ('stderr was not closed for'
                                                   ' command: %s' % (cmd._cmd,))
    # all commands expected must have been run
    leftovers = [cmd['cmd'] for cmd in cls._expected_commands]
    assert not leftovers, 'Expected command(s) never executed: %s' % leftovers

  class _AssertingStream(io.BytesIO):
    def close(self):
      assert not self.read(), 'All stream output must be read before close()'
      io.BytesIO.close(self)


def ExternalsDescriptionFromDefaults(dstpath='baz', srcrepo='/svn/foo',
                                     srcrev=None, srcpath='baz', srcpeg=None):
  """Helper for creating ExternalsDescriptions with defaults for all fields."""
  return svndumpmultitool.ExternalsDescription(dstpath, srcrepo, srcrev,
                                               srcpath, srcpeg)


class PopenTest(unittest.TestCase):

  @mock.patch('svndumpmultitool.subprocess.Popen')
  @mock.patch('svndumpmultitool.LOGGER')
  def testPopen(self, logger, popen):
    # Dummy command
    cmd = ('foo', 'bar', 'baz')

    # Invoke Popen
    foo = svndumpmultitool.Popen(*cmd, foo='foo', bar='bar')

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

  @mock.patch('svndumpmultitool.LOGGER')
  def testSuccess(self, logger):
    sub = self.CreateMockSub(0)
    code = svndumpmultitool.CheckExitCode(sub)
    self.assertEquals(sub.wait.call_count, 1)
    self.assertEquals(code, 0)
    self.assertEquals(logger.debug.call_count, 1)
    self.assertRegexpMatches(logger.debug.call_args[0][0], r'^Finished')

  @mock.patch('svndumpmultitool.LOGGER')
  def testSuccessWhenFailureIsAllowed(self, logger):
    sub = self.CreateMockSub(0)
    code = svndumpmultitool.CheckExitCode(sub, allow_failure=True)
    self.assertEquals(sub.wait.call_count, 1)
    self.assertEquals(code, 0)
    self.assertEquals(logger.debug.call_count, 1)
    self.assertRegexpMatches(logger.debug.call_args[0][0], r'^Finished')

  def testFailureWhenFailureIsNotAllowed(self):
    sub = self.CreateMockSub(1)
    with self.assertRaises(subprocess.CalledProcessError):
      svndumpmultitool.CheckExitCode(sub)
    self.assertEquals(sub.wait.call_count, 1)

  @mock.patch('svndumpmultitool.LOGGER')
  def testFailureWhenFailureIsAllowed(self, logger):
    sub = self.CreateMockSub(-1)
    code = svndumpmultitool.CheckExitCode(sub, allow_failure=True)
    self.assertEquals(sub.wait.call_count, 1)
    self.assertEquals(code, -1)
    self.assertEquals(logger.debug.call_count, 1)
    self.assertRegexpMatches(logger.debug.call_args[0][0], r'returned non-zero')


class ExternalsDescriptionConstructorTest(unittest.TestCase):
  """Tests all combinations of rev and head (int, HEAD, None)."""

  def testRevHeadPegHead(self):
    ed = ExternalsDescriptionFromDefaults(srcrev='head', srcpeg='HEAD')
    self.assertIsNone(ed.srcrev)
    self.assertIsNone(ed.srcpeg)

  def testRevHeadPegInt(self):
    """rev=HEAD should not trigger default behavior of copying peg."""
    ed = ExternalsDescriptionFromDefaults(srcrev='head', srcpeg=5)
    self.assertIsNone(ed.srcrev)
    self.assertEquals(ed.srcpeg, 5)

  def testRevHeadPegNone(self):
    ed = ExternalsDescriptionFromDefaults(srcrev='heAd', srcpeg=None)
    self.assertIsNone(ed.srcrev)
    self.assertIsNone(ed.srcpeg)

  def testRevIntPegHead(self):
    ed = ExternalsDescriptionFromDefaults(srcrev=10, srcpeg='head')
    self.assertEquals(ed.srcrev, 10)
    self.assertIsNone(ed.srcpeg)

  def testRevIntPegInt(self):
    ed = ExternalsDescriptionFromDefaults(srcrev=10, srcpeg=5)
    self.assertEquals(ed.srcrev, 10)
    self.assertEquals(ed.srcpeg, 5)

  def testRevIntPegNone(self):
    """Peg should not default to rev."""
    ed = ExternalsDescriptionFromDefaults(srcrev=10, srcpeg=None)
    self.assertEquals(ed.srcrev, 10)
    self.assertIsNone(ed.srcpeg)

  def testRevNonePegHead(self):
    ed = ExternalsDescriptionFromDefaults(srcrev=None, srcpeg='HEAD')
    self.assertIsNone(ed.srcrev)
    self.assertIsNone(ed.srcpeg)

  def testRevNonePegInt(self):
    """Rev should default to peg."""
    ed = ExternalsDescriptionFromDefaults(srcrev=None, srcpeg=5)
    self.assertEquals(ed.srcrev, 5)
    self.assertEquals(ed.srcpeg, 5)

  def testRevNonePegNone(self):
    ed = ExternalsDescriptionFromDefaults(srcrev=None, srcpeg=None)
    self.assertIsNone(ed.srcrev)
    self.assertIsNone(ed.srcpeg)

  def testRevInvalid(self):
    with self.assertRaises(ValueError):
      ExternalsDescriptionFromDefaults(srcrev='FOO')

  def testPegInvalid(self):
    with self.assertRaises(ValueError):
      ExternalsDescriptionFromDefaults(srcpeg='-1')

  def testRevAndPegInvalid(self):
    with self.assertRaises(ValueError):
      ExternalsDescriptionFromDefaults(srcrev='-1', srcpeg='FOO')


class ExternalsDescriptionSanitizeRevTest(unittest.TestCase):
  """Tests that revision numbers are sanitized properly."""

  def testIntAsString(self):
    """String representation of int should be converted to int."""
    self.assertEqual(svndumpmultitool.ExternalsDescription._SanitizeRev('1'), 1)

  def testInt(self):
    """int should stay the same."""
    self.assertEqual(svndumpmultitool.ExternalsDescription._SanitizeRev(100),
                     100)

  def testHEAD(self):
    """HEAD (case-insensitive) should become None."""
    self.assertEqual(svndumpmultitool.ExternalsDescription._SanitizeRev('hEaD'),
                     None)

  def testNone(self):
    """None should stay the same."""
    self.assertEqual(svndumpmultitool.ExternalsDescription._SanitizeRev(None),
                     None)

  def testNegativeInt(self):
    """Negative int should raise ValueError."""
    with self.assertRaises(ValueError):
      svndumpmultitool.ExternalsDescription._SanitizeRev(-1)

  def testNegativeIntAsString(self):
    """String representation of negative int should raise ValueError."""
    with self.assertRaises(ValueError):
      svndumpmultitool.ExternalsDescription._SanitizeRev('-1')

  def testNonIntegerString(self):
    """Non-integer string should raise ValueError."""
    with self.assertRaises(ValueError):
      svndumpmultitool.ExternalsDescription._SanitizeRev('1.0')


@mock.patch('svndumpmultitool.subprocess.Popen', new=MockPopen)
class ExternalsDescriptionSourceExistsTest(unittest.TestCase):
  def testExists(self):
    with MockPopen.ExpectCommands({
        'cmd': ('svn', 'ls', 'file:///svn/foo/baz@1'),
        'stdout': 'some output',
        'stderr': ''
        }):
      ed = ExternalsDescriptionFromDefaults(srcrev=1)
      self.assertEquals(ed.SourceExists(), True)

  @mock.patch('svndumpmultitool.LOGGER')
  def testDoesNotExist(self, logger):
    with MockPopen.ExpectCommands({
        'cmd': ('svn', 'ls', 'file:///svn/foo/baz@1'),
        'stdout': '',
        'stderr': 'error!',
        'returncode': 1
        }):
      ed = ExternalsDescriptionFromDefaults(srcrev=1)
      self.assertEquals(ed.SourceExists(), False)
      self.assertEquals(logger.warning.call_count, 1)


class ExternalsDescriptionDiffTest(unittest.TestCase):
  def testDiff(self):
    """Test that Diff produces the correct results."""
    old = {}
    new = {}
    # Change repo (delete, add)
    old['delete_and_add'] = svndumpmultitool.ExternalsDescription(
        'delete_and_add', '/usr/local/repos/myrepo', 1080, 'bar/dst1', 1000)
    new['delete_and_add'] = svndumpmultitool.ExternalsDescription(
        'delete_and_add', '/usr/local/repos/newrepo', 1080, 'bar/dst1', 1000)
    # Change rev (change)
    old['changed_rev'] = svndumpmultitool.ExternalsDescription(
        'changed_rev', '/usr/local/repos/myrepo', 1080, 'bar/dst2', 1000)
    new['changed_rev'] = svndumpmultitool.ExternalsDescription(
        'changed_rev', '/usr/local/repos/myrepo', 1090, 'bar/dst2', 1000)
    # Changes dst (change)
    old['changed_dst'] = svndumpmultitool.ExternalsDescription(
        'changed_dst', '/usr/local/repos/myrepo', 1080, 'bar/dst3', 1000)
    new['changed_dst'] = svndumpmultitool.ExternalsDescription(
        'changed_dst', '/usr/local/repos/myrepo', 1080, 'bar/dst3a', 1000)
    # Changes peg (noop)
    old['peg_change_noop'] = svndumpmultitool.ExternalsDescription(
        'peg_change_noop', '/usr/local/repos/myrepo', 1080, 'bar/dst4', 1000)
    new['peg_change_noop'] = svndumpmultitool.ExternalsDescription(
        'peg_change_noop', '/usr/local/repos/myrepo', 1080, 'bar/dst4', 2000)
    # Deletes deleted, adds added
    old['deleted'] = svndumpmultitool.ExternalsDescription(
        'deleted', '/usr/local/repos/myrepo', 1080, 'bar/dst5', 1000)
    new['added'] = svndumpmultitool.ExternalsDescription(
        'added', '/usr/local/repos/myrepo', 1080, 'bar/dst6', 2000)

    # Let's establish some expectations
    expected_adds = [new['delete_and_add'], new['added']]
    expected_changes = [(old['changed_rev'], new['changed_rev']),
                        (old['changed_dst'], new['changed_dst'])]
    expected_deletes = ['delete_and_add', 'deleted']

    # Actually exercise the code
    added, changed, deleted = svndumpmultitool.ExternalsDescription.Diff(old,
                                                                         new)

    self.assertItemsEqual(expected_adds, added)
    self.assertItemsEqual(expected_changes, changed)
    self.assertItemsEqual(expected_deletes, deleted)


class ExternalsDescriptionReprTest(unittest.TestCase):
  def testSimple(self):
    ed = ExternalsDescriptionFromDefaults()
    result = repr(ed)
    self.assertEquals(result,
                      'ExternalsDescription(\'baz\', \'/svn/foo\', None,'
                      ' \'baz\', None)')


class ExternalsDescriptionParseTest(unittest.TestCase):

  def Parse(self, description, externals_map=True):
    return svndumpmultitool.ExternalsDescription.Parse(
        MAIN_REPO,
        MAIN_REPO_REV,
        PARENT_DIR,
        description,
        EXTERNALS_MAP if externals_map else None
        )

  @mock.patch('svndumpmultitool.ExternalsDescription.SourceExists')
  def testSimple(self, _):
    result = self.Parse('http://svn.foo.com/foo/baz baz')
    expected = {'baz': ExternalsDescriptionFromDefaults()}
    self.assertEquals(result, expected)

  @mock.patch('svndumpmultitool.ExternalsDescription.SourceExists')
  def testComments(self, _):
    result = self.Parse('#foo\nhttp://svn.foo.com/foo/baz baz')
    expected = {'baz': ExternalsDescriptionFromDefaults()}
    self.assertEquals(result, expected)

  @mock.patch('svndumpmultitool.ExternalsDescription.SourceExists')
  def testBlankLines(self, _):
    result = self.Parse('\n \t \nhttp://svn.foo.com/foo/baz baz\n\n')
    expected = {'baz': ExternalsDescriptionFromDefaults()}
    self.assertEquals(result, expected)

  @mock.patch('svndumpmultitool.ExternalsDescription.SourceExists')
  def testMultiple(self, _):
    result = self.Parse('http://svn.foo.com/foo/baz baz\n'
                        'http://svn.foo.com/foo/boo boo')
    expected = {
        'baz': ExternalsDescriptionFromDefaults(),
        'boo': ExternalsDescriptionFromDefaults(dstpath='boo', srcpath='boo')
        }
    self.assertEquals(result, expected)

  @mock.patch('svndumpmultitool.ExternalsDescription.SourceExists')
  def testSourceDoesNotExist(self, source_exists):
    source_exists.return_value = False
    result = self.Parse('http://svn.foo.com/foo/baz baz')
    self.assertEquals(result, {})

  @mock.patch('svndumpmultitool.ExternalsDescription.SourceExists')
  def testNoExternalsMap(self, _):
    result = self.Parse('../include/bar bar', externals_map=False)
    expected = {
        'bar': svndumpmultitool.ExternalsDescription(
            'bar', MAIN_REPO, MAIN_REPO_REV - 1, PARENT_DIR + '/include/bar',
            MAIN_REPO_REV - 1)
        }
    self.assertEquals(result, expected)


class ExternalsDescriptionParseLineTest(unittest.TestCase):
  def ParseLine(self, line):
    return svndumpmultitool.ExternalsDescription.ParseLine(
        MAIN_REPO,
        MAIN_REPO_REV,
        PARENT_DIR,
        line,
        EXTERNALS_MAP
        )

  # The following test cases exercise parsing of the six different allowed
  # formats of externals allowed by SVN. They are named after the numbers
  # assigned to them in the docstring for ExternalsDescription.Parse.
  def testFormat1Simple(self):
    result = self.ParseLine('baz http://svn.foo.com/foo/baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat1Pegged(self):
    """Peg revisions not allowed in Format 1."""
    result = self.ParseLine('baz http://svn.foo.com/foo/baz@1')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz@1', None)
    self.assertEquals(result, expected)

  def testFormat2Int(self):
    result = self.ParseLine('baz -r 5 http://svn.foo.com/foo/baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat2Head(self):
    result = self.ParseLine('baz -r HEAD http://svn.foo.com/foo/baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat2Invalid(self):
    result = self.ParseLine('baz -r FOO http://svn.foo.com/foo/baz')
    self.assertIsNone(result)

  def testFormat2Pegged(self):
    """Peg revisions not allowed in Format 2."""
    result = self.ParseLine('baz -r 5 http://svn.foo.com/foo/baz@1')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz@1', 5)
    self.assertEquals(result, expected)

  def testFormat3Int(self):
    result = self.ParseLine('baz -r5 http://svn.foo.com/foo/baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat3Head(self):
    result = self.ParseLine('baz -r HEAD http://svn.foo.com/foo/baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat3Invalid(self):
    result = self.ParseLine('baz -rFOO http://svn.foo.com/foo/baz')
    self.assertIsNone(result)

  def testFormat3Pegged(self):
    """Peg revisions not allowed in Format 3."""
    result = self.ParseLine('baz -r5 http://svn.foo.com/foo/baz@1')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz@1', 5)
    self.assertEquals(result, expected)

  def testFormat4Simple(self):
    result = self.ParseLine('http://svn.foo.com/foo/baz baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat4Int(self):
    result = self.ParseLine('http://svn.foo.com/foo/baz@5 baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat4Head(self):
    result = self.ParseLine('http://svn.foo.com/foo/baz@HeAd baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat4Invalid(self):
    result = self.ParseLine('http://svn.foo.com/foo/baz@FOO baz')
    self.assertIsNone(result)

  def testFormat5Simple(self):
    result = self.ParseLine('-r 10 http://svn.foo.com/foo/baz baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 10, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat5RevIntPegInt(self):
    result = self.ParseLine('-r 10 http://svn.foo.com/foo/baz@5 baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 10, 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat5RevHeadPegInt(self):
    result = self.ParseLine('-r HEAD http://svn.foo.com/foo/baz@5 baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 'HEAD', 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat5RevIntPegHead(self):
    result = self.ParseLine('-r 5 http://svn.foo.com/foo/baz@HeAD baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat5RevHeadPegHead(self):
    result = self.ParseLine('-r HEAD http://svn.foo.com/foo/baz@head baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat6Simple(self):
    result = self.ParseLine('-r10 http://svn.foo.com/foo/baz baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 10, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat6RevIntPegInt(self):
    result = self.ParseLine('-r10 http://svn.foo.com/foo/baz@6 baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 10, 'baz', 6)
    self.assertEquals(result, expected)

  def testFormat6RevHeadPegInt(self):
    result = self.ParseLine('-rHEAD http://svn.foo.com/foo/baz@6 baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 'HEAD', 'baz', 6)
    self.assertEquals(result, expected)

  def testFormat6RevIntPegHead(self):
    result = self.ParseLine('-r6 http://svn.foo.com/foo/baz@HeAD baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', 6, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat6RevHeadPegHead(self):
    result = self.ParseLine('-rHEAD http://svn.foo.com/foo/baz@head baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  # The following test cases test that the current revision number - 1 is
  # substituted for HEAD for both the operant and peg revisions.
  def testRevSubstitutionBoth(self):
    result = self.ParseLine('baz http://svn.foo.com/zoo/baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', MAIN_REPO, MAIN_REPO_REV - 1, 'baz', MAIN_REPO_REV - 1)
    self.assertEquals(result, expected)

  def testRevSubstitutionRev(self):
    result = self.ParseLine('-r2 http://svn.foo.com/zoo/baz baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', MAIN_REPO, 2, 'baz', MAIN_REPO_REV - 1)
    self.assertEquals(result, expected)

  def testRevSubstitutionPeg(self):
    result = self.ParseLine('-rHEAD http://svn.foo.com/zoo/baz@2 baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', MAIN_REPO, MAIN_REPO_REV - 1, 'baz', 2)
    self.assertEquals(result, expected)

  def testRevSubstitutionNeither(self):
    result = self.ParseLine('-r1 http://svn.foo.com/zoo/baz@2 baz')
    expected = svndumpmultitool.ExternalsDescription(
        'baz', MAIN_REPO, 1, 'baz', 2)
    self.assertEquals(result, expected)

  # Tests for new format relative URLs
  def testRepoRootRelativeSameRepo(self):
    result = self.ParseLine('^/trunk/bar bar')
    expected = svndumpmultitool.ExternalsDescription(
        'bar', MAIN_REPO, MAIN_REPO_REV - 1, 'trunk/bar', MAIN_REPO_REV - 1)
    self.assertEquals(result, expected)

  def testRepoRootRelativeNewRepo(self):
    result = self.ParseLine('^/../foo/trunk/bar bar')
    expected = svndumpmultitool.ExternalsDescription(
        'bar', '/svn/foo', None, 'trunk/bar', None)
    self.assertEquals(result, expected)

  @mock.patch('svndumpmultitool.LOGGER')
  def testRepoRootRelativeAboveFilesystemRoot(self, logger):
    result = self.ParseLine('^/../../../foo/trunk/bar bar')
    self.assertIsNone(result)
    self.assertEquals(logger.warning.call_count, 1)
    self.assertRegexpMatches(logger.warning.call_args[0][0],
                             r'above filesystem root')

  def testPegRelative(self):
    result = self.ParseLine('../baz bar')
    expected = svndumpmultitool.ExternalsDescription(
        'bar', MAIN_REPO, MAIN_REPO_REV - 1, PARENT_DIR + '/baz',
        MAIN_REPO_REV - 1)
    self.assertEquals(result, expected)

  @mock.patch('svndumpmultitool.LOGGER')
  def testSchemeRelative(self, logger):
    result = self.ParseLine('//foo.com/bar bar')
    self.assertIsNone(result)
    self.assertEquals(logger.warning.call_count, 1)
    self.assertRegexpMatches(logger.warning.call_args[0][0], r'scheme-relative')

  @mock.patch('svndumpmultitool.LOGGER')
  def testServerRootRelative(self, logger):
    result = self.ParseLine('/svn/bar bar')
    self.assertIsNone(result)
    self.assertEquals(logger.warning.call_count, 1)
    self.assertRegexpMatches(logger.warning.call_args[0][0], r'server-relative')

  # Tests for cases that should fail
  @mock.patch('svndumpmultitool.LOGGER')
  def testUnmappableExternal(self, logger):
    result = self.ParseLine('http://fake-domain.com fake')
    self.assertIsNone(result)
    self.assertEquals(logger.warning.call_count, 1)
    self.assertRegexpMatches(logger.warning.call_args[0][0], r'^Failed to map')

  @mock.patch('svndumpmultitool.LOGGER')
  def testTooFewParts(self, logger):
    result = self.ParseLine('bar')
    self.assertIsNone(result)
    self.assertEquals(logger.warning.call_count, 1)
    self.assertRegexpMatches(logger.warning.call_args[0][0], r'^Unparseable')

  @mock.patch('svndumpmultitool.LOGGER')
  def testTooManyParts(self, logger):
    result = self.ParseLine('-r 5 http://svn/foo bar @5')
    self.assertIsNone(result)
    self.assertEquals(logger.warning.call_count, 1)
    self.assertRegexpMatches(logger.warning.call_args[0][0], r'^Unparseable')


class ExternalsDescriptionFindExternalPathTest(unittest.TestCase):
  def testSimple(self):
    repo, path = svndumpmultitool.ExternalsDescription.FindExternalPath(
        'http://svn.foo.com/foo/trunk/bar',
        EXTERNALS_MAP)
    self.assertEquals(repo, '/svn/foo')
    self.assertEquals(path, 'trunk/bar')

  def testRepoRoot(self):
    repo, path = svndumpmultitool.ExternalsDescription.FindExternalPath(
        'http://svn.foo.com/foo',
        EXTERNALS_MAP)
    self.assertEquals(repo, '/svn/foo')
    self.assertEquals(path, '')

  def testNotFound(self):
    repo, path = svndumpmultitool.ExternalsDescription.FindExternalPath(
        'http://svn.bar.com/foo',
        EXTERNALS_MAP)
    self.assertIsNone(repo)
    self.assertIsNone(path)


@mock.patch('svndumpmultitool.subprocess.Popen', new=MockPopen)
class ExternalsDescriptionFromRevTest(unittest.TestCase):
  def testSVNFails(self):
    with MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'propget', '-r10', MAIN_REPO, 'svn:externals',
                'trunk/foo'),
        'returncode': 1,
        'stdout': 'Bad stdout',
        }):
      result = svndumpmultitool.ExternalsDescription.FromRev(
          MAIN_REPO, 10, 'trunk/foo', EXTERNALS_MAP)
    self.assertEquals(result, {})

  # Don't make external calls to verify that the source exists
  @mock.patch('svndumpmultitool.ExternalsDescription.SourceExists')
  def testSucceeds(self, _):
    externals_property = 'http://svn.foo.com/foo/baz baz'
    with MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'propget', '-r10', MAIN_REPO, 'svn:externals',
                'trunk/foo'),
        'stdout': externals_property
        }):
      result = svndumpmultitool.ExternalsDescription.FromRev(
          MAIN_REPO, 10, 'trunk/foo', EXTERNALS_MAP)
    expected = {
        'baz': svndumpmultitool.ExternalsDescription(
            'baz', '/svn/foo', None, 'baz', None)
        }
    self.assertEquals(result, expected)


class InterestingPathsTest(unittest.TestCase):
  def setUp(self):
    self.ip = svndumpmultitool.InterestingPaths(['/foo/bar', 'zo+/bar/'])

  def testEmptyPath(self):
    """"Empty path should always be a PARENT."""
    self.assertEquals(self.ip.Interesting(''), self.ip.PARENT)

  def testParent(self):
    self.assertEquals(self.ip.Interesting('foo'), self.ip.PARENT)
    self.assertEquals(self.ip.Interesting('zoo'), self.ip.PARENT)

  def testRoot(self):
    self.assertEquals(self.ip.Interesting('foo/bar'), self.ip.YES)
    self.assertEquals(self.ip.Interesting('zoo/bar'), self.ip.YES)

  def testChild(self):
    self.assertEquals(self.ip.Interesting('foo/bar/baz'), self.ip.YES)
    self.assertEquals(self.ip.Interesting('zooooooooo/bar/baz'), self.ip.YES)

  def testNoMatch(self):
    self.assertEquals(self.ip.Interesting('goo/bar'), self.ip.NO)
    self.assertEquals(self.ip.Interesting('fooz/bar'), self.ip.NO)
    self.assertEquals(self.ip.Interesting('foo/barz'), self.ip.NO)
    self.assertEquals(self.ip.Interesting('zoooom/bar'), self.ip.NO)

  def testNoIncludes(self):
    """No includes means include everything."""
    ip = svndumpmultitool.InterestingPaths([])
    self.assertEquals(ip.Interesting(''), ip.YES)
    self.assertEquals(ip.Interesting('foo'), ip.YES)
    self.assertEquals(ip.Interesting('foo/bar'), ip.YES)


class LumpConstructorTest(unittest.TestCase):
  def testSimple(self):
    lump = svndumpmultitool.Lump()
    self.assertFalse(lump.headers)
    self.assertIsNone(lump.props)
    self.assertIsNone(lump.text)
    self.assertIs(lump.source, lump.DUMP)

  def testPath(self):
    lump = svndumpmultitool.Lump(path='foo')
    self.assertEqual(lump.headers['Node-path'], 'foo')
    self.assertEqual(len(lump.headers), 1)
    self.assertIsNone(lump.props)
    self.assertIsNone(lump.text)

  def testAction(self):
    lump = svndumpmultitool.Lump(action='foo')
    self.assertEqual(lump.headers['Node-action'], 'foo')
    self.assertEqual(len(lump.headers), 1)
    self.assertIsNone(lump.props)
    self.assertIsNone(lump.text)

  def testKind(self):
    lump = svndumpmultitool.Lump(kind='foo')
    self.assertEqual(lump.headers['Node-kind'], 'foo')
    self.assertEqual(len(lump.headers), 1)
    self.assertIsNone(lump.props)
    self.assertIsNone(lump.text)

  def testSource(self):
    lump = svndumpmultitool.Lump(source=svndumpmultitool.Lump.COPY)
    self.assertFalse(lump.headers)
    self.assertIsNone(lump.props)
    self.assertIsNone(lump.text)
    self.assertIs(lump.source, lump.COPY)


class LumpDeleteHeaderTest(unittest.TestCase):
  def testExists(self):
    lump = svndumpmultitool.Lump()
    lump.headers['foo'] = 'bar'
    lump.DeleteHeader('foo')
    self.assertNotIn('foo', lump.headers)

  def testDoesNotExist(self):
    lump = svndumpmultitool.Lump()
    lump.DeleteHeader('foo')
    # We're just checking that it doesn't raise an exception


class LumpParsePropsTest(unittest.TestCase):
  def setUp(self):
    self.lump = svndumpmultitool.Lump()

  def testSimple(self):
    self.lump._ParseProps('K 3\nfoo\nV 3\nbar\nPROPS-END\n')
    self.assertEquals(self.lump.props['foo'], 'bar')

  def testMultiple(self):
    self.lump._ParseProps('K 3\nfoo\nV 3\nbar\n'
                          'K 3\nbar\nV 3\nbaz\n'
                          'D 3\nbaz\n'
                          'PROPS-END\n')
    self.assertEquals(self.lump.props['foo'], 'bar')
    self.assertEquals(self.lump.props['bar'], 'baz')
    self.assertIsNone(self.lump.props['baz'])

  def testWithNewline(self):
    """Keys and values with newlines in them should just work."""
    self.lump._ParseProps('K 7\n\nf\no\no\n\nV 7\n\nb\na\nr\n\nPROPS-END\n')
    self.assertEquals(self.lump.props['\nf\no\no\n'], '\nb\na\nr\n')

  def testDelete(self):
    self.lump._ParseProps('D 3\nfoo\nPROPS-END\n')
    self.assertIsNone(self.lump.props['foo'])

  def testEmpty(self):
    self.lump._ParseProps('PROPS-END\n')
    self.assertFalse(self.lump.headers)

  def testMissingPropsEnd(self):
    with self.assertRaises(Exception):
      self.lump._ParseProps('D 3\nfoo\n')

  def testTruncated(self):
    with self.assertRaises(Exception):
      self.lump._ParseProps('K 3\nfoo\nV 100\nfoo')

  def testUnknownFormat(self):
    with self.assertRaises(ValueError):
      self.lump._ParseProps('Z 3\nPROPS-END\n')


class LumpSetPropertyTest(unittest.TestCase):
  def setUp(self):
    self.lump = svndumpmultitool.Lump()

  def testFirstProperty(self):
    self.lump.SetProperty('foo', 'bar')
    self.assertEquals(self.lump.props['foo'], 'bar')

  def testNotFirstProperty(self):
    self.lump.SetProperty('foo', 'bar')
    self.lump.SetProperty('bar', 'baz')
    self.assertEquals(self.lump.props['foo'], 'bar')
    self.assertEquals(self.lump.props['bar'], 'baz')


class LumpDeletePropertyTest(unittest.TestCase):
  def setUp(self):
    self.lump = svndumpmultitool.Lump()

  def testExists(self):
    self.lump.SetProperty('foo', 'bar')
    self.lump.DeleteProperty('foo')
    self.assertNotIn('foo', self.lump.props)

  def testDoesNotExist(self):
    self.lump.SetProperty('bar', 'baz')
    self.lump.DeleteProperty('foo')
    # Just making sure no exception is raised

  def testPropsIsNone(self):
    self.lump.DeleteProperty('foo')
    # Just making sure no exception is raised


class LumpGeneratePropTextTest(unittest.TestCase):
  def setUp(self):
    self.lump = svndumpmultitool.Lump()

  def testSimple(self):
    self.lump.SetProperty('foo', 'bar')
    self.assertEquals(self.lump._GeneratePropText(),
                      'K 3\nfoo\nV 3\nbar\nPROPS-END\n')

  def testMultiple(self):
    self.lump.SetProperty('foo', 'bar')
    self.lump.SetProperty('bar', 'baz')
    self.lump.SetProperty('baz', None)
    self.assertEquals(self.lump._GeneratePropText(),
                      'K 3\nfoo\nV 3\nbar\n'
                      'K 3\nbar\nV 3\nbaz\n'
                      'D 3\nbaz\n'
                      'PROPS-END\n')

  def testDelete(self):
    self.lump.SetProperty('foo', None)
    self.assertEquals(self.lump._GeneratePropText(), 'D 3\nfoo\nPROPS-END\n')

  def testEmpty(self):
    self.lump.SetProperty('foo', 'bar')
    self.lump.DeleteProperty('foo')
    self.assertEquals(self.lump._GeneratePropText(), 'PROPS-END\n')

  def testNoPropertiesBlock(self):
    self.assertEquals(self.lump._GeneratePropText(), '')


class LumpFixHeadersTest(unittest.TestCase):
  def testPropContentLength(self):
    lump = svndumpmultitool.Lump()
    lump.headers['Prop-content-length'] = '1'
    lump.SetProperty('foo', 'bar')
    proptext = lump._GeneratePropText()
    lump._FixHeaders(proptext, None)
    self.assertEquals(lump.headers['Prop-content-length'],
                      str(len(proptext)))

  def testDeletePropContentLength(self):
    lump = svndumpmultitool.Lump()
    lump.headers['Prop-content-length'] = '1'
    proptext = lump._GeneratePropText()
    lump._FixHeaders(proptext, None)
    self.assertNotIn('Prop-content-length', lump.headers)

  def testSetTextContentLength(self):
    lump = svndumpmultitool.Lump()
    lump.text = 'foo'
    lump._FixHeaders('', None)
    self.assertEquals(lump.headers['Text-content-length'], '3')

  def testSetTextContentMD5(self):
    lump = svndumpmultitool.Lump()
    lump.text = 'foo'
    lump._FixHeaders('', None)
    self.assertEquals(lump.headers['Text-content-md5'],
                      'acbd18db4cc2f85cedef654fccc4a4d8')

  def testLeaveTextDeltaAlone(self):
    lump = svndumpmultitool.Lump()
    lump.headers['Text-delta'] = 'true'
    lump.headers['Text-content-md5'] = 'foo'
    lump.text = 'foo'
    lump._FixHeaders('', None)
    self.assertEquals(lump.headers['Text-content-md5'], 'foo')
    self.assertEquals(lump.headers['Text-content-length'], '3')

  def testDeleteTextHeaders(self):
    lump = svndumpmultitool.Lump()
    lump.headers['Text-content-length'] = '3'
    lump.headers['Text-content-md5'] = 'foo'
    lump.headers['Text-content-sha1'] = 'bar'
    lump.headers['Text-delta'] = 'baz'
    lump._FixHeaders('', None)
    self.assertNotIn('Text-content-length', lump.headers)
    self.assertNotIn('Text-content-md5', lump.headers)
    self.assertNotIn('Text-content-sha1', lump.headers)
    self.assertNotIn('Text-delta', lump.headers)

  def testSetContentLength(self):
    lump = svndumpmultitool.Lump()
    lump.headers['Content-length'] = '10'
    lump.text = 'foo'
    proptext = 'bar'
    lump._FixHeaders(proptext, None)
    self.assertEquals(lump.headers['Content-length'], '6')

  def testRevmapRevision(self):
    lump = svndumpmultitool.Lump()
    lump.headers['Revision-number'] = '10'
    revmap = {10: 20}
    lump._FixHeaders('', revmap)
    self.assertEquals(lump.headers['Revision-number'], '20')

  def testRevmapCopyFrom(self):
    lump = svndumpmultitool.Lump()
    lump.headers['Node-copyfrom-rev'] = '10'
    revmap = {10: 20}
    lump._FixHeaders('', revmap)
    self.assertEquals(lump.headers['Node-copyfrom-rev'], '20')


class LumpReadRFC822HeadersTest(unittest.TestCase):
  def testSimple(self):
    stream = StringIO.StringIO('foo: bar\n\n')
    result = svndumpmultitool.Lump._ReadRFC822Headers(stream)
    self.assertEquals(result.headers['foo'], 'bar')

  def testMultiple(self):
    stream = StringIO.StringIO('foo: bar\nbar: baz\n\n')
    result = svndumpmultitool.Lump._ReadRFC822Headers(stream)
    self.assertEquals(result.headers['foo'], 'bar')
    self.assertEquals(result.headers['bar'], 'baz')

  def testBlankLines(self):
    stream = StringIO.StringIO('\n\nfoo: bar\n\n')
    result = svndumpmultitool.Lump._ReadRFC822Headers(stream)
    self.assertEquals(result.headers['foo'], 'bar')

  def testColonInValue(self):
    stream = StringIO.StringIO('foo: b:a:r\n\n')
    result = svndumpmultitool.Lump._ReadRFC822Headers(stream)
    self.assertEquals(result.headers['foo'], 'b:a:r')

  def testInvalid(self):
    stream = StringIO.StringIO('foobar\n\n')
    with self.assertRaises(ValueError):
      svndumpmultitool.Lump._ReadRFC822Headers(stream)

  def testEOF(self):
    stream = StringIO.StringIO('')
    result = svndumpmultitool.Lump._ReadRFC822Headers(stream)
    self.assertIsNone(result)

  def testTruncated(self):
    stream = StringIO.StringIO('foo: bar')
    with self.assertRaises(EOFError):
      svndumpmultitool.Lump._ReadRFC822Headers(stream)
    # A trailing blank line is needed to end headers
    stream = StringIO.StringIO('foo: bar\n')
    with self.assertRaises(EOFError):
      svndumpmultitool.Lump._ReadRFC822Headers(stream)


class LumpReadTest(unittest.TestCase):
  def testEOF(self):
    stream = StringIO.StringIO('\n')
    result = svndumpmultitool.Lump.Read(stream)
    self.assertIsNone(result)

  def testHeadersOnly(self):
    stream = StringIO.StringIO('foo: bar\n\n')
    result = svndumpmultitool.Lump.Read(stream)
    self.assertEquals(result.headers['foo'], 'bar')
    self.assertIsNone(result.props)
    self.assertIsNone(result.text)

  def testProps(self):
    stream = StringIO.StringIO('Prop-content-length: 26\n\n'
                               'K 3\nfoo\nV 3\nbar\nPROPS-END\n')
    result = svndumpmultitool.Lump.Read(stream)
    self.assertEquals(result.props['foo'], 'bar')
    self.assertIsNone(result.text)

  def testText(self):
    text = 'Some text\nSome more text'
    stream = StringIO.StringIO('Text-content-length: %s\n\n%s'
                               % (len(text), text))
    result = svndumpmultitool.Lump.Read(stream)
    self.assertEquals(result.text, text)
    self.assertIsNone(result.props)

  def testBoth(self):
    stream = StringIO.StringIO('Text-content-length: 3\n'
                               'Prop-content-length: 26\n\n'
                               'K 3\nfoo\nV 3\nbar\nPROPS-END\n'
                               'foo\n')
    result = svndumpmultitool.Lump.Read(stream)
    self.assertEquals(result.text, 'foo')
    self.assertEquals(result.props['foo'], 'bar')


class LumpWriteTest(unittest.TestCase):
  def setUp(self):
    self.stream = StringIO.StringIO()
    self.lump = svndumpmultitool.Lump()

  def testJustHeaders(self):
    self.lump.headers['foo'] = 'bar'
    self.lump.Write(self.stream, None)
    self.assertEquals(self.stream.getvalue(), 'foo: bar\n\n')

  def testText(self):
    self.lump.text = 'foo'
    self.lump.Write(self.stream, None)
    self.assertEquals(self.stream.getvalue(),
                      'Text-content-length: 3\n'
                      'Text-content-md5: acbd18db4cc2f85cedef654fccc4a4d8\n'
                      'Content-length: 3\n\n'
                      'foo\n\n')

  def testProps(self):
    self.lump.headers['foo'] = 'bar'
    self.lump.SetProperty('bar', 'baz')
    self.lump.Write(self.stream, None)
    self.assertEquals(self.stream.getvalue(),
                      'foo: bar\n'
                      'Prop-content-length: 26\n'
                      'Content-length: 26\n\n'
                      'K 3\nbar\nV 3\nbaz\nPROPS-END\n\n')

  def testBoth(self):
    self.lump.headers['foo'] = 'bar'
    self.lump.SetProperty('bar', 'baz')
    self.lump.Write(self.stream, None)
    self.lump.text = 'foo'
    self.assertEquals(self.stream.getvalue(),
                      'foo: bar\n'
                      'Prop-content-length: 26\n'
                      'Content-length: 26\n\n'
                      'K 3\nbar\nV 3\nbaz\nPROPS-END\n\n')


class LumpDoesNotAffectExternalsTest(unittest.TestCase):
  def testDelete(self):
    lump = svndumpmultitool.Lump(action='delete')
    lump.SetProperty('svn:externals', 'foo')
    self.assertEquals(lump.DoesNotAffectExternals(), True)

  def testFile(self):
    lump = svndumpmultitool.Lump(kind='file', action='change')
    lump.SetProperty('svn:externals', 'foo')
    self.assertEquals(lump.DoesNotAffectExternals(), True)

  def testNoPropertiesBlock(self):
    lump = svndumpmultitool.Lump(kind='dir', action='change')
    self.assertEquals(lump.DoesNotAffectExternals(), True)

  def testExplicitModification(self):
    lump = svndumpmultitool.Lump(kind='dir', action='change')
    lump.SetProperty('svn:externals', 'foo')
    self.assertEquals(lump.DoesNotAffectExternals(), False)

  def testExplicitDeletion(self):
    lump = svndumpmultitool.Lump(kind='dir', action='change')
    lump.headers['Prop-delta'] = 'true'
    lump.SetProperty('svn:externals', None)
    self.assertEquals(lump.DoesNotAffectExternals(), False)

  def testAdd(self):
    lump = svndumpmultitool.Lump(kind='dir', action='add')
    lump.SetProperty('garbage', 'foo')
    self.assertEquals(lump.DoesNotAffectExternals(), True)

  def testPropDeltaTrue(self):
    lump = svndumpmultitool.Lump(kind='dir', action='change')
    lump.headers['Prop-delta'] = 'true'
    lump.SetProperty('garbage', 'foo')
    self.assertEquals(lump.DoesNotAffectExternals(), True)

  def testPossibleDeleteByOmission(self):
    lump = svndumpmultitool.Lump(kind='dir', action='change')
    lump.SetProperty('garbage', 'foo')
    self.assertEquals(lump.DoesNotAffectExternals(), False)


class GrabLumpsForPathTest(unittest.TestCase):

  @mock.patch('svndumpmultitool.svn_core')
  @mock.patch('svndumpmultitool.svn_repos')
  @mock.patch('svndumpmultitool.svn_fs')
  def testGrabLumps(self, fs, unused_repos, core):
    is_dir = {
        '': True,
        'foo': True,
        'foo/file1': False,
        'foo/file2': False,
        'foo/subdir': True
        }
    fs.is_dir = lambda _, path: is_dir[path]
    dir_entries = {
        '': {'foo': None},
        'foo': collections.OrderedDict((('file1', None),
                                        ('file2', None),
                                        ('subdir', None))),
        'foo/subdir': {}
        }
    fs.dir_entries = lambda _, path: dir_entries[path]
    file_contents = {
        'foo/file1': io.BytesIO('file1_contents'),
        'foo/file2': io.BytesIO('file2_contents')
        }
    fs.file_contents = lambda _, path: file_contents[path]
    core.svn_stream_read = lambda stream, size: stream.read(size)
    file_md5_checksum = {
        'foo/file1': 'file1_checksum',
        'foo/file2': 'file2_checksum'
        }
    fs.file_md5_checksum = lambda _, path: file_md5_checksum[path]
    node_proplist = {
        '': {},
        'foo': {'fooprop': 'fooval'},
        'foo/file1': {'file1prop': 'file1val'},
        'foo/file2': {},
        'foo/subdir': {}
        }
    fs.node_proplist = lambda _, path: node_proplist[path]
    results = svndumpmultitool.GrabLumpsForPath(
        MAIN_REPO, MAIN_REPO_REV, '', 'bar', svndumpmultitool.Lump.COPY)
    self.assertEquals(len(results), 5)
    root, foo, subdir, file2, file1 = results
    self.assertEquals(dict(root.headers), {
        'Node-path': 'bar',
        'Node-kind': 'dir',
        'Node-action': 'add',
        })
    self.assertFalse(root.props)
    self.assertIsNone(root.text)
    self.assertIs(root.source, root.COPY)
    self.assertEquals(dict(foo.headers), {
        'Node-path': 'bar/foo',
        'Node-kind': 'dir',
        'Node-action': 'add',
        })
    self.assertEquals(dict(foo.props), {'fooprop': 'fooval'})
    self.assertIsNone(foo.text)
    self.assertIs(foo.source, foo.COPY)
    self.assertEquals(dict(file1.headers), {
        'Node-path': 'bar/foo/file1',
        'Node-kind': 'file',
        'Node-action': 'add',
        'Text-content-md5': 'file1_checksum'.encode('hex_codec')
        })
    self.assertEquals(dict(file1.props), {'file1prop': 'file1val'})
    self.assertEquals(file1.text, 'file1_contents')
    self.assertIs(file1.source, file1.COPY)
    self.assertEquals(dict(file2.headers), {
        'Node-path': 'bar/foo/file2',
        'Node-kind': 'file',
        'Node-action': 'add',
        'Text-content-md5': 'file2_checksum'.encode('hex_codec')
        })
    self.assertFalse(file2.props)
    self.assertEquals(file2.text, 'file2_contents')
    self.assertIs(file2.source, file2.COPY)
    self.assertEquals(dict(subdir.headers), {
        'Node-path': 'bar/foo/subdir',
        'Node-kind': 'dir',
        'Node-action': 'add',
        })
    self.assertFalse(subdir.props)
    self.assertIsNone(subdir.text)
    self.assertIs(subdir.source, subdir.COPY)

  @mock.patch('svndumpmultitool.svn_core')
  @mock.patch('svndumpmultitool.svn_repos')
  @mock.patch('svndumpmultitool.svn_fs')
  def testGrabLumpsWithSrcPath(self, fs, unused_repos, core):
    fs.is_dir.return_value = False
    fs.file_contents.return_value = io.BytesIO('foo')
    core.svn_stream_read = lambda stream, size: stream.read(size)
    fs.file_md5_checksum.return_value = 'foo_checksum'
    fs.node_proplist.return_value = {}
    results = svndumpmultitool.GrabLumpsForPath(MAIN_REPO, MAIN_REPO_REV,
                                                'foo/bar', 'baz',
                                                svndumpmultitool.Lump.EXTERNALS)
    self.assertEqual(len(results), 1)
    self.assertEqual(results[0].headers['Node-path'], 'baz')
    self.assertEqual(results[0].source, svndumpmultitool.Lump.EXTERNALS)


@mock.patch('svndumpmultitool.subprocess.Popen', new=MockPopen)
class ExtractNodeKindTest(unittest.TestCase):
  def testFile(self):
    with MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'filesize', MAIN_REPO, '-r%s' % MAIN_REPO_REV,
                'foo'),
        'stdout': '120',
        'stderr': ''
        }):
      result = svndumpmultitool.ExtractNodeKind(MAIN_REPO, MAIN_REPO_REV, 'foo')
    self.assertEqual(result, 'file')

  def testDir(self):
    with MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'filesize', MAIN_REPO, '-r%s' % MAIN_REPO_REV,
                'foo'),
        'stdout': '',
        'stderr': 'File not found',
        'returncode': 1
        }):
      result = svndumpmultitool.ExtractNodeKind(MAIN_REPO, MAIN_REPO_REV, 'foo')
    self.assertEqual(result, 'dir')


@mock.patch('svndumpmultitool.subprocess.Popen', new=MockPopen)
class ExtractNodeKindsTest(unittest.TestCase):
  def testDir(self):
    with MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'tree', '--full-paths', '-r%s' % MAIN_REPO_REV,
                MAIN_REPO, 'foo'),
        'stdout': ('foo/\n'
                   'foo/dir1/\n'
                   'foo/dir1/file1\n'
                   'foo/dir1/file2\n'
                   'foo/dir2/\n'
                   'foo/file3\n\n'),
        }):
      result = svndumpmultitool.ExtractNodeKinds(MAIN_REPO, MAIN_REPO_REV,
                                                 'foo')
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
    with MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'tree', '--full-paths', '-r%s' % MAIN_REPO_REV,
                MAIN_REPO, 'foo'),
        'stdout': 'foo\n'
        }):
      result = svndumpmultitool.ExtractNodeKinds(MAIN_REPO, MAIN_REPO_REV,
                                                 'foo')
    self.assertEqual(result, {'': 'file'})

  def testFails(self):
    with self.assertRaises(subprocess.CalledProcessError):
      with MockPopen.ExpectCommands({
          'cmd': ('svnlook', 'tree', '--full-paths', '-r%s' % MAIN_REPO_REV,
                  MAIN_REPO, 'foo'),
          'stdout': 'foo\n',
          'returncode': 1
          }):
        svndumpmultitool.ExtractNodeKinds(MAIN_REPO, MAIN_REPO_REV, 'foo')


@mock.patch('svndumpmultitool.subprocess.Popen', new=MockPopen)
class DiffPathsTest(unittest.TestCase):
  def testNormal(self):
    with MockPopen.ExpectCommands({
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
      results = svndumpmultitool.DiffPaths(MAIN_REPO, 'foo', MAIN_REPO_REV - 1,
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
    with self.assertRaises(ValueError), MockPopen.ExpectCommands({
        'cmd': ('svn', 'diff', '--summarize',
                '--old=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV - 1),
                '--new=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV)),
        'stdout': 'X  file://' + MAIN_REPO + '/foo/unknown\n'
        }):
      svndumpmultitool.DiffPaths(MAIN_REPO, 'foo', MAIN_REPO_REV - 1, 'foo',
                                 MAIN_REPO_REV)

  def testBadPropsOp(self):
    with self.assertRaises(ValueError), MockPopen.ExpectCommands({
        'cmd': ('svn', 'diff', '--summarize',
                '--old=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV - 1),
                '--new=file://%s/%s@%s' % (MAIN_REPO, 'foo', MAIN_REPO_REV)),
        'stdout': ' X file://' + MAIN_REPO + '/foo/unknown\n'
        }):
      svndumpmultitool.DiffPaths(MAIN_REPO, 'foo', MAIN_REPO_REV - 1, 'foo',
                                 MAIN_REPO_REV)


class FilterFilterLumpTest(unittest.TestCase):
  def setUp(self):
    self.paths = svndumpmultitool.InterestingPaths(['trunk/foo'])
    self.filter = svndumpmultitool.Filter('/svn/foo', self.paths)

  def testBoringPath(self):
    """Path that does not match the filter should return no Lumps."""
    lump = svndumpmultitool.Lump(kind='file', action='add',
                                 path='trunk/bar/baz')
    output = self.filter._FilterLump(10, lump)
    self.assertEquals(output, [])

  def testInterestingPath(self):
    """Path that matches the filter should pass through unchanged."""
    lump = svndumpmultitool.Lump(kind='file', action='add',
                                 path='trunk/foo/bar')
    output = self.filter._FilterLump(10, lump)
    self.assertEquals(output, [lump])

  def testParentDir(self):
    """Parent dir should have its properties stripped."""
    lump = svndumpmultitool.Lump(kind='dir', action='add', path='trunk')
    lump.SetProperty('foo', 'bar')
    output = self.filter._FilterLump(10, lump)
    self.assertEquals(output, [lump])
    self.assertIsNone(lump.props)

  def testParentFile(self):
    """Parent file should be replaced with propertyless dir."""
    lump = svndumpmultitool.Lump(kind='file', action='add', path='trunk')
    lump.SetProperty('foo', 'bar')
    output = self.filter._FilterLump(10, lump)
    # Result should be a single Lump
    self.assertEquals(len(output), 1)
    # A new lump should be created
    self.assertNotEqual(output[0], lump)
    # It should be a propertyless dir with the same path as the input
    self.assertEquals(output[0].headers['Node-kind'], 'dir')
    self.assertEquals(output[0].headers['Node-path'], lump.headers['Node-path'])
    self.assertIsNone(output[0].props)

  def testParentChange(self):
    """Parent changes should be ignored."""
    lump = svndumpmultitool.Lump(kind='dir', action='change', path='trunk')
    output = self.filter._FilterLump(10, lump)
    self.assertEquals(output, [])

  def testParentDelete(self):
    """Parent deletes should be passed through unchanged."""
    lump = svndumpmultitool.Lump(action='delete', path='trunk')
    output = self.filter._FilterLump(10, lump)
    self.assertEquals(output, [lump])

  @mock.patch('svndumpmultitool.Filter._FixCopyFrom')
  def testCopyFromOnParent(self, fix_copy_from):
    """_FixCopyFrom must be called."""
    lump = svndumpmultitool.Lump(kind='dir', action='add', path='trunk')
    lump.headers['Node-copyfrom-path'] = 'branches/bar'
    lump.headers['Node-copyfrom-rev'] = '1'
    fix_copy_from.return_value = ['FIXED']
    output = self.filter._FilterLump(10, lump)
    fix_copy_from.assert_called_once_with(lump)
    self.assertEquals(output, fix_copy_from.return_value)

  @mock.patch('svndumpmultitool.Filter._InternalizeExternals')
  def testPathWithExternals(self, internalize_externals):
    """_InternalizeExternals must be called."""
    # externals_map must not be empty to trigger internalizing externals
    self.filter.externals_map = {'foo': 'bar'}
    lump = svndumpmultitool.Lump(kind='dir', action='add', path='trunk/foo/bar')
    lump.SetProperty('svn:externals', 'foo')
    internalize_externals.return_value = ['FIXED']
    output = self.filter._FilterLump(10, lump)
    internalize_externals.assert_called_once_with(10, lump)
    self.assertEquals(output, internalize_externals.return_value)

  @mock.patch('svndumpmultitool.Filter._InternalizeExternals')
  def testPathWithExternalsDisabled(self, internalize_externals):
    """_InternalizeExternals must not be called when no externals map exists."""
    lump = svndumpmultitool.Lump(kind='dir', action='add', path='trunk/foo/bar')
    lump.SetProperty('svn:externals', 'foo')
    output = self.filter._FilterLump(10, lump)
    self.assertFalse(internalize_externals.called)
    self.assertEquals(output, [lump])


class FilterFixCopyFromTest(unittest.TestCase):
  # TODO(emosenkis): complete test coverage of _FixCopyFrom

  @mock.patch('svndumpmultitool.InterestingPaths.Interesting',
              return_value=svndumpmultitool.InterestingPaths.PARENT)
  @mock.patch('svndumpmultitool.GrabLumpsForPath')
  def testCopyParentToParent(self, grab_lumps, _):
    filt = svndumpmultitool.Filter(MAIN_REPO,
                                   svndumpmultitool.InterestingPaths([]))
    lump = svndumpmultitool.Lump(action='add', path='foo', kind='dir')
    lump.headers['Node-copyfrom-rev'] = '10'
    lump.headers['Node-copyfrom-path'] = 'foo'
    result = filt._FixCopyFrom(lump)
    self.assertEquals(len(result), 1)
    result = result[0]
    self.assertEquals(result.headers['Node-copyfrom-rev'], '10')
    self.assertEquals(result.headers['Node-copyfrom-path'], 'foo')
    self.assertFalse(grab_lumps.called)


class FilterFlattenMultipleActionsTest(unittest.TestCase):

  # Autospec causes the mock to receive self as its first arg
  @mock.patch('svndumpmultitool.Filter._ActionPairFlattener.Flatten',
              autospec=True)
  def testRunThroughPairs(self, flatten):
    filt = svndumpmultitool.Filter(MAIN_REPO,
                                   svndumpmultitool.InterestingPaths([]))
    contents = []
    # Add three lumps for one path, three lumps for another, and one lump for a
    # third
    contents.append(svndumpmultitool.Lump(path='foo', action='add',
                                          kind='file'))
    contents.append(svndumpmultitool.Lump(path='foo', action='change',
                                          kind='file'))
    contents.append(svndumpmultitool.Lump(path='foo', action='delete',
                                          kind='file'))
    contents.append(svndumpmultitool.Lump(path='bar', action='add', kind='dir'))
    contents.append(svndumpmultitool.Lump(path='bar', action='change',
                                          kind='dir'))
    contents.append(svndumpmultitool.Lump(path='bar', action='delete',
                                          kind='dir'))
    contents.append(svndumpmultitool.Lump(path='baz', action='add', kind='dir'))
    def Flatten(self):
      self.lumps.pop(0)
      self.contents.pop(0)
    flatten.side_effect = Flatten
    filt._FlattenMultipleActions(MAIN_REPO_REV, contents)
    self.assertEqual(len(contents), 3)
    self.assertEqual(flatten.call_count, 4)

  def testAddAddDelete(self):
    filt = svndumpmultitool.Filter(MAIN_REPO,
                                   svndumpmultitool.InterestingPaths([]))
    contents = []
    contents.append(svndumpmultitool.Lump(path='foo', action='add',
                                          kind='file'))
    contents.append(svndumpmultitool.Lump(path='foo', action='add',
                                          kind='file'))
    contents.append(svndumpmultitool.Lump(path='foo', action='delete',
                                          kind='file'))
    filt._FlattenMultipleActions(MAIN_REPO_REV, contents)
    self.assertFalse(contents)

  def testAddChangeDelete(self):
    filt = svndumpmultitool.Filter(MAIN_REPO,
                                   svndumpmultitool.InterestingPaths([]))
    contents = []
    contents.append(svndumpmultitool.Lump(path='foo', action='add',
                                          kind='file'))
    contents.append(svndumpmultitool.Lump(path='foo', action='change',
                                          kind='file'))
    contents.append(svndumpmultitool.Lump(path='foo', action='delete',
                                          kind='file'))
    filt._FlattenMultipleActions(MAIN_REPO_REV, contents)
    self.assertFalse(contents)

  def testDeleteAddChange(self):
    filt = svndumpmultitool.Filter(MAIN_REPO,
                                   svndumpmultitool.InterestingPaths([]))
    contents = []
    contents.append(svndumpmultitool.Lump(path='foo', action='delete',
                                          kind='file'))
    contents.append(svndumpmultitool.Lump(path='foo', action='add',
                                          kind='file'))
    contents.append(svndumpmultitool.Lump(path='foo', action='change',
                                          kind='file'))
    filt._FlattenMultipleActions(MAIN_REPO_REV, contents)
    self.assertEqual(len(contents), 1)
    self.assertEqual(contents[0].headers['Node-action'], 'replace')


class FilterActionPairFlattenerTest(unittest.TestCase):
  def testConstructor(self):
    apf = svndumpmultitool.Filter._ActionPairFlattener(
        MAIN_REPO, MAIN_REPO_REV, range(10), 'trunk', range(5))
    self.assertEqual(apf.repo, MAIN_REPO)
    self.assertEqual(apf.revision_number, MAIN_REPO_REV)
    self.assertEqual(apf.contents, range(10))
    self.assertEqual(apf.path, 'trunk')
    self.assertEqual(apf.lumps, range(5))
    self.assertEqual(apf.first, 0)
    self.assertEqual(apf.second, 1)

  def MakeActionPairFlattener(self, action1, action2):
    if action1 == 'delete':
      first = svndumpmultitool.Lump(path='foo', action=action1)
    else:
      first = svndumpmultitool.Lump(path='foo', kind='file', action=action1)
    if action2 == 'delete':
      second = svndumpmultitool.Lump(path='foo', action=action2)
    else:
      second = svndumpmultitool.Lump(path='foo', kind='file', action=action2)
    contents = [first, second]
    lumps = [first, second]
    apf = svndumpmultitool.Filter._ActionPairFlattener(MAIN_REPO, MAIN_REPO_REV,
                                                       contents, 'trunk', lumps)
    return apf

  def testDropExtraneousAdd(self):
    """The first add operation should be deleted."""
    apf = self.MakeActionPairFlattener('add', 'add')
    apf.Flatten()
    self.assertEqual(len(apf.contents), 1)
    self.assertIs(apf.contents[0], apf.second)

  def testMergeChangeIntoAddWithText(self):
    apf = self.MakeActionPairFlattener('add', 'change')
    apf.first.text = 'foo'
    apf.second.text = 'bar'
    apf.second.headers['Text-content-md5'] = 'bar-checksum'
    apf.Flatten()
    self.assertEqual(len(apf.contents), 1)
    result = apf.contents[0]
    self.assertEqual(result.headers['Node-action'], 'add')
    self.assertEqual(result.headers['Text-content-md5'], 'bar-checksum')
    self.assertEqual(result.text, 'bar')

  def testMergeChangeIntoAddWithTextNoChecksum(self):
    apf = self.MakeActionPairFlattener('add', 'change')
    apf.first.text = 'foo'
    apf.second.text = 'bar'
    apf.first.headers['Text-content-md5'] = 'bar-checksum'
    apf.Flatten()
    self.assertEqual(len(apf.contents), 1)
    result = apf.contents[0]
    self.assertEqual(result.headers['Node-action'], 'add')
    self.assertNotIn('Text-content-md5', result.headers)
    self.assertEqual(result.text, 'bar')

  def testMergeChangeIntoAddWithoutText(self):
    apf = self.MakeActionPairFlattener('add', 'change')
    apf.first.text = 'foo'
    apf.Flatten()
    self.assertEqual(len(apf.contents), 1)
    result = apf.contents[0]
    self.assertEqual(result.headers['Node-action'], 'add')
    self.assertEqual(result.text, 'foo')

  def testMergeChangeIntoAddWithTextDelta(self):
    apf = self.MakeActionPairFlattener('add', 'change')
    apf.first.text = 'foo'
    apf.second.text = 'bar'
    apf.second.headers['Text-delta'] = 'true'
    with self.assertRaises(ValueError):
      apf.Flatten()

  def testMergeChangeIntoAddWithProps(self):
    apf = self.MakeActionPairFlattener('add', 'change')
    apf.first.props = {'foo': 'bar'}
    apf.second.props = {'bar': 'baz'}
    apf.Flatten()
    self.assertEqual(len(apf.contents), 1)
    result = apf.contents[0]
    self.assertEqual(result.headers['Node-action'], 'add')
    self.assertEqual(result.props, {'bar': 'baz'})

  def testMergeChangeWithPropsIntoAddWithoutProps(self):
    apf = self.MakeActionPairFlattener('add', 'change')
    apf.second.props = {'bar': 'baz'}
    apf.Flatten()
    self.assertEqual(len(apf.contents), 1)
    result = apf.contents[0]
    self.assertEqual(result.headers['Node-action'], 'add')
    self.assertEqual(result.props, {'bar': 'baz'})

  def testMergeChangeIntoAddWithoutProps(self):
    apf = self.MakeActionPairFlattener('add', 'change')
    apf.first.props = {'foo': 'bar'}
    apf.Flatten()
    self.assertEqual(len(apf.contents), 1)
    result = apf.contents[0]
    self.assertEqual(result.headers['Node-action'], 'add')
    self.assertEqual(result.props, {'foo': 'bar'})

  def testMergeChangeIntoAddWithPropsDelta(self):
    apf = self.MakeActionPairFlattener('add', 'change')
    apf.first.props = {'p1': 'v1', 'p2': 'v2', 'p3': 'v3'}
    apf.second.props = {'p1': 'v4', 'p2': None, 'p4': 'v5'}
    apf.second.headers['Prop-delta'] = 'true'
    apf.Flatten()
    self.assertEqual(len(apf.contents), 1)
    result = apf.contents[0]
    self.assertEqual(result.headers['Node-action'], 'add')
    self.assertEqual(result.props, {'p1': 'v4', 'p3': 'v3', 'p4': 'v5'})

  def testMergeChangeIntoChange(self):
    apf = self.MakeActionPairFlattener('change', 'change')
    apf.first.headers['Text-delta'] = 'true'
    apf.first.headers['Prop-delta'] = 'true'
    apf.first.props = {'p1': 'v1', 'p2': None, 'p3': None, 'p4': 'v2'}
    apf.second.headers['Prop-delta'] = 'true'
    apf.second.props = {'p1': None, 'p2': 'v3', 'p5': 'v4'}
    apf.first.text = 'first-text'
    apf.second.text = 'second-text'
    apf.Flatten()
    self.assertEqual(len(apf.contents), 1)
    result = apf.contents[0]
    self.assertEqual(result.headers['Node-action'], 'change')
    self.assertNotIn('Text-delta', result.headers)
    self.assertEqual(result.props, {'p1': None, 'p2': 'v3', 'p3': None,
                                    'p4': 'v2', 'p5': 'v4'})
    self.assertEqual(result.text, 'second-text')

  def testMoveDeleteToBeforeAdd(self):
    apf = self.MakeActionPairFlattener('add', 'delete')
    apf.first.source = svndumpmultitool.Lump.EXTERNALS
    apf.Flatten()
    self.assertEqual(apf.contents, [apf.second, apf.first])

  def testDropAddDeletePair(self):
    apf = self.MakeActionPairFlattener('add', 'delete')
    apf.Flatten()
    self.assertFalse(apf.contents)

  def testConvertDeleteAndAddIntoReplace(self):
    apf = self.MakeActionPairFlattener('delete', 'add')
    apf.second.text = 'foo-text'
    apf.Flatten()
    self.assertEquals(len(apf.contents), 1)
    result = apf.contents[0]
    self.assertEquals(result.headers['Node-path'], 'foo')
    self.assertEquals(result.headers['Node-kind'], 'file')
    self.assertEquals(result.headers['Node-action'], 'replace')
    self.assertEquals(result.text, 'foo-text')

  def testUnsupportedActionPairsFail(self):
    pairs = [('change', 'add'), ('change', 'delete'), ('delete', 'change'),
             ('delete', 'delete')]
    for action1, action2 in pairs:
      apf = self.MakeActionPairFlattener(action1, action2)
      with self.assertRaises(ValueError):
        apf.Flatten()


class FilterFilterRevTest(unittest.TestCase):
  def testTruncateRevs(self):
    filt = svndumpmultitool.Filter(MAIN_REPO,
                                   svndumpmultitool.InterestingPaths([]),
                                   truncate_revs=[2])
    lump = svndumpmultitool.Lump(path='trunk', action='add', kind='file')
    good_revhdr = svndumpmultitool.Lump()
    good_revhdr.headers['Revision-number'] = '1'
    self.assertTrue(filt.FilterRev(good_revhdr, [lump]))
    bad_revhdr = svndumpmultitool.Lump()
    bad_revhdr.headers['Revision-number'] = '2'
    self.assertFalse(filt.FilterRev(bad_revhdr, [lump]))

  def testDeleteProps(self):
    filt = svndumpmultitool.Filter(MAIN_REPO,
                                   svndumpmultitool.InterestingPaths([]),
                                   delete_properties=['bad-property'])
    lump = svndumpmultitool.Lump(path='trunk', action='add', kind='file')
    lump.SetProperty('bad-property', 'bad-value')
    lump.SetProperty('good-property', 'good-value')
    revhdr = svndumpmultitool.Lump()
    revhdr.headers['Revision-number'] = MAIN_REPO_REV
    self.assertTrue(filt.FilterRev(revhdr, [lump]))
    self.assertNotIn('bad-property', lump.props)
    self.assertIn('good-property', lump.props)


if __name__ == '__main__':
  unittest.main()
