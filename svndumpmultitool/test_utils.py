# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Utilities for use in tests."""

from __future__ import absolute_import

import contextlib
import io
import subprocess


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

  def __init__(self, cmd, stdout=None, stderr=None,
               bufsize=None):
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
