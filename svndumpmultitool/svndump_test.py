# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Tests for svndump."""

from __future__ import absolute_import

import collections
import io
import StringIO
import unittest

import mock

from svndumpmultitool import svndump

# Static data
MAIN_REPO = '/svn/zoo'
MAIN_REPO_REV = 5


class RecordConstructorTest(unittest.TestCase):
  def testSimple(self):
    record = svndump.Record()
    self.assertFalse(record.headers)
    self.assertIsNone(record.props)
    self.assertIsNone(record.text)
    self.assertIs(record.source, record.DUMP)

  def testPath(self):
    record = svndump.Record(path='foo')
    self.assertEqual(record.headers['Node-path'], 'foo')
    self.assertEqual(len(record.headers), 1)
    self.assertIsNone(record.props)
    self.assertIsNone(record.text)

  def testAction(self):
    record = svndump.Record(action='foo')
    self.assertEqual(record.headers['Node-action'], 'foo')
    self.assertEqual(len(record.headers), 1)
    self.assertIsNone(record.props)
    self.assertIsNone(record.text)

  def testKind(self):
    record = svndump.Record(kind='foo')
    self.assertEqual(record.headers['Node-kind'], 'foo')
    self.assertEqual(len(record.headers), 1)
    self.assertIsNone(record.props)
    self.assertIsNone(record.text)

  def testSource(self):
    record = svndump.Record(source=svndump.Record.COPY)
    self.assertFalse(record.headers)
    self.assertIsNone(record.props)
    self.assertIsNone(record.text)
    self.assertIs(record.source, record.COPY)


class RecordDeleteHeaderTest(unittest.TestCase):
  def testExists(self):
    record = svndump.Record()
    record.headers['foo'] = 'bar'
    record.DeleteHeader('foo')
    self.assertNotIn('foo', record.headers)

  def testDoesNotExist(self):
    record = svndump.Record()
    record.DeleteHeader('foo')
    # We're just checking that it doesn't raise an exception


class ParsePropsTest(unittest.TestCase):
  def testSimple(self):
    props = svndump._ParseProps('K 3\nfoo\nV 3\nbar\nPROPS-END\n')
    self.assertEquals(props['foo'], 'bar')

  def testMultiple(self):
    props = svndump._ParseProps('K 3\nfoo\nV 3\nbar\n'
                                'K 3\nbar\nV 3\nbaz\n'
                                'D 3\nbaz\n'
                                'PROPS-END\n')
    self.assertEquals(props['foo'], 'bar')
    self.assertEquals(props['bar'], 'baz')
    self.assertIsNone(props['baz'])

  def testWithNewline(self):
    """Keys and values with newlines in them should just work."""
    props = svndump._ParseProps(
        'K 7\n\nf\no\no\n\nV 7\n\nb\na\nr\n\nPROPS-END\n')
    self.assertEquals(props['\nf\no\no\n'], '\nb\na\nr\n')

  def testDelete(self):
    props = svndump._ParseProps('D 3\nfoo\nPROPS-END\n')
    self.assertIsNone(props['foo'])

  def testEmpty(self):
    props = svndump._ParseProps('PROPS-END\n')
    self.assertFalse(props)

  def testMissingPropsEnd(self):
    with self.assertRaises(svndump.PropsParseError):
      svndump._ParseProps('D 3\nfoo\n')

  def testTruncated(self):
    with self.assertRaises(IndexError):
      svndump._ParseProps('K 3\nfoo\nV 100\nfoo')

  def testUnknownFormat(self):
    with self.assertRaises(svndump.PropsParseError):
      svndump._ParseProps('Z 3\nPROPS-END\n')


class RecordSetPropertyTest(unittest.TestCase):
  def setUp(self):
    self.record = svndump.Record()

  def testFirstProperty(self):
    self.record.SetProperty('foo', 'bar')
    self.assertEquals(self.record.props['foo'], 'bar')

  def testNotFirstProperty(self):
    self.record.SetProperty('foo', 'bar')
    self.record.SetProperty('bar', 'baz')
    self.assertEquals(self.record.props['foo'], 'bar')
    self.assertEquals(self.record.props['bar'], 'baz')


class RecordDeletePropertyTest(unittest.TestCase):
  def setUp(self):
    self.record = svndump.Record()

  def testExists(self):
    self.record.SetProperty('foo', 'bar')
    self.record.DeleteProperty('foo')
    self.assertNotIn('foo', self.record.props)

  def testDoesNotExist(self):
    self.record.SetProperty('bar', 'baz')
    self.record.DeleteProperty('foo')
    # Just making sure no exception is raised

  def testPropsIsNone(self):
    self.record.DeleteProperty('foo')
    # Just making sure no exception is raised


class RecordGeneratePropTextTest(unittest.TestCase):
  def setUp(self):
    self.record = svndump.Record()

  def testSimple(self):
    self.record.SetProperty('foo', 'bar')
    self.assertEquals(self.record._GeneratePropText(),
                      'K 3\nfoo\nV 3\nbar\nPROPS-END\n')

  def testMultiple(self):
    self.record.SetProperty('foo', 'bar')
    self.record.SetProperty('bar', 'baz')
    self.record.SetProperty('baz', None)
    self.assertEquals(self.record._GeneratePropText(),
                      'K 3\nfoo\nV 3\nbar\n'
                      'K 3\nbar\nV 3\nbaz\n'
                      'D 3\nbaz\n'
                      'PROPS-END\n')

  def testDelete(self):
    self.record.SetProperty('foo', None)
    self.assertEquals(self.record._GeneratePropText(), 'D 3\nfoo\nPROPS-END\n')

  def testEmpty(self):
    self.record.SetProperty('foo', 'bar')
    self.record.DeleteProperty('foo')
    self.assertEquals(self.record._GeneratePropText(), 'PROPS-END\n')

  def testNoPropertiesBlock(self):
    self.assertEquals(self.record._GeneratePropText(), '')


class RecordFixHeadersTest(unittest.TestCase):
  def testPropContentLength(self):
    record = svndump.Record()
    record.headers['Prop-content-length'] = '1'
    record.SetProperty('foo', 'bar')
    proptext = record._GeneratePropText()
    record._FixHeaders(proptext, None)
    self.assertEquals(record.headers['Prop-content-length'],
                      str(len(proptext)))

  def testDeletePropContentLength(self):
    record = svndump.Record()
    record.headers['Prop-content-length'] = '1'
    proptext = record._GeneratePropText()
    record._FixHeaders(proptext, None)
    self.assertNotIn('Prop-content-length', record.headers)

  def testSetTextContentLength(self):
    record = svndump.Record()
    record.text = 'foo'
    record._FixHeaders('', None)
    self.assertEquals(record.headers['Text-content-length'], '3')

  def testSetTextContentMD5(self):
    record = svndump.Record()
    record.text = 'foo'
    record._FixHeaders('', None)
    self.assertEquals(record.headers['Text-content-md5'],
                      'acbd18db4cc2f85cedef654fccc4a4d8')

  def testLeaveTextDeltaAlone(self):
    record = svndump.Record()
    record.headers['Text-delta'] = 'true'
    record.headers['Text-content-md5'] = 'foo'
    record.text = 'foo'
    record._FixHeaders('', None)
    self.assertEquals(record.headers['Text-content-md5'], 'foo')
    self.assertEquals(record.headers['Text-content-length'], '3')

  def testDeleteTextHeaders(self):
    record = svndump.Record()
    record.headers['Text-content-length'] = '3'
    record.headers['Text-content-md5'] = 'foo'
    record.headers['Text-content-sha1'] = 'bar'
    record.headers['Text-delta'] = 'baz'
    record._FixHeaders('', None)
    self.assertNotIn('Text-content-length', record.headers)
    self.assertNotIn('Text-content-md5', record.headers)
    self.assertNotIn('Text-content-sha1', record.headers)
    self.assertNotIn('Text-delta', record.headers)

  def testSetContentLength(self):
    record = svndump.Record()
    record.headers['Content-length'] = '10'
    record.text = 'foo'
    proptext = 'bar'
    record._FixHeaders(proptext, None)
    self.assertEquals(record.headers['Content-length'], '6')

  def testRevmapRevision(self):
    record = svndump.Record()
    record.headers['Revision-number'] = '10'
    revmap = {10: 20}
    record._FixHeaders('', revmap)
    self.assertEquals(record.headers['Revision-number'], '20')

  def testRevmapCopyFrom(self):
    record = svndump.Record()
    record.headers['Node-copyfrom-rev'] = '10'
    revmap = {10: 20}
    record._FixHeaders('', revmap)
    self.assertEquals(record.headers['Node-copyfrom-rev'], '20')


class _ReadRFC822HeadersTest(unittest.TestCase):
  def testSimple(self):
    stream = StringIO.StringIO('foo: bar\n\n')
    result = svndump._ReadRFC822Headers(stream)
    self.assertEquals(result.headers['foo'], 'bar')

  def testMultiple(self):
    stream = StringIO.StringIO('foo: bar\nbar: baz\n\n')
    result = svndump._ReadRFC822Headers(stream)
    self.assertEquals(result.headers['foo'], 'bar')
    self.assertEquals(result.headers['bar'], 'baz')

  def testBlankLines(self):
    stream = StringIO.StringIO('\n\nfoo: bar\n\n')
    result = svndump._ReadRFC822Headers(stream)
    self.assertEquals(result.headers['foo'], 'bar')

  def testColonInValue(self):
    stream = StringIO.StringIO('foo: b:a:r\n\n')
    result = svndump._ReadRFC822Headers(stream)
    self.assertEquals(result.headers['foo'], 'b:a:r')

  def testInvalid(self):
    stream = StringIO.StringIO('foobar\n\n')
    with self.assertRaises(ValueError):
      svndump._ReadRFC822Headers(stream)

  def testEOF(self):
    stream = StringIO.StringIO('')
    result = svndump._ReadRFC822Headers(stream)
    self.assertIsNone(result)

  def testTruncated(self):
    stream = StringIO.StringIO('foo: bar')
    with self.assertRaises(EOFError):
      svndump._ReadRFC822Headers(stream)
    # A trailing blank line is needed to end headers
    stream = StringIO.StringIO('foo: bar\n')
    with self.assertRaises(EOFError):
      svndump._ReadRFC822Headers(stream)


class ReadRecordTest(unittest.TestCase):
  def testEOF(self):
    stream = StringIO.StringIO('\n')
    result = svndump.ReadRecord(stream)
    self.assertIsNone(result)

  def testHeadersOnly(self):
    stream = StringIO.StringIO('foo: bar\n\n')
    result = svndump.ReadRecord(stream)
    self.assertEquals(result.headers['foo'], 'bar')
    self.assertIsNone(result.props)
    self.assertIsNone(result.text)

  def testProps(self):
    stream = StringIO.StringIO('Prop-content-length: 26\n\n'
                               'K 3\nfoo\nV 3\nbar\nPROPS-END\n')
    result = svndump.ReadRecord(stream)
    self.assertEquals(result.props['foo'], 'bar')
    self.assertIsNone(result.text)

  def testText(self):
    text = 'Some text\nSome more text'
    stream = StringIO.StringIO('Text-content-length: %s\n\n%s'
                               % (len(text), text))
    result = svndump.ReadRecord(stream)
    self.assertEquals(result.text, text)
    self.assertIsNone(result.props)

  def testBoth(self):
    stream = StringIO.StringIO('Text-content-length: 3\n'
                               'Prop-content-length: 26\n\n'
                               'K 3\nfoo\nV 3\nbar\nPROPS-END\n'
                               'foo\n')
    result = svndump.ReadRecord(stream)
    self.assertEquals(result.text, 'foo')
    self.assertEquals(result.props['foo'], 'bar')


class RecordWriteTest(unittest.TestCase):
  def setUp(self):
    self.stream = StringIO.StringIO()
    self.record = svndump.Record()

  def testJustHeaders(self):
    self.record.headers['foo'] = 'bar'
    self.record.Write(self.stream, None)
    self.assertEquals(self.stream.getvalue(), 'foo: bar\n\n')

  def testText(self):
    self.record.text = 'foo'
    self.record.Write(self.stream, None)
    self.assertEquals(self.stream.getvalue(),
                      'Text-content-length: 3\n'
                      'Text-content-md5: acbd18db4cc2f85cedef654fccc4a4d8\n'
                      'Content-length: 3\n\n'
                      'foo\n\n')

  def testProps(self):
    self.record.headers['foo'] = 'bar'
    self.record.SetProperty('bar', 'baz')
    self.record.Write(self.stream, None)
    self.assertEquals(self.stream.getvalue(),
                      'foo: bar\n'
                      'Prop-content-length: 26\n'
                      'Content-length: 26\n\n'
                      'K 3\nbar\nV 3\nbaz\nPROPS-END\n\n')

  def testBoth(self):
    self.record.headers['foo'] = 'bar'
    self.record.SetProperty('bar', 'baz')
    self.record.Write(self.stream, None)
    self.record.text = 'foo'
    self.assertEquals(self.stream.getvalue(),
                      'foo: bar\n'
                      'Prop-content-length: 26\n'
                      'Content-length: 26\n\n'
                      'K 3\nbar\nV 3\nbaz\nPROPS-END\n\n')


class RecordDoesNotAffectExternalsTest(unittest.TestCase):
  def testDelete(self):
    record = svndump.Record(action='delete')
    record.SetProperty('svn:externals', 'foo')
    self.assertEquals(record.DoesNotAffectExternals(), True)

  def testFile(self):
    record = svndump.Record(kind='file', action='change')
    record.SetProperty('svn:externals', 'foo')
    self.assertEquals(record.DoesNotAffectExternals(), True)

  def testNoPropertiesBlock(self):
    record = svndump.Record(kind='dir', action='change')
    self.assertEquals(record.DoesNotAffectExternals(), True)

  def testExplicitModification(self):
    record = svndump.Record(kind='dir', action='change')
    record.SetProperty('svn:externals', 'foo')
    self.assertEquals(record.DoesNotAffectExternals(), False)

  def testExplicitDeletion(self):
    record = svndump.Record(kind='dir', action='change')
    record.headers['Prop-delta'] = 'true'
    record.SetProperty('svn:externals', None)
    self.assertEquals(record.DoesNotAffectExternals(), False)

  def testAdd(self):
    record = svndump.Record(kind='dir', action='add')
    record.SetProperty('garbage', 'foo')
    self.assertEquals(record.DoesNotAffectExternals(), True)

  def testPropDeltaTrue(self):
    record = svndump.Record(kind='dir', action='change')
    record.headers['Prop-delta'] = 'true'
    record.SetProperty('garbage', 'foo')
    self.assertEquals(record.DoesNotAffectExternals(), True)

  def testPossibleDeleteByOmission(self):
    record = svndump.Record(kind='dir', action='change')
    record.SetProperty('garbage', 'foo')
    self.assertEquals(record.DoesNotAffectExternals(), False)


class MakeRecordsFromPathTest(unittest.TestCase):

  @mock.patch.object(svndump, 'svn_core')
  @mock.patch.object(svndump, 'svn_repos')
  @mock.patch.object(svndump, 'svn_fs')
  def testGrabRecords(self, fs, unused_repos, core):
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
    results = svndump.MakeRecordsFromPath(
        MAIN_REPO, MAIN_REPO_REV, '', 'bar', svndump.Record.COPY)
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

  @mock.patch.object(svndump, 'svn_core')
  @mock.patch.object(svndump, 'svn_repos')
  @mock.patch.object(svndump, 'svn_fs')
  def testGrabRecordsWithSrcPath(self, fs, unused_repos, core):
    fs.is_dir.return_value = False
    fs.file_contents.return_value = io.BytesIO('foo')
    core.svn_stream_read = lambda stream, size: stream.read(size)
    fs.file_md5_checksum.return_value = 'foo_checksum'
    fs.node_proplist.return_value = {}
    results = svndump.MakeRecordsFromPath(MAIN_REPO, MAIN_REPO_REV,
                                          'foo/bar', 'baz',
                                          svndump.Record.EXTERNALS)
    self.assertEqual(len(results), 1)
    self.assertEqual(results[0].headers['Node-path'], 'baz')
    self.assertEqual(results[0].source, svndump.Record.EXTERNALS)


if __name__ == '__main__':
  unittest.main()
