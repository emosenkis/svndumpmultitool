# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Utilities for parsing, modifying, and writing SVN dump files.

http://svn.apache.org/repos/asf/subversion/trunk/notes/dump-load-format.txt
"""

from __future__ import absolute_import

import collections
import md5
import sys

from svn import core as svn_core
from svn import fs as svn_fs
from svn import repos as svn_repos


class Error(Exception):
  """Parent class for this module's errors."""


class PropsParseError(Error):
  """Failure to parse a Record's properties block."""


class Record(object):
  """A record of RFC822-ish headers-plus-data from an SVN dump file.

  Attributes:
    headers: {str: str} OrderedDict representing the headers section
    props: {str: str} OrderedDict representing the properties section, or None
           if no properties section
    text: str text content or None if no text content
    source: constant value for internal use only representing the source of the
            Record (see comments on DUMP, COPY, EXTERNALS).
  """
  DUMP = 0  # Record was read from the dump file being filtered
  COPY = 1  # Record was created to dereference a copy action
  EXTERNALS = 2  # Record was internalize an external path

  def __init__(self, path=None, action=None, kind=None, source=DUMP):
    """Create a new Record.

    Args:
      path: Node-path header value
      action: Node-action header value
      kind: Node-kind header value
      source: Source of this Record (DUMP, COPY, or EXTERNALS)

    path, action, and kind arguments are merely helpers to set the most commonly
    used headers.
    """
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
    self.headers.pop(key, None)

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
    _FilterRev() instead because _FixHeaders should be idempotent.

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
    if not proptext and self.text is None:
      self.DeleteHeader('Content-length')
    else:
      try:
        textlen = len(self.text)
      except TypeError:
        textlen = 0
      self.headers['Content-length'] = str(len(proptext) + textlen)
    # Adjust the revision numbers as needed.
    # TODO revmap needs to be persisted across executions of this
    # script or else copies from old revisions will refer to the wrong revision
    # See help for flag --drop-empty-revs for current restrictions.
    if revmap:
      for header in ['Revision-number', 'Node-copyfrom-rev']:
        if header in self.headers:
          old_rev = int(self.headers[header])
          self.headers[header] = str(revmap[old_rev])

  def Write(self, stream, revmap):
    """Write a Record to the given file-like object.

    Args:
      stream: a writeable file-like object
      revmap: a dict mapping old revision number to new revision number

    This calls _FixHeaders to ensure that the Record's headers are consistent
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
    """Can a Record be determined to NOT affect svn:externals in any way?

    Returns:
      True if the Record can be proven to not have any effect on the
      svn:externals property, False if this cannot be proven

    In most cases, it's quite obvious whether svn:externals is affected because
    the svn:externals property will be set on the Record. However, the
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

  def __eq__(self, other):
    return (isinstance(other, type(self))
            and self.headers == other.headers
            and self.props == other.props
            and self.text == other.text)


def ReadRecord(stream):
  """Read a Record from the given file-like object.

  Args:
    stream: a readable file-like object

  Returns:
    a Record read from stream or None if EOF is reached
  """
  record = _ReadRFC822Headers(stream)
  if record is None:
    return None
  pcl = int(record.headers.get('Prop-content-length', '0'))
  if pcl > 0:
    record.props = _ParseProps(stream.read(pcl))
  if 'Text-content-length' in record.headers:
    tcl = int(record.headers['Text-content-length'])
    record.text = stream.read(tcl)
  return record


def _ReadRFC822Headers(stream):
  """Create a Record with headers populated by reading from a stream.

  Args:
    stream: a file-like stream

  Returns:
    a Record if parsing succeeds or None if stream was empty

  Raises:
    EOFError: if EOF is reached before a blank line indicating the end of the
              headers section

  Helper for Read().
  """
  record = Record()
  while True:
    # It is necessary to use readline() instead of iterating over stream because
    # the file iterator keeps its own internal buffer, causing future uses of
    # stream.read() to raise 'ValueError: Mixing iteration and read methods
    # would lose data'
    line = stream.readline()
    if not line:  # EOF
      break
    if line == '\n':
      if record.headers:
        return record
      else:
        continue  # newline before headers is simply ignored
    line = line.rstrip('\n')
    key, val = line.split(': ', 1)
    record.headers[key] = val
  # EOF was reached without a blank line
  if record.headers:
    raise EOFError('Reached EOF while reading headers')
  else:
    # EOF is ok if no headers are found first
    return None


def _ParseProps(proptext):
  """Parses the given property string into an OrderedDict.

  Args:
    proptext: a string containing the properties block of a Record

  Returns:
    an OrderedDict containing the parsed properties

  Raises:
    PropsParseError: if parsing fails

  Excerpted from
  http://svn.apache.org/repos/asf/subversion/trunk/notes/dump-load-format.txt:

  A property section consists of pairs of key and value records and
  is ended by a fixed trailer.  Here is an example attached to a
  Revision record:

  -------------------------------------------------------------------
  Revision-number: 1422
  Prop-content-length: 80
  Content-length: 80

  K 6
  author
  V 7
  sussman
  K 3
  log
  V 33
  Added two files, changed a third.
  PROPS-END
  -------------------------------------------------------------------

  The fixed trailer is "PROPS-END\n" and its length is included in the
  Prop-content-length. Before it, each K and V record consists of a
  header line giving the length of the key or value content in bytes.
  The content follows.  The content is itself always followed by \n.

  In version 3 of the format, a third type 'D' of property record is
  introduced to describe property deletion.
  """
  # TODO use BytesIO to clean this up
  props = collections.OrderedDict()
  index = 0
  while True:
    if proptext[index:index+2] == 'K ':
      wantval = True
    elif proptext[index:index+2] == 'D ':
      wantval = False
    elif proptext[index:index+9] == 'PROPS-END':
      break
    else:
      raise PropsParseError('Unrecognised record in %r' % proptext[index:])
    nlpos = proptext.find('\n', index)
    if nlpos <= 0:
      raise PropsParseError('Missing newline after name length in %r'
                            % proptext[index:])
    namelen = int(proptext[index+2:nlpos])
    if proptext[nlpos+1+namelen] != '\n':
      raise PropsParseError('Missing newline after name in %r'
                            % proptext[index:])
    name = proptext[nlpos+1:nlpos+1+namelen]
    index = nlpos+2+namelen
    if wantval:
      if proptext[index:index+2] != 'V ':
        raise PropsParseError('Expected "V ...", got %r' % proptext[index:])
      nlpos = proptext.find('\n', index)
      if nlpos <= 0:
        raise PropsParseError('Missing newline after value length in %r'
                              % proptext[index:])
      proplen = int(proptext[index+2:nlpos])
      if proptext[nlpos+1+proplen] != '\n':
        raise PropsParseError('Missing newline after value in %r'
                              % proptext[index:])
      prop = proptext[nlpos+1:nlpos+1+proplen]
      index = nlpos+2+proplen
    else:
      prop = None
    props[name] = prop
  if len(proptext) != index + 10:
    raise PropsParseError('Trailing characters after PROPS-END: %s'
                          % proptext[index:])
  return props


def MakeRecordsFromPath(srcrepo, srcrev, srcpath, dstpath, record_source):
  """Generate Records adding the contents of a given repo/rev/path.

  Args:
    srcrepo: path to the source repository
    srcrev: revision number
    srcpath: path within the source repository
    dstpath: destination path in the repository being filtered
    record_source: the source attribute of the Records generated

  Returns:
    a list of Records

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
  The dump file is parsed into Records, the paths have the destination path
  prepended, and the Records are inserted into the dump.

  Unfortunately, svnrdump always produces format 3 dumps which use deltas. Even
  though it was only used for a single non-incremental revision, every file's
  contents were in the form of a delta. Since some tools (such as p4convert-svn)
  do not support deltas, svnrdump was done away with, replaced by the SVN SWIG
  bindings.

  It turns out that this same functionality is critical to 'internalizing' SVN
  externals. By generating Records that add all of the files and directories in
  the repo/rev/path referenced by an svn:external property, the history can be
  made to look as though the actual files had been there all along, not just a
  reference to them. Further filtering of these generated Records must be done
  in the case of externals to delete externals when they are removed and modify
  the filesystem when the revision is changed, rather than deleting and reading
  it every time (see externals.FromRev, externals.Diff, Diff).
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
      record = Record(action='add', kind='dir', path=node_path,
                      source=record_source)
      # Add children to the stack
      prefix = (path + '/') if path else ''
      for name in svn_fs.dir_entries(root, path).keys():
        stack.append(prefix + name)
    else:
      record = Record(action='add', kind='file', path=node_path,
                      source=record_source)
      # Fetch file content
      stream = svn_fs.file_contents(root, path)
      record.text = _ReadSVNStream(stream)
      checksum = svn_fs.file_md5_checksum(root, path)
      record.headers['Text-content-md5'] = checksum.encode('hex_codec')
    # Fetch properties
    props = svn_fs.node_proplist(root, path)
    record.props = {key: str(value) for key, value in props.iteritems()}
    output.append(record)
  return output


def _ReadSVNStream(stream):
  """Read an entire SVN stream into a string.

  Args:
    stream: an SVN stream

  Returns:
    str containing entire stream
  """
  out = ''
  while True:
    data = svn_core.svn_stream_read(stream, 16384)
    if not data:
      break
    out += data
  return out
