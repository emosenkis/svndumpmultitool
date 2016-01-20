# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Tests for svndumpmultitool."""

from __future__ import absolute_import

import unittest

import mock

from svndumpmultitool import svndump
from svndumpmultitool import svndumpmultitool_cli as svndumpmultitool
from svndumpmultitool import util

# Static data
MAIN_REPO = '/svn/zoo'
MAIN_REPO_REV = 5


class FilterFilterRecordTest(unittest.TestCase):
  def setUp(self):
    self.paths = util.PathFilter(['trunk/foo'])
    self.filter = svndumpmultitool.Filter('/svn/foo', self.paths)

  def testExcludedPath(self):
    """Path that does not match the filter should return no Records."""
    record = svndump.Record(kind='file', action='add', path='trunk/bar/baz')
    output = self.filter._FilterRecord(10, record)
    self.assertEquals(output, [])

  def testIncludedPath(self):
    """Path that matches the filter should pass through unchanged."""
    record = svndump.Record(kind='file', action='add', path='trunk/foo/bar')
    output = self.filter._FilterRecord(10, record)
    self.assertEquals(output, [record])

  def testParentDir(self):
    """Parent dir should have its properties stripped."""
    record = svndump.Record(kind='dir', action='add', path='trunk')
    record.SetProperty('foo', 'bar')
    output = self.filter._FilterRecord(10, record)
    self.assertEquals(output, [record])
    self.assertIsNone(record.props)

  def testParentFile(self):
    """Parent file should be replaced with propertyless dir."""
    record = svndump.Record(kind='file', action='add', path='trunk')
    record.SetProperty('foo', 'bar')
    output = self.filter._FilterRecord(10, record)
    # Result should be a single Record
    self.assertEquals(len(output), 1)
    # A new record should be created
    self.assertNotEqual(output[0], record)
    # It should be a propertyless dir with the same path as the input
    self.assertEquals(output[0].headers['Node-kind'], 'dir')
    self.assertEquals(output[0].headers['Node-path'],
                      record.headers['Node-path'])
    self.assertIsNone(output[0].props)

  def testParentChange(self):
    """Parent changes should be ignored."""
    record = svndump.Record(kind='dir', action='change', path='trunk')
    output = self.filter._FilterRecord(10, record)
    self.assertEquals(output, [])

  def testParentDelete(self):
    """Parent deletes should be passed through unchanged."""
    record = svndump.Record(action='delete', path='trunk')
    output = self.filter._FilterRecord(10, record)
    self.assertEquals(output, [record])

  @mock.patch.object(svndumpmultitool.Filter, '_FixCopyFrom')
  def testCopyFromOnParent(self, fix_copy_from):
    """_FixCopyFrom must be called."""
    record = svndump.Record(kind='dir', action='add', path='trunk')
    record.headers['Node-copyfrom-path'] = 'branches/bar'
    record.headers['Node-copyfrom-rev'] = '1'
    fix_copy_from.return_value = ['FIXED']
    output = self.filter._FilterRecord(10, record)
    fix_copy_from.assert_called_once_with(record)
    self.assertEquals(output, fix_copy_from.return_value)

  @mock.patch.object(svndumpmultitool.Filter, '_InternalizeExternals')
  def testPathWithExternals(self, internalize_externals):
    """_InternalizeExternals must be called."""
    # externals_map must not be empty to trigger internalizing externals
    self.filter.externals_map = {'foo': 'bar'}
    record = svndump.Record(kind='dir', action='add', path='trunk/foo/bar')
    record.SetProperty('svn:externals', 'foo')
    internalize_externals.return_value = ['FIXED']
    output = self.filter._FilterRecord(10, record)
    internalize_externals.assert_called_once_with(10, record)
    self.assertEquals(output, internalize_externals.return_value)

  @mock.patch.object(svndumpmultitool.Filter, '_InternalizeExternals')
  def testPathWithExternalsDisabled(self, internalize_externals):
    """_InternalizeExternals must not be called when no externals map exists."""
    record = svndump.Record(kind='dir', action='add', path='trunk/foo/bar')
    record.SetProperty('svn:externals', 'foo')
    output = self.filter._FilterRecord(10, record)
    self.assertFalse(internalize_externals.called)
    self.assertEquals(output, [record])


class FilterFixCopyFromTest(unittest.TestCase):
  # TODO: complete test coverage of _FixCopyFrom

  @mock.patch.object(util.PathFilter, 'CheckPath',
                     return_value=util.PathFilter.PARENT)
  @mock.patch.object(svndump, 'MakeRecordsFromPath')
  def testCopyParentToParent(self, grab_records, _):
    filt = svndumpmultitool.Filter(MAIN_REPO, util.PathFilter([]))
    record = svndump.Record(action='add', path='foo', kind='dir')
    record.headers['Node-copyfrom-rev'] = '10'
    record.headers['Node-copyfrom-path'] = 'foo'
    result = filt._FixCopyFrom(record)
    self.assertEquals(len(result), 1)
    result = result[0]
    self.assertEquals(result.headers['Node-copyfrom-rev'], '10')
    self.assertEquals(result.headers['Node-copyfrom-path'], 'foo')
    self.assertFalse(grab_records.called)


class FilterFlattenMultipleActionsTest(unittest.TestCase):

  # Autospec causes the mock to receive self as its first arg
  @mock.patch.object(svndumpmultitool.Filter._ActionPairFlattener, 'Flatten',
                     autospec=True)
  def testRunThroughPairs(self, flatten):
    filt = svndumpmultitool.Filter(MAIN_REPO, util.PathFilter([]))
    contents = []
    # Add three Records for one path, three Records for another, and one Record
    # for a third
    contents.append(svndump.Record(path='foo', action='add', kind='file'))
    contents.append(svndump.Record(path='foo', action='change', kind='file'))
    contents.append(svndump.Record(path='foo', action='delete', kind='file'))
    contents.append(svndump.Record(path='bar', action='add', kind='dir'))
    contents.append(svndump.Record(path='bar', action='change', kind='dir'))
    contents.append(svndump.Record(path='bar', action='delete', kind='dir'))
    contents.append(svndump.Record(path='baz', action='add', kind='dir'))
    def Flatten(self):
      self.records.pop(0)
      self.contents.pop(0)
    flatten.side_effect = Flatten
    filt._FlattenMultipleActions(MAIN_REPO_REV, contents)
    self.assertEqual(len(contents), 3)
    self.assertEqual(flatten.call_count, 4)

  def testAddAddDelete(self):
    filt = svndumpmultitool.Filter(MAIN_REPO, util.PathFilter([]))
    contents = []
    contents.append(svndump.Record(path='foo', action='add', kind='file'))
    contents.append(svndump.Record(path='foo', action='add', kind='file'))
    contents.append(svndump.Record(path='foo', action='delete', kind='file'))
    filt._FlattenMultipleActions(MAIN_REPO_REV, contents)
    self.assertFalse(contents)

  def testAddChangeDelete(self):
    filt = svndumpmultitool.Filter(MAIN_REPO, util.PathFilter([]))
    contents = []
    contents.append(svndump.Record(path='foo', action='add', kind='file'))
    contents.append(svndump.Record(path='foo', action='change', kind='file'))
    contents.append(svndump.Record(path='foo', action='delete', kind='file'))
    filt._FlattenMultipleActions(MAIN_REPO_REV, contents)
    self.assertFalse(contents)

  def testDeleteAddChange(self):
    filt = svndumpmultitool.Filter(MAIN_REPO, util.PathFilter([]))
    contents = []
    contents.append(svndump.Record(path='foo', action='delete', kind='file'))
    contents.append(svndump.Record(path='foo', action='add', kind='file'))
    contents.append(svndump.Record(path='foo', action='change', kind='file'))
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
    self.assertEqual(apf.records, range(5))
    self.assertEqual(apf.first, 0)
    self.assertEqual(apf.second, 1)

  def MakeActionPairFlattener(self, action1, action2):
    if action1 == 'delete':
      first = svndump.Record(path='foo', action=action1)
    else:
      first = svndump.Record(path='foo', kind='file', action=action1)
    if action2 == 'delete':
      second = svndump.Record(path='foo', action=action2)
    else:
      second = svndump.Record(path='foo', kind='file', action=action2)
    contents = [first, second]
    records = [first, second]
    apf = svndumpmultitool.Filter._ActionPairFlattener(MAIN_REPO, MAIN_REPO_REV,
                                                     contents, 'trunk', records)
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
    with self.assertRaises(svndumpmultitool.UnsupportedActionPair):
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
    apf.first.source = svndump.Record.EXTERNALS
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
      with self.assertRaises(svndumpmultitool.UnsupportedActionPair):
        apf.Flatten()


class FilterFilterRevTest(unittest.TestCase):
  def testTruncateRevs(self):
    filt = svndumpmultitool.Filter(MAIN_REPO, util.PathFilter([]),
                                 truncate_revs=[2])
    record = svndump.Record(path='trunk', action='add', kind='file')
    good_revhdr = svndump.Record()
    good_revhdr.headers['Revision-number'] = '1'
    self.assertTrue(filt._FilterRev(good_revhdr, [record]))
    bad_revhdr = svndump.Record()
    bad_revhdr.headers['Revision-number'] = '2'
    self.assertFalse(filt._FilterRev(bad_revhdr, [record]))

  def testDeleteProps(self):
    filt = svndumpmultitool.Filter(MAIN_REPO, util.PathFilter([]),
                                 delete_properties=['bad-property'])
    record = svndump.Record(path='trunk', action='add', kind='file')
    record.SetProperty('bad-property', 'bad-value')
    record.SetProperty('good-property', 'good-value')
    revhdr = svndump.Record()
    revhdr.headers['Revision-number'] = MAIN_REPO_REV
    self.assertTrue(filt._FilterRev(revhdr, [record]))
    self.assertNotIn('bad-property', record.props)
    self.assertIn('good-property', record.props)

  def testDropActions(self):
    filt = svndumpmultitool.Filter(MAIN_REPO, util.PathFilter([]),
                                 drop_actions={1: set(['foo'])})
    revhdr = svndump.Record()
    revhdr.headers['Revision-number'] = '1'
    records = [
        svndump.Record(path='foo', action='add'),
        svndump.Record(path='foo', action='delete'),
        svndump.Record(path='bar', action='edit')
    ]
    result = filt._FilterRev(revhdr, records)
    expect = [svndump.Record(path='bar', action='edit')]
    self.assertEqual(result, expect)

  def testForceDelete(self):
    force_delete = {
        1: ['foo', 'foo', 'bar'],
        2: [''],
    }
    filt = svndumpmultitool.Filter(MAIN_REPO, util.PathFilter([]),
                                 force_delete=force_delete)
    revhdr = svndump.Record()
    revhdr.headers['Revision-number'] = '1'
    result = filt._FilterRev(revhdr, [])
    expect = [
        svndump.Record(path='foo', action='delete'),
        svndump.Record(path='foo', action='delete'),
        svndump.Record(path='bar', action='delete')
    ]
    self.assertEqual(result, expect)
    revhdr.headers['Revision-number'] = '2'
    result = filt._FilterRev(revhdr, [])
    expect = [svndump.Record(path='', action='delete')]
    self.assertEqual(result, expect)
    revhdr.headers['Revision-number'] = '3'
    result = filt._FilterRev(revhdr, [])
    self.assertEqual(result, [])


if __name__ == '__main__':
  unittest.main()
