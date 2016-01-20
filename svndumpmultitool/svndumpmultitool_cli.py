#!/usr/bin/python2.7

# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Filter SVN dump files in various ways.

This script takes an SVN dump file on stdin, applies various filtering
operations to the history represented by the dump file, and prints the resulting
dump file to stdout. A number of different filtering operations are available,
each enabled by command-line flag. Multiple operations can be used at the same
time. If run without any operations enabled, the script will validate the dump
file's structure and output the same dump file to stdout.

Dependencies:
- Python v2.7.x
- Subversion v1.7 or higher
- Subversion API SWIG bindings for Python (NOT the pysvn library)

Operations:
  Path filtering (--include):
    Each argument to --include is a regular expression. Only paths that
    match one or more --include regexps will be included in the output. A path
    whose ancestor directory matches a regexp will also be included. A path that
    could be the ancestor directory for a path that matches the regexp will be
    included as a directory without properties, even if originally it was a file
    or it had properties.

    The regular expressions accepted by --include are based on standard Python
    regular expressions, but have one major difference: they are broken into
    /-separated pieces and applied to one /-separated path segment at a time.
    See [1] for detailed examples of how this works.

    It is usually necessary to provide --repo when using --include. See [2] for
    details.

    See "Limitations" and --drop-empty-revs below.

    Examples:
    --include=foo
    Includes: foo, foo/bar
    Excludes: trunk/foo

    --include=branches/v.*/foo
    Includes: branches/v1/foo, branches/v2/foo/bar
    Excludes: branches/foo, branches/v1/x/foo, branches/bar
    Includes as directory w/out properties: branches

  Externals (--externals-map):
    If the --externals-map argument is provided, the filter will attempt to
    alter the history such that whenever SVN externals[3] are included using the
    svn:externals property, the contents referenced therein are fetched from
    their source repository and inserted in the output stream as if they had
    been physically included in the main repository from the beginning.

    In order to internalize SVN externals, a local copy of each referenced
    repository is required, as well as a mapping from the URLs used to reference
    it to the local path at which it resides. A file providing this mapping must
    be passed as the value of --externals-map. Only externals using URLs
    included in the map will be internalized.

    See "Limitations" below.

    Example:
      --externals-map=/path/to/my/externals.map

  Revision cancellation (--truncate-rev):
    The value for --truncate-rev should be a revision number. All changes to the
    repository that occurred in that revision will be dropped (commit messages
    are retained). This is extremely dangerous because future revisions will
    still expect the revision to have taken effect. There are a few cases when
    it is safe to use --truncate-rev:

    1. If used on a pair of revisions that cancel each other out (e.g.
       --truncate-rev=108 --truncate-rev=109, where r108 deletes trunk, r109
       copies trunk from r107).
    2. If used on a revision that modifies files/directories, but does not add
       or remove them.

    --truncate-rev may be given more than once to truncate multiple revisions.

    See also --drop-empty-revs.

  Property deletion (--delete-property):
    The SVN property given as the value for --delete-property will be stripped
    from all paths. --delete-property can be specified more than once to delete
    multiple properties.

    Examples:
      --delete-property=svn:keywords (to turn off keyword expansion)
      --delete-property=svn:special (to convert symlinks to regular files
        containing 'link <link-target>')

  Handling of empty revisions (--drop-empty-revs, --renumber-revs):
    There are two cases that can result in revisions that perform no actions on
    the repository:
    1. All paths originally affected by the revision are excluded by the path
       filters.
    2. --truncate-rev was used to explicitly cancel all actions from the
       revision.
    By default, these empty revisions are included in the output dump stream. If
    --drop-empty-revs is used, empty revisions are instead dropped from the
    output. If --renumber-revs is used in addition to --drop-empty-revs, the
    following revisions will be renumbered to eliminate the gap left by the
    deleted revision.

    See "Limitations" below.

Limitations:
  Externals:
    - If an externals definition imports the external into a subdirectory, that
      subdirectory will not be automatically created.
    - Currently, the svn:externals property is not modified or deleted when
      externals are internalized.

  Revision renumbering:
    The revision mapping used by --renumber-revs to ensure that copy operations
    point to the correct source is not propagated across multiple invocations of
    the script. This makes it unsuitable for use on incremental dumps.

  Testing:
    Unit testing is approximately 80% complete. End-to-end testing has not been
    started yet.

Use as a library:
  svndumpmultitool can be used as a library for manipulating SVN dump files. The

  main entry point for this is the Record class, which handles parsing and
  serializing data in the SVN dump file format. For a simple example, see the
  included svndumpgrab script.

Notes:
[1] Examples of /-separated regexp matching:

    The regexp "branches/v.*/web" is used for all the examples.

    - The path "branches/v1/web" would be checked in three steps:
      1. "branches" matches "branches"
      2. "v1" matches "v.*"
      3. "web" matches "web"
      4. It's a match!

    - The path "branches/v1/web/index.html" would be checked in the same three
      steps. After step 3, all parts of the regexp have been satisfied so it's
      considered a match.

    - The path "branches/v1/test/web" would be checked in three steps:
      1. "branches" matches "branches"
      2. "v1" matches "v.*"
      3. "test" DOES NOT MATCH "web"
      4. No match.
      Note that "v.*" is not allowed to match "v1/test" because it is matched
      against only one path segment.

    - The path "test/branches/v1/web" would be checked in one step:
      1. "test" DOES NOT MATCH "branches"
      2. No match.
      Note that, unlike a standard regular expression, matching only occurs at
      the beginning of the path.

    - The path "branches/v1" would be checked in two steps:
      1. "branches" matches "branches"
      2. "v1" matches "v.*"
      3. Partial match. Include as directory.

[2] The Subversion (SVN) revision control system offers very few options for
    modifying the history once it has been committed. The one official tool for
    making retroactive modifications is the svndumpfilter tool, which operates
    on SVN dump files, which encode the history of a repository into a stream
    format. Unfortunately, besides only being able to do rudimentary path-based
    filtering, svndumpfilter is unable to correctly handle copy operations.

    Rather than recording copy operations in a way that includes all of the data
    being copied, SVN saves space by only recording the source and destination
    of the copy operation. However, svndumpfilter only examines the destination
    of copy operations, not the source. This means that if the copy destination
    is included in the path filter, but the copy source is not, the copy
    operation will still be output unchanged. When the operation is then loaded,
    SVN will be unable to find the files to copy because they were excluded from
    the filter, so loading the file will fail.

    To fix this problem, svndumpmultitool checks sources of copy operations
    against the path filter and, when the copy source is excluded, it fetches
    the contents of the copy source from the repository (--repo) and generates
    add operations from those contents to simulate the copy operation.

[3] See http://svnbook.red-bean.com/en/1.7/svn.advanced.externals.html
"""

from __future__ import absolute_import

import argparse
import collections
import logging
import os
import sys
import urllib

from svndumpmultitool import externals
from svndumpmultitool import svn_util
from svndumpmultitool import svndump
from svndumpmultitool import util

# TODO: add tests for all untested functions, get coverage above 90%

LOGGER = logging.getLogger('svndumpmultitool' if __name__ == '__main__'
                           else __name__)


class Error(Exception):
  """Parent class for this module's errors."""


class UnsupportedActionPair(Error):
  """Encountered a pair of actions for which there is no merge strategy."""


# Higher-level class that makes use of the above to filter dump
# file fragments a whole revision at a time.
class Filter(object):
  """Filter SVN dumps one revision at a time.

  See __init__ for documentation of attributes.
  """

  def __init__(self,
               repo,
               paths,
               input_stream=sys.stdin,
               output_stream=sys.stdout,
               drop_empty_revs=True,
               revmap=None,
               externals_map=None,
               delete_properties=None,
               truncate_revs=None,
               drop_actions=None,
               force_delete=None):
    """Create a new Filter with the given attributes.

    Args:
      repo: absolute path to local SVN repo whose dump file will be filtered
            (must not contain a trailing /)
      paths: util.PathFilter object indicating which paths to include when
             filtering
      input_stream: a file-like object to read dump file from
      output_stream: a file-like object to write filtered dump file to
      drop_empty_revs: if True, revisions that contain no actions after
                       filtering will be dropped from output. See revmap for
                       handling of revision numbers when this is enabled.
      revmap: a dict {int: int} mapping revision numbers in the input repo to
              revision numbers after filtering. Usually given as an empty dict.
              If drop_empty_revs is True and revmap is not given, original
              revision numbers will be preserved, leaving gaps in the numbering.
              If revmap is given, output revision numbers will remain
              sequential, but one revision may have different numbers before and
              after filtering.
      externals_map: a dict {str: str}. Each key is the URL of the root of an
                     SVN repository and each value is the absolute path where
                     that repository can be found locally. When externals_map is
                     provided and non-empty, internalizing externals is enabled
                     for those externals pointing to URLs that are in the map.
      delete_properties: a list or set of SVN properties that will be deleted
                         from every path during filtering
      truncate_revs: an iterable of revision numbers in int form. All actions
                     in revisions in truncate_revs will be dropped during
                     filtering.
      drop_actions: a dict of sets where the keys of the dict are revision
                    numbers (int) and the items in the set are paths to drop all
                    actions for in those revisions.
      force_delete: a dict of lists where the keys of the dict are revision
                    numbers (int) and the items in the list are paths to add
                    delete actions for in those revisions.
    """
    self.repo = repo
    self.paths = paths
    self.input_stream = input_stream
    self.output_stream = output_stream
    self.drop_empty_revs = drop_empty_revs
    self.revmap = revmap
    self.externals_map = externals_map
    self.delete_properties = delete_properties
    self.truncate_revs = set(truncate_revs) if truncate_revs else set()
    self.drop_actions = drop_actions if drop_actions else dict()
    self.force_delete = force_delete if force_delete else dict()

  def Filter(self):
    """Filter the entire dump file in input_stream.

    Output is written to output_stream.
    """
    # Pass the dump-file header through unchanged
    record = svndump.ReadRecord(self.input_stream)
    while 'Revision-number' not in record.headers:
      record.Write(self.output_stream, self.revmap)
      record = svndump.ReadRecord(self.input_stream)

    revhdr = record

    current_output_rev = 0
    while revhdr is not None:
      # Read revision header.
      assert 'Revision-number' in revhdr.headers
      contents = []
      # Read revision contents.
      while True:
        record = svndump.ReadRecord(self.input_stream)
        if record is None or 'Revision-number' in record.headers:
          newrevhdr = record
          break
        contents.append(record)

      revision_number = int(revhdr.headers['Revision-number'])

      # Alter the contents of the revision.
      contents = self._FilterRev(revhdr, contents)

      # Determine whether we should output this revision.  We only
      # update the current_output_rev if we're actually going to write
      # something.
      should_write = contents or not self.drop_empty_revs
      if should_write:
        current_output_rev += 1

      # Update our revmap with information about this revision.  Note that
      # if this revision won't be written, current_output_rev still points
      # to the last version we dumped.
      if self.drop_empty_revs and self.revmap is not None:
        self.revmap[revision_number] = current_output_rev

      # Write out this revision, if that's what we've decided to do.
      if should_write:
        revhdr.Write(self.output_stream, self.revmap)
        for record in contents:
          record.Write(self.output_stream, self.revmap)

      # And loop round again.
      revhdr = newrevhdr

  def _FilterRev(self, revhdr, contents):
    """Filter all Records in a revision."""
    revision_number = int(revhdr.headers['Revision-number'])
    LOGGER.debug('Filtering r%s', revision_number)

    if revision_number in self.truncate_revs:
      LOGGER.warning('Truncating known bad revision r%s', revision_number)
      return []

    new_contents = []
    for record in contents:
      # Skip actions specified in drop_actions
      if (revision_number in self.drop_actions
          and record.headers['Node-path']
          in self.drop_actions[revision_number]):
        continue
      new_contents.extend(self._FilterRecord(revision_number, record))

    self._FlattenMultipleActions(revision_number, new_contents)

    if revision_number in self.force_delete:
      for path in self.force_delete[revision_number]:
        new_contents.append(svndump.Record(path=path, action='delete'))

    # Property removal must occur after all artificially generated Records have
    # been added to ensure we have a chance to remove their properties.
    if self.delete_properties:
      for record in new_contents:
        for prop in self.delete_properties:
          record.DeleteProperty(prop)

    return new_contents

  def _FilterRecord(self, revision_number, record):
    """Filter a single Record by path; import dangling copies and externals.

    Args:
      revision_number: the number of the revision that the Record belongs to
      record: a Record

    Returns:
      a list of zero or more Records

    An util.PathFilter is used to filter out excluded paths. Paths determined
    to be potential PARENTs of included paths are forced to be propertyless
    directories in case they do end up having included contents added to them.
    Add and delete operations are permitted on PARENTs, but change operations
    are discarded as they are not allowed to have properties or contents to
    change.

    _FixCopyFrom is called to fix copy operations that refer to excluded paths
    _InternalizeExternals is called if an externals map exists and the
    svn:externals property is set on the given Record.
    """
    path = record.headers['Node-path']

    interest = self.paths.CheckPath(path)

    if interest is util.PathFilter.NO:
      return []  # boooring
    elif interest is util.PathFilter.PARENT:
      # Parent dirs of interesting paths are coerced to be propertyless
      # directories
      if record.headers['Node-action'] == 'change':
        return []  # Parents can only be added or deleted
      elif record.headers['Node-action'] in ('add', 'replace'):
        if record.headers['Node-kind'] == 'file':
          # Files are turned into directories
          record = svndump.Record(path=path, kind='dir',
                                  action=record.headers['Node-action'])
        else:
          # Directories have their properties removed
          record.props = None
      else:
        assert record.headers['Node-action'] == 'delete'

    if 'Node-copyfrom-path' in record.headers:
      copyless_records = self._FixCopyFrom(record)
    else:
      copyless_records = (record,)

    output = []
    for copyless_record in copyless_records:
      # Internalizing externals is enabled if externals_map is populated
      if not self.externals_map or copyless_record.DoesNotAffectExternals():
        # Externals are not affected or internalizing externals is not enabled
        output.append(copyless_record)
      else:
        output.extend(
            self._InternalizeExternals(revision_number, copyless_record))
    return output

  def _FixCopyFrom(self, record):
    """Replace copies from excluded paths with adds.

    Args:
     record: a Record that represents a copy operation

    Returns:
      a list of one or more Records

    For a longer discussion, see svndump.MakeRecordsFromPath.
    """
    # Is the copy valid given our path filters?
    srcrev = int(record.headers['Node-copyfrom-rev'])
    srcpath = record.headers['Node-copyfrom-path']
    dstpath = record.headers['Node-path']

    if self.paths.IsIncluded(srcpath):
      # Copy is valid, leave it as is.
      return (record,)

    if self.paths.IsParentOfIncluded(dstpath) and srcpath == dstpath:
      # When copying into a parent path, it is usually necessary to use
      # _FilterPaths to determine which parts of the copy source should be
      # copied and which should not. However, if the copy source directory is
      # the same as the destination, it is safe to allow the copy operation to
      # remain as-is because the source will have already been filtered
      # correctly.
      return (record,)

    # Copy from a boring path to an interesting one, meaning we must extract the
    # subtree and convert it into records.
    output = []
    if self.paths.IsIncluded(dstpath):
      # The entire destination path is included, grab it all!
      output.extend(svndump.MakeRecordsFromPath(self.repo, srcrev, srcpath,
                                                dstpath, svndump.Record.COPY))
    else:
      # The destination itself is not included, but some included paths may
      # be created by this copy operation
      empty_dirs, recursive_dirs = self._FilterPaths(srcrev, srcpath, dstpath)
      for dir_name in empty_dirs:
        dir_name = (dstpath + '/' + dir_name) if dir_name else dstpath
        output.append(svndump.Record(kind='dir', action='add', path=dir_name,
                                     source=svndump.Record.COPY))
      for dir_name in recursive_dirs:
        output.extend(svndump.MakeRecordsFromPath(self.repo,
                                                  srcrev,
                                                  srcpath + '/' + dir_name,
                                                  dstpath + '/' + dir_name,
                                                  svndump.Record.COPY))
    if record.text is not None:
      # This was a copyfrom _plus_ some sort of
      # delta or new contents, which means that
      # having done the copy we now also need a
      # change record providing the new contents.
      record.headers['Node-action'] = 'change'
      del record.headers['Node-copyfrom-rev']
      del record.headers['Node-copyfrom-path']
      record.DeleteHeader('Text-copy-source-md5')
      record.DeleteHeader('Text-copy-source-sha1')
      output.append(record)
    return output

  def _InternalizeExternals(self, revision_number, record):
    """Use the externals map to replace externals with real files.

    Args:
      revision_number: the number of the revision being operated on
      record: a Record with an svn:externals property to be fixed

    Returns:
      a list of Records including the original Record passed in and any Records
      generated in order to pull in externals

    Triggered by --externals-map
    """
    # Always include the input Record in output
    output = [record]
    # Get the root of the externals
    path = record.headers['Node-path']
    # Parse the new value of svn:externals
    if record.props.get('svn:externals'):
      # TODO: change svn:externals to exclude the externals being
      # internalized.
      # The property is set
      new_externals = externals.Parse(
          self.repo, revision_number, path,
          record.props['svn:externals'], self.externals_map)
    else:
      # The property is absent or it is set to None, signifying it is being
      # deleted with Props-delta: true. Therefore we must check if the previous
      # revision has any externals that we should delete.
      new_externals = {}
    # Get the previous value of svn:externals
    prev_rev = revision_number - 1
    prev_externals = externals.FromRev(self.repo, prev_rev, path,
                                       self.externals_map)
    # Check how the externals descriptions have changed since last revision
    added, changed, deleted = externals.Diff(prev_externals, new_externals)
    LOGGER.debug('Changed externals for %s\n'
                 'from: %s\n'
                 'to: %s\n'
                 'Added: %s\n'
                 'Changed: %s\n'
                 'Deleted: %s',
                 path,
                 prev_externals,
                 new_externals,
                 added,
                 changed,
                 deleted)
    # First do changes because they might be converted into (delete, add)
    for old, new in changed:
      # Check whether processing as a change is possible and optimal
      if (old.srcrev is None
          or (new.srcrepo == self.repo and
              self.paths.IsIncluded(new.srcpath))):
        # - We can't do a diff if we don't know the old revision.
        # - If this external points inside the same repository to a path that is
        #   included by the filters, it's faster to just do a new copy operation
        #   than to update the contents.
        deleted.append(old)
        added.append(new)
        continue
      if new.srcrev is None:
        LOGGER.warning('Can\'t guess rev # for external repo %s', new)
        continue
      output.extend(self._ApplyExternalsChange(path, old, new))
    # Delete former externals paths
    for description in deleted:
      # TODO: if dstpath contains '/', introspect the source
      # repository to see if the intermediary directory exists. If not, delete
      # it instead.
      output.append(svndump.Record(
          path=path + '/' + description.dstpath,
          action='delete',
          source=svndump.Record.EXTERNALS))
    # Add new externals
    for description in added:
      # TODO: if dstpath contains '/', introspect the source
      # repository to see if the intermediary directory exists (if not, add a
      # Record to create it).
      if (description.srcrepo == self.repo and
          self.paths.IsIncluded(description.srcpath)):
        # External is in the same repo - do it as a copy
        # We don't support external files
        copy_record = svndump.Record(path=path +'/' + description.dstpath,
                                     kind='dir',
                                     action='add',
                                     source=svndump.Record.EXTERNALS)
        copy_record.headers['Node-copyfrom-path'] = description.srcpath
        copy_record.headers['Node-copyfrom-rev'] = description.srcrev
        output.append(copy_record)
      else:
        # External is not in the same repo - pull it in manually
        if description.srcrev is None:
          LOGGER.warning('Can\'t guess rev # for externals repo %s',
                         description)
          continue
        output.extend(
            svndump.MakeRecordsFromPath(description.srcrepo,
                                        description.srcrev,
                                        description.srcpath,
                                        path + '/' + description.dstpath,
                                        svndump.Record.EXTERNALS))
    return output

  def _ApplyExternalsChange(self, path, old, new):
    """Make Records to simulate the change from old to new ExternalsDescription.

    Args:
      path: the path on which the svn:externals property is set
      old: the ExternalsDescription from the previous revision
      new: an ExternalsDescription from the new revision

    Returns:
      a list of zero or more Records that convert the contents of the path
      referenced by old into the contents of the path referenced by new

    Raises:
      RuntimeError: if unsupported operations are shown in the svn diff output

    This is only possible if both descriptions refer to the same repository.

    Diff is called to find out which paths have changed, whether their
    properties, contents, or both have changed, and whether each path is a file
    or a directory. Records are generated to perform all deletes, then
    svndump.MakeRecordsFromPath is called to get Records creating the new state.
    The resulting Records are filtered through the list of changes, changing the
    action from add to change and deleting the properties or text content blocks
    if only the other is being changed. Records for paths listed as adds are
    passed through unchanged and Records not mentioned as deleted, changed, or
    added are dropped.
    """
    # Sanity check
    assert old.srcrepo == new.srcrepo
    output = []

    # Get a list of changes between the old and new revisions
    paths_changed = svn_util.Diff(new.srcrepo,
                                  old.srcpath,
                                  old.srcrev,
                                  new.srcpath,
                                  new.srcrev)

    # If nothing changed, we're done
    if not paths_changed:
      return output

    # First do deletes
    for chpath in paths_changed:
      contents_op, props_op = paths_changed[chpath]
      if contents_op == 'delete':
        # Sanity check
        assert props_op is None
        output.append(svndump.Record(
            path='%s/%s/%s' % (path, new.dstpath, chpath),
            action='delete',
            source=svndump.Record.EXTERNALS))

    # Grab Records to create the new version
    add_records = svndump.MakeRecordsFromPath(new.srcrepo,
                                              new.srcrev,
                                              new.srcpath,
                                              path + '/' + new.dstpath,
                                              svndump.Record.EXTERNALS)

    # Filter the Records to create a change instead of an add
    for add_record in add_records:
      record_path = add_record.headers['Node-path']
      # Strip off the dstpath
      record_path = record_path[len(path) + len(new.dstpath) + 2:]
      # Check if the path changed
      if record_path not in paths_changed:
        # Ignore paths that haven't changed
        continue

      # Find out what changed
      contents_op, props_op = paths_changed[record_path]

      # Handle contents_op
      if contents_op == 'add':
        # If it's an add, pass through unchanged
        pass
      elif contents_op == 'modify':
        add_record.headers['Node-action'] = 'change'
      elif contents_op is None:
        # Drop text contents - they haven't changed
        add_record.text = None
      else:
        raise RuntimeError('Unexpected contents operation %s in svn diff'
                           % contents_op)

      # Handle props_op
      if props_op is None and contents_op != 'add':
        # Drop props - they haven't changed
        add_record.props = None

      # This Record has lived to see another day...
      output.append(add_record)
    return output

  def _FilterPaths(self, srcrev, srcpath, dstpath):
    """Determine paths to import, either recursively or as empty directories.

    Args:
      srcrev: source revision
      srcpath: source path
      dstpath: destination path

    Returns:
      empty_dirs: a list of dirs to create empty
      recursive_dirs: a list of dirs to copy recursively

    Sometimes, a directory that is included by one of the path filters is
    created by a copy operation on a parent directory that is not included by
    the filters:

      included: trunk/foo

      svn rm trunk
      svn copy branches/bar trunk

    When that copy operation is processed, this function is called to determine
    which paths from branches/bar should be created as empty directories, which
    should be copied recursively, and which should be discarded in order to get
    the correct contents of trunk/foo after the copy.
    """
    empty_dirs = []
    recursive_dirs = []
    # Get a list of paths
    paths = svn_util.ExtractNodeKinds(self.repo, srcrev, srcpath)
    # Sort to ensure directories come before their children
    for path in sorted(paths):
      full_path = dstpath + '/' + path if path else dstpath
      interest = self.paths.CheckPath(full_path)
      if interest is util.PathFilter.PARENT:
        empty_dirs.append(path)
      elif interest is util.PathFilter.YES:
        include_me = True
        for parent_dir in recursive_dirs:
          if path.startswith(parent_dir + '/'):
            include_me = False
            break
        if include_me:
          recursive_dirs.append(path)
    return empty_dirs, recursive_dirs

  def _FlattenMultipleActions(self, revision_number, contents):
    """Fix multiple actions for a single path in one revision.

    Args:
      revision_number: the number of the revision in question
      contents: a list of all the Records in the revision (edited in-place)

    Raises:
     UnsupportedActionPair: if an unexpected sequence of actions is found or an
                            (add, change) pair includes a Text-delta change.

    There are several cases that can arise which would cause there to be
    multiple actions for a single path in one revision:
    - The original dump file contained a (delete, add) pair which makes changes
      and breaks the history of a file. This can be left alone.
    - A copy from a path not included by the filter includes modifications,
      resulting in an (add, change) pair. The change is merged into the add.
      This can also occur if a copy from a path not included by the filter is
      followed by a change to a subpath.
    - A copy from a path not included by the filter is followed by another copy
      on a subpath resulting in an (add, add) pair. The first add can be dropped
      in favor of the second.
    - A real directory is deleted in the same revision that an external is added
      at the same path. Subversion doesn't know to treat the external like a
      real path so it might list the addition of the external before the
      deletion of its destination path. In that case, the delete is moved to be
      before the add.
    - A copy from a path not included by the filter is followed by a delete on a
      subpath resulting in an (add, delete) pair. Both can be dropped since they
      cancel each other.
    - Any other case is not expected and will raise an exception.

    +--------------------------------------------------------------------------+
    |         2nd action|    delete   |     add    |    change   |   replace   |
    |    1st action     |             |            |             |             |
    |--------------------------------------------------------------------------|
    |       delete      |      !      |  replace   |      !      |      !      |
    |--------------------------------------------------------------------------|
    |        add        |    None*    |    2nd     |     add     |      !      |
    |--------------------------------------------------------------------------|
    |       change      |      !      |     !      |    change   |      !      |
    |--------------------------------------------------------------------------|
    |      replace      |      !      |     !      |    replace  |      !      |
    |--------------------------------------------------------------------------|
    | Result                    | Meaning                                      |
    |--------------------------------------------------------------------------|
    | replace/add/change/delete | merge into a single action of that type      |
    |--------------------------------------------------------------------------|
    | 1st/2nd                   | only the 1st or 2nd action survives          |
    |--------------------------------------------------------------------------|
    | None                      | both actions are purged                      |
    |--------------------------------------------------------------------------|
    | !                         | an exception is raised                       |
    +--------------------------------------------------------------------------+

    * (add, delete) is converted to (delete, add) by pulling the delete action
      earlier if the add's source is EXTERNALS and the delete's source is DUMP
      in order to handle the case where a normal directory is converted into an
      external by deleting the real directory and setting the parent's
      svn:externals property in the same revision (so Subversion does not know
      that the delete must preceed the property change).
    """
    paths = collections.defaultdict(list)
    for record in contents:
      path = record.headers['Node-path']
      paths[path].append(record)
    for path, records in paths.iteritems():
      while len(records) > 1:
        data = self._ActionPairFlattener(self.repo, revision_number, contents,
                                         path, records)
        data.Flatten()

  class _ActionPairFlattener(object):
    """Helper for _FlattenMultipleActions."""

    def __init__(self, repo, revision_number, contents, path, records):
      """Create an ActionPairFlattener.

      Args:
        repo: the source repo of the dump file being filtered
        revision_number: the revision currently being filtered
        contents: a list of all Records in the current revision
        path: the path whose actions are to be flattened
        records: a list of all Records in the current revision for path

      self.first and self.second are set to the first two items in records for
      convenience.
      """
      self.repo = repo
      self.revision_number = revision_number
      self.contents = contents
      self.path = path
      self.records = records
      self.first = records[0]
      self.second = records[1]

    def Flatten(self):
      """Merge the first two Records together.

      This function delegates to a number of helpers to do the action merge,
      depending on the types of the two actions. Each helper must be careful to
      make the appropriate changes to self.contents and self.records:
      - self.contents is the actual list of Records that will be output for the
        current revision. If a Record is deleted or the order is changed, that
        modification must be made to self.contents.
      - self.records is the list of all Records for the same path. If a Record
        is deleted or the order is changed, that modification must also be made
        to self.records so that merging can proceed in the correct order, and
        without trying to merge the same two Records again.

      Raises:
        UnsupportedActionPair: if an action pair is encountered for which no
                               merge strategy is defined
      """
      actions = (self.first.headers['Node-action'],
                 self.second.headers['Node-action'])
      if actions == ('add', 'add'):
        self.DropExtraneousAdd()
      elif (actions[0] in ('add', 'change', 'replace')
            and actions[1] == 'change'):
        self.MergeChange(actions[0])
      elif actions == ('add', 'delete'):
        if (self.first.source is svndump.Record.EXTERNALS
            and self.second.source is svndump.Record.DUMP):
          # A real path is being replaced with an external. Subversion doesn't
          # know that the external needs to go after the delete, so we have to
          # move the delete before the add.
          self.MoveDeleteToBeforeAdd()
        else:
          self.DropAddDeletePair()
      elif actions == ('delete', 'add'):
        # Collapse delete followed by add into replace.
        self.ConvertDeleteAndAddIntoReplace()
      else:
        # Catch-all for cases we shouldn't ever encounter and/or wouldn't
        # know how to resolve: (change, add), (change, change),
        # (change, delete), (delete, change), (delete, delete)
        raise UnsupportedActionPair('Found (%s, %s) for path %s in r%s'
                                    % (actions[0], actions[1], self.path,
                                       self.revision_number))

    def DropExtraneousAdd(self):
      LOGGER.warning('Found (add,add) - deleting first for path %s in r%s',
                     self.path, self.revision_number)
      self.contents.remove(self.first)
      self.records.remove(self.first)

    def MergeChange(self, first_action):
      """Apply a change action to an add|change|replace for the same path."""
      LOGGER.warning('Found (%s, change) - merging for path %s in r%s',
                     first_action, self.path, self.revision_number)
      if self.second.text is not None:
        if self.second.headers.get('Text-delta', 'false') == 'true':
          raise UnsupportedActionPair('Cannot merge (%s, change) when'
                                      ' Text-delta is set to true for path %s'
                                      ' in r%s'
                                      % (first_action, self.path,
                                         self.revision_number))
        self.first.text = self.second.text
        self.first.DeleteHeader('Text-delta')
        new_md5 = self.second.headers.get('Text-content-md5')
        if new_md5:
          self.first.headers['Text-content-md5'] = new_md5
        else:
          self.first.DeleteHeader('Text-content-md5')
      if self.second.props is not None:
        if self.first.props is None:
          self.first.props = self.second.props
        elif self.second.headers.get('Prop-delta', 'false') == 'true':
          self.first.props.update(self.second.props)
          if self.first.headers.get('Prop-delta', 'false') != 'true':
            # Actually delete properties, don't set them to None
            for key, value in self.first.props.items():
              if value is None:
                del self.first.props[key]
        else:
          self.first.props = self.second.props
      self.contents.remove(self.second)
      self.records.remove(self.second)

    def MoveDeleteToBeforeAdd(self):
      """Move a delete action to before an add for the same path."""
      LOGGER.warning('Found externals-related add followed by regular delete -'
                     ' moving the delete before the add for path %s in r%s',
                     self.path, self.revision_number)
      # Remove the delete Record, then insert it before the add.
      self.contents.remove(self.second)
      index = self.contents.index(self.first)
      self.contents.insert(index, self.second)
      # Reprocess this as (delete, add) by putting them back on the deque
      # in the new order. self.first and self.second are convenience copies of
      # self.records[0] and self.records[1] so we can rearrange them easily.
      self.records[0] = self.second
      self.records[1] = self.first

    def DropAddDeletePair(self):
      LOGGER.warning('Found (add, delete) - dropping both for path %s in r%s',
                     self.path, self.revision_number)
      self.contents.remove(self.first)
      self.contents.remove(self.second)
      self.records.remove(self.first)
      self.records.remove(self.second)

    def ConvertDeleteAndAddIntoReplace(self):
      LOGGER.warning('Converting (del, add) to replace for path %s in r%s',
                     self.path, self.revision_number)
      self.second.headers['Node-action'] = 'replace'
      self.contents.remove(self.first)
      self.records.remove(self.first)


def main(argv):
  """Filter an SVN dump file.

  Args:
    argv: a list of flags passed to the script (but not argv[0])

  See module docstring for extensive documentation on filtering.
  """
  # Parse command-line arguments.
  parser = argparse.ArgumentParser(epilog=__doc__,
                                   formatter_class=(
                                       argparse.RawDescriptionHelpFormatter))
  parser.add_argument('--include',
                      action='append',
                      default=[],
                      metavar='REGEXP',
                      help='Only include paths that match this regular'
                      ' expression (may be used multiple times).')
  parser.add_argument('--repo',
                      metavar='PATH',
                      help='Path of the SVN repo that produced the dump file.')
  parser.add_argument('--externals-map',
                      type=file,
                      metavar='FILE',
                      help='File mapping URLs used to reference externals to'
                      ' path of local copy of referenced repository. Format is'
                      ' one local path per line:  PATH [URL [URL ...]].')
  parser.add_argument('--delete-property',
                      action='append',
                      metavar='PROPNAME',
                      help='Delete an SVN property (such as svn:keywords) from'
                      ' all paths (may be used multiple times).')
  parser.add_argument('--truncate-rev',
                      action='append',
                      type=int,
                      metavar='REVNUM',
                      help='Drop all changes made in a particular revision, but'
                      ' keep the commit message (DANGEROUS). If combined with'
                      ' --drop-empty-revs, the revision wil be deleted entirely'
                      ' (EVEN MORE DANGEROUS) (may be used multiple times).')
  parser.add_argument('--drop-action',
                      action='append',
                      metavar='REV:PATH',
                      help='Drop all actions for PATH in REV (may be used'
                      ' multiple times).')
  parser.add_argument('--force-delete',
                      action='append',
                      metavar='REV:PATH',
                      help='Insert a delete action for PATH at the end of REV'
                      ' (may be used multiple times).')
  parser.add_argument('--drop-empty-revs',
                      action='store_true',
                      help='Delete empty revisions caused by path filtering or'
                      ' --truncate-rev (default is to output empty revisions'
                      ' with date, commit message, and author intact).')
  # TODO: make this accept an optional file argument that the revmap
  # will be loaded from if it exists, then serialized to upon completion.
  parser.add_argument('--renumber-revs',
                      action='store_true',
                      help='Renumber revisions to be sequential after'
                      ' --drop-empty-revs or damaged data caused gaps in'
                      ' revision numbers. This should only be used when'
                      ' filtering the entire history at once, e.g. not using'
                      ' the -r option of svnadmin dump or svnrdump.')
  parser.add_argument('--debug', action='store_true',
                      help='Log verbosely to stderr.')

  options = parser.parse_args(argv)

  if options.debug:
    logging.basicConfig(level=logging.DEBUG)

  # We use this table to map input revisions to output revisions.
  if options.renumber_revs:
    revmap = {}
  else:
    revmap = None

  # Load the externals map if given
  if options.externals_map:
    externals_map = {}
    for line in options.externals_map:
      if line.startswith('#'):
        continue
      parts = line.split()
      # By default, each path is mapped to its own file:// URL
      externals_map[util.FileURL(parts[0], None, None)] = parts[0]
      # Add any user-specified mappings (these may replace the default file://
      # mapping or add aliases using file://, http[s]://, svn+ssh://, etc.
      # %-encoding can be used in the file for URLs that contain whitespace
      # (or other weird characters)
      for url in parts[1:]:
        externals_map[urllib.unquote(url)] = parts[0]
    options.externals_map.close()
    LOGGER.debug('Found externals definitions:\n%s',
                 '\n'.join('%s -> %s' % (url, path)
                           for url, path in sorted(externals_map.iteritems()))
                )
  else:
    externals_map = None

  if options.drop_action:
    drop_actions = collections.defaultdict(set)
    for spec in options.drop_action:
      rev, path = spec.split(':', 1)
      rev = int(rev)
      drop_actions[rev].add(path)
  else:
    drop_actions = None

  if options.force_delete:
    force_delete = collections.defaultdict(list)
    for spec in options.force_delete:
      rev, path = spec.split(':', 1)
      rev = int(rev)
      force_delete[rev].append(path)
  else:
    force_delete = None

  # Create a Filter
  filt = Filter(os.path.abspath(options.repo) if options.repo else None,
                util.PathFilter(options.include),
                drop_empty_revs=options.drop_empty_revs,
                revmap=revmap,
                externals_map=externals_map,
                delete_properties=options.delete_property,
                truncate_revs=options.truncate_rev,
                drop_actions=drop_actions,
                force_delete=force_delete)

  filt.Filter()


if __name__ == '__main__':
  main(sys.argv[1:])
