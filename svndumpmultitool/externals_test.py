# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Tests for externals."""

from __future__ import absolute_import

import unittest

import mock

from svndumpmultitool import externals
from svndumpmultitool import test_utils

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


def ExternalsDescriptionFromDefaults(dstpath='baz', srcrepo='/svn/foo',
                                     srcrev=None, srcpath='baz', srcpeg=None):
  """Helper for creating ExternalsDescriptions with defaults for all fields."""
  return externals.ExternalsDescription(dstpath, srcrepo, srcrev, srcpath,
                                        srcpeg)


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


class SanitizeRevTest(unittest.TestCase):
  """Tests that revision numbers are sanitized properly."""

  def testIntAsString(self):
    """String representation of int should be converted to int."""
    self.assertEqual(externals._SanitizeRev('1'), 1)

  def testInt(self):
    """int should stay the same."""
    self.assertEqual(externals._SanitizeRev(100), 100)

  def testHEAD(self):
    """HEAD (case-insensitive) should become None."""
    self.assertEqual(externals._SanitizeRev('hEaD'), None)

  def testNone(self):
    """None should stay the same."""
    self.assertEqual(externals._SanitizeRev(None), None)

  def testNegativeInt(self):
    """Negative int should raise ValueError."""
    with self.assertRaises(ValueError):
      externals._SanitizeRev(-1)

  def testNegativeIntAsString(self):
    """String representation of negative int should raise ValueError."""
    with self.assertRaises(ValueError):
      externals._SanitizeRev('-1')

  def testNonIntegerString(self):
    """Non-integer string should raise ValueError."""
    with self.assertRaises(ValueError):
      externals._SanitizeRev('1.0')


@mock.patch('subprocess.Popen', new=test_utils.MockPopen)
class ExternalsDescriptionSourceExistsTest(unittest.TestCase):
  def testExists(self):
    with test_utils.MockPopen.ExpectCommands({
        'cmd': ('svn', 'ls', 'file:///svn/foo/baz@1'),
        'stdout': 'some output',
        'stderr': ''
        }):
      ed = ExternalsDescriptionFromDefaults(srcrev=1)
      self.assertEquals(ed.SourceExists(), True)

  @mock.patch.object(externals, 'LOGGER')
  def testDoesNotExist(self, logger):
    with test_utils.MockPopen.ExpectCommands({
        'cmd': ('svn', 'ls', 'file:///svn/foo/baz@1'),
        'stdout': '',
        'stderr': 'error!',
        'returncode': 1
        }):
      ed = ExternalsDescriptionFromDefaults(srcrev=1)
      self.assertEquals(ed.SourceExists(), False)
      self.assertEquals(logger.warning.call_count, 1)


class DiffTest(unittest.TestCase):
  def testDiff(self):
    """Test that Diff produces the correct results."""
    old = {}
    new = {}
    # Change repo (delete, add)
    old['delete_and_add'] = externals.ExternalsDescription(
        'delete_and_add', '/usr/local/repos/myrepo', 1080, 'bar/dst1', 1000)
    new['delete_and_add'] = externals.ExternalsDescription(
        'delete_and_add', '/usr/local/repos/newrepo', 1080, 'bar/dst1', 1000)
    # Change rev (change)
    old['changed_rev'] = externals.ExternalsDescription(
        'changed_rev', '/usr/local/repos/myrepo', 1080, 'bar/dst2', 1000)
    new['changed_rev'] = externals.ExternalsDescription(
        'changed_rev', '/usr/local/repos/myrepo', 1090, 'bar/dst2', 1000)
    # Changes dst (change)
    old['changed_dst'] = externals.ExternalsDescription(
        'changed_dst', '/usr/local/repos/myrepo', 1080, 'bar/dst3', 1000)
    new['changed_dst'] = externals.ExternalsDescription(
        'changed_dst', '/usr/local/repos/myrepo', 1080, 'bar/dst3a', 1000)
    # Changes peg (noop)
    old['peg_change_noop'] = externals.ExternalsDescription(
        'peg_change_noop', '/usr/local/repos/myrepo', 1080, 'bar/dst4', 1000)
    new['peg_change_noop'] = externals.ExternalsDescription(
        'peg_change_noop', '/usr/local/repos/myrepo', 1080, 'bar/dst4', 2000)
    # Deletes deleted, adds added
    old['deleted'] = externals.ExternalsDescription(
        'deleted', '/usr/local/repos/myrepo', 1080, 'bar/dst5', 1000)
    new['added'] = externals.ExternalsDescription(
        'added', '/usr/local/repos/myrepo', 1080, 'bar/dst6', 2000)

    # Let's establish some expectations
    expected_adds = [new['delete_and_add'], new['added']]
    expected_changes = [(old['changed_rev'], new['changed_rev']),
                        (old['changed_dst'], new['changed_dst'])]
    expected_deletes = [old['delete_and_add'], old['deleted']]

    # Actually exercise the code
    added, changed, deleted = externals.Diff(old, new)

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


class ParseTest(unittest.TestCase):

  def Parse(self, description, externals_map=True):
    return externals.Parse(
        MAIN_REPO,
        MAIN_REPO_REV,
        PARENT_DIR,
        description,
        EXTERNALS_MAP if externals_map else None
        )

  @mock.patch.object(externals.ExternalsDescription, 'SourceExists')
  def testSimple(self, _):
    result = self.Parse('http://svn.foo.com/foo/baz baz')
    expected = {'baz': ExternalsDescriptionFromDefaults()}
    self.assertEquals(result, expected)

  @mock.patch.object(externals.ExternalsDescription, 'SourceExists')
  def testComments(self, _):
    result = self.Parse('#foo\nhttp://svn.foo.com/foo/baz baz')
    expected = {'baz': ExternalsDescriptionFromDefaults()}
    self.assertEquals(result, expected)

  @mock.patch.object(externals.ExternalsDescription, 'SourceExists')
  def testBlankLines(self, _):
    result = self.Parse('\n \t \nhttp://svn.foo.com/foo/baz baz\n\n')
    expected = {'baz': ExternalsDescriptionFromDefaults()}
    self.assertEquals(result, expected)

  @mock.patch.object(externals.ExternalsDescription, 'SourceExists')
  def testMultiple(self, _):
    result = self.Parse('http://svn.foo.com/foo/baz baz\n'
                        'http://svn.foo.com/foo/boo boo')
    expected = {
        'baz': ExternalsDescriptionFromDefaults(),
        'boo': ExternalsDescriptionFromDefaults(dstpath='boo', srcpath='boo')
        }
    self.assertEquals(result, expected)

  @mock.patch.object(externals.ExternalsDescription, 'SourceExists')
  def testSourceDoesNotExist(self, source_exists):
    source_exists.return_value = False
    result = self.Parse('http://svn.foo.com/foo/baz baz')
    self.assertEquals(result, {})

  @mock.patch.object(externals.ExternalsDescription, 'SourceExists')
  def testNoExternalsMap(self, _):
    result = self.Parse('../include/bar bar', externals_map=False)
    expected = {
        'bar': externals.ExternalsDescription(
            'bar', MAIN_REPO, MAIN_REPO_REV - 1, PARENT_DIR + '/include/bar',
            MAIN_REPO_REV - 1)
        }
    self.assertEquals(result, expected)


class ParseLineTest(unittest.TestCase):
  def ParseLine(self, line):
    return externals.ParseLine(
        MAIN_REPO,
        MAIN_REPO_REV,
        PARENT_DIR,
        line,
        EXTERNALS_MAP,
        )

  # The following test cases exercise parsing of the six different allowed
  # formats of externals allowed by SVN. They are named after the numbers
  # assigned to them in the docstring for Parse.
  def testFormat1Simple(self):
    result = self.ParseLine('baz http://svn.foo.com/foo/baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat1Pegged(self):
    """Peg revisions not allowed in Format 1."""
    result = self.ParseLine('baz http://svn.foo.com/foo/baz@1')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz@1', None)
    self.assertEquals(result, expected)

  def testFormat2Int(self):
    result = self.ParseLine('baz -r 5 http://svn.foo.com/foo/baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat2Head(self):
    result = self.ParseLine('baz -r HEAD http://svn.foo.com/foo/baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat2Invalid(self):
    with self.assertRaises(externals.ParseError):
      self.ParseLine('baz -r FOO http://svn.foo.com/foo/baz')

  def testFormat2Pegged(self):
    """Peg revisions not allowed in Format 2."""
    result = self.ParseLine('baz -r 5 http://svn.foo.com/foo/baz@1')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz@1', 5)
    self.assertEquals(result, expected)

  def testFormat3Int(self):
    result = self.ParseLine('baz -r5 http://svn.foo.com/foo/baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat3Head(self):
    result = self.ParseLine('baz -rHEAD http://svn.foo.com/foo/baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat3Invalid(self):
    with self.assertRaises(externals.ParseError):
      self.ParseLine('baz -rFOO http://svn.foo.com/foo/baz')

  def testFormat3Pegged(self):
    """Peg revisions not allowed in Format 3."""
    result = self.ParseLine('baz -r5 http://svn.foo.com/foo/baz@1')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz@1', 5)
    self.assertEquals(result, expected)

  def testFormat4Simple(self):
    result = self.ParseLine('http://svn.foo.com/foo/baz baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat4Int(self):
    result = self.ParseLine('http://svn.foo.com/foo/baz@5 baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat4Head(self):
    result = self.ParseLine('http://svn.foo.com/foo/baz@HeAd baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat4Invalid(self):
    with self.assertRaises(externals.ParseError):
      self.ParseLine('http://svn.foo.com/foo/baz@FOO baz')

  def testFormat5Simple(self):
    result = self.ParseLine('-r 10 http://svn.foo.com/foo/baz baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 10, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat5RevIntPegInt(self):
    result = self.ParseLine('-r 10 http://svn.foo.com/foo/baz@5 baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 10, 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat5RevHeadPegInt(self):
    result = self.ParseLine('-r HEAD http://svn.foo.com/foo/baz@5 baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 'HEAD', 'baz', 5)
    self.assertEquals(result, expected)

  def testFormat5RevIntPegHead(self):
    result = self.ParseLine('-r 5 http://svn.foo.com/foo/baz@HeAD baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 5, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat5RevHeadPegHead(self):
    result = self.ParseLine('-r HEAD http://svn.foo.com/foo/baz@head baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat6Simple(self):
    result = self.ParseLine('-r10 http://svn.foo.com/foo/baz baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 10, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat6RevIntPegInt(self):
    result = self.ParseLine('-r10 http://svn.foo.com/foo/baz@6 baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 10, 'baz', 6)
    self.assertEquals(result, expected)

  def testFormat6RevHeadPegInt(self):
    result = self.ParseLine('-rHEAD http://svn.foo.com/foo/baz@6 baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 'HEAD', 'baz', 6)
    self.assertEquals(result, expected)

  def testFormat6RevIntPegHead(self):
    result = self.ParseLine('-r6 http://svn.foo.com/foo/baz@HeAD baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', 6, 'baz', None)
    self.assertEquals(result, expected)

  def testFormat6RevHeadPegHead(self):
    result = self.ParseLine('-rHEAD http://svn.foo.com/foo/baz@head baz')
    expected = externals.ExternalsDescription(
        'baz', '/svn/foo', None, 'baz', None)
    self.assertEquals(result, expected)

  # The following test cases test that the current revision number - 1 is
  # substituted for HEAD for both the operant and peg revisions.
  def testRevSubstitutionBoth(self):
    result = self.ParseLine('baz http://svn.foo.com/zoo/baz')
    expected = externals.ExternalsDescription(
        'baz', MAIN_REPO, MAIN_REPO_REV - 1, 'baz', MAIN_REPO_REV - 1)
    self.assertEquals(result, expected)

  def testRevSubstitutionRev(self):
    result = self.ParseLine('-r2 http://svn.foo.com/zoo/baz baz')
    expected = externals.ExternalsDescription(
        'baz', MAIN_REPO, 2, 'baz', MAIN_REPO_REV - 1)
    self.assertEquals(result, expected)

  def testRevSubstitutionPeg(self):
    result = self.ParseLine('-rHEAD http://svn.foo.com/zoo/baz@2 baz')
    expected = externals.ExternalsDescription(
        'baz', MAIN_REPO, MAIN_REPO_REV - 1, 'baz', 2)
    self.assertEquals(result, expected)

  def testRevSubstitutionNeither(self):
    result = self.ParseLine('-r1 http://svn.foo.com/zoo/baz@2 baz')
    expected = externals.ExternalsDescription(
        'baz', MAIN_REPO, 1, 'baz', 2)
    self.assertEquals(result, expected)

  # Tests for new format relative URLs
  def testRepoRootRelativeSameRepo(self):
    result = self.ParseLine('^/trunk/bar bar')
    expected = externals.ExternalsDescription(
        'bar', MAIN_REPO, MAIN_REPO_REV - 1, 'trunk/bar', MAIN_REPO_REV - 1)
    self.assertEquals(result, expected)

  def testRepoRootRelativeNewRepo(self):
    result = self.ParseLine('^/../foo/trunk/bar bar')
    expected = externals.ExternalsDescription(
        'bar', '/svn/foo', None, 'trunk/bar', None)
    self.assertEquals(result, expected)

  def testRepoRootRelativeAboveFilesystemRoot(self):
    with self.assertRaisesRegexp(externals.ParseError,
                                 r'above filesystem root'):
      self.ParseLine('^/../../../foo/trunk/bar bar')

  def testPegRelative(self):
    result = self.ParseLine('../baz bar')
    expected = externals.ExternalsDescription(
        'bar', MAIN_REPO, MAIN_REPO_REV - 1, PARENT_DIR + '/baz',
        MAIN_REPO_REV - 1)
    self.assertEquals(result, expected)

  def testSchemeRelative(self):
    with self.assertRaisesRegexp(externals.ParseError, r'Scheme-relative'):
      self.ParseLine('//foo.com/bar bar')

  def testServerRootRelative(self):
    with self.assertRaisesRegexp(externals.ParseError, r'server-relative'):
      self.ParseLine('/svn/bar bar')

  def testUnmappableExternal(self):
    with self.assertRaisesRegexp(externals.ParseError, r'Failed to map'):
      self.ParseLine('http://fake-domain.com fake')

  def testTooFewParts(self):
    with self.assertRaises(externals.ParseError):
      self.ParseLine('bar')

  def testTooManyParts(self):
    with self.assertRaises(externals.ParseError):
      self.ParseLine('-r 5 http://svn/foo bar @5')


class FindExternalPathTest(unittest.TestCase):
  def testSimple(self):
    repo, path = externals._FindExternalPath(
        'http://svn.foo.com/foo/trunk/bar', EXTERNALS_MAP)
    self.assertEquals(repo, '/svn/foo')
    self.assertEquals(path, 'trunk/bar')

  def testRepoRoot(self):
    repo, path = externals._FindExternalPath(
        'http://svn.foo.com/foo', EXTERNALS_MAP)
    self.assertEquals(repo, '/svn/foo')
    self.assertEquals(path, '')

  def testNotFound(self):
    with self.assertRaises(externals.UnknownRepo):
      externals._FindExternalPath(
          'http://svn.bar.com/foo', EXTERNALS_MAP)


@mock.patch('subprocess.Popen', new=test_utils.MockPopen)
class FromRevTest(unittest.TestCase):
  def testSVNFails(self):
    with test_utils.MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'propget', '-r10', MAIN_REPO, 'svn:externals',
                'trunk/foo'),
        'returncode': 1,
        'stdout': 'Bad stdout',
        }):
      result = externals.FromRev(
          MAIN_REPO, 10, 'trunk/foo', EXTERNALS_MAP)
    self.assertEquals(result, {})

  # Don't make external calls to verify that the source exists
  @mock.patch.object(externals.ExternalsDescription, 'SourceExists')
  def testSucceeds(self, _):
    externals_property = 'http://svn.foo.com/foo/baz baz'
    with test_utils.MockPopen.ExpectCommands({
        'cmd': ('svnlook', 'propget', '-r10', MAIN_REPO, 'svn:externals',
                'trunk/foo'),
        'stdout': externals_property
        }):
      result = externals.FromRev(
          MAIN_REPO, 10, 'trunk/foo', EXTERNALS_MAP)
    expected = {
        'baz': externals.ExternalsDescription(
            'baz', '/svn/foo', None, 'baz', None)
        }
    self.assertEquals(result, expected)


if __name__ == '__main__':
  unittest.main()
