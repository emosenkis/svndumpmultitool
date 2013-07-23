svndumpmultitool.
====================

Tool for filtering, fixing, breaking, and munging SVN dump files.

This script takes an SVN dump file on stdin, applies various filtering
operations to the history represented by the dump file, and prints the resulting
dump file to stdout. A number of different filtering operations are available,
each enabled by command-line flag. Multiple operations can be used at the same
time. If run without any operations enabled, the script will validate the dump
file's structure and output the same dump file to stdout.

Dependencies
------------
- Python v2.7.x
- Subversion v1.6 or higher
- Subversion API SWIG bindings for Python (NOT the pysvn library)
- mock (to run the tests)

Operations
----------
Path filtering (``--include``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Each argument to ``--include`` is a regular expression. Only paths that
match one or more ``--include`` regexps will be included in the output. A path
whose ancestor directory matches a regexp will also be included. A path that
could be the ancestor directory for a path that matches the regexp will be
included as a directory without properties, even if originally it was a file
or it had properties.

The regular expressions accepted by ``--include`` are based on standard Python
regular expressions, but have one major difference: they are broken into
/-separated pieces and applied to one /-separated path segment at a time.
See [1]_ for detailed examples of how this works.

It is usually necessary to provide ``--repo`` when using ``--include``. See [2]_
for details.

See Limitations_ and `--drop-empty-revs`_ below.

Examples::

  --include=foo
  Includes: foo, foo/bar
  Excludes: trunk/foo

  --include=branches/v.*/foo
  Includes: branches/v1/foo, branches/v2/foo/bar
  Excludes: branches/foo, branches/v1/x/foo, branches/bar
  Includes as directory w/out properties: branches

Externals (``--externals-map``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If the ``--externals-map`` argument is provided, the filter will attempt to
alter the history such that whenever SVN externals [3]_ are included using the
svn:externals property, the contents referenced therein are fetched from
their source repository and inserted in the output stream as if they had
been physically included in the main repository from the beginning.

In order to internalize SVN externals, a local copy of each referenced
repository is required, as well as a mapping from the URLs used to reference
it to the local path at which it resides. A file providing this mapping must
be passed as the value of ``--externals-map``. Only externals using URLs
included in the map will be internalized.

See Limitations_ below.

Example::

  --externals-map=/path/to/my/externals.map

Revision cancellation (``--truncate-rev``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The value for ``--truncate-rev`` should be a revision number. All changes to the
repository that occurred in that revision will be dropped (commit messages
are retained). This is extremely dangerous because future revisions will
still expect the revision to have taken effect. There are a few cases when
it is safe to use ``--truncate-rev``:

1. If used on a pair of revisions that cancel each other out (e.g.
   ``--truncate-rev=108 --truncate-rev=109``, where r108 deletes trunk, r109
   copies trunk from r107).
2. If used on a revision that modifies files/directories, but does not add
   or remove them.

--truncate-rev may be given more than once to truncate multiple revisions.

See also `--drop-empty-revs`_.

Property deletion (``--delete-property``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The SVN property given as the value for ``--delete-property`` will be stripped
from all paths. ``--delete-property`` can be specified more than once to delete
multiple properties.

Examples::

  --delete-property=svn:keywords (to turn off keyword expansion)
  --delete-property=svn:special (to convert symlinks to regular files
    containing 'link <link-target>')

Handling of empty revisions (``--drop-empty-revs``, ``--renumber-revs``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
There are two cases that can result in revisions that perform no actions on
the repository:

1. All paths originally affected by the revision are excluded by the path
   filters.
2. ``--truncate-rev`` was used to explicitly cancel all actions from the
   revision.

By default, these empty revisions are included in the output dump stream. If
``--drop-empty-revs`` is used, empty revisions are instead dropped from the
output. If ``--renumber-revs`` is used in addition to ``--drop-empty-revs``, the
following revisions will be renumbered to eliminate the gap left by the
deleted revision.

See Limitations_ below.

Limitations
-----------
Dump file format:
  'delta' dumps are not fully supported.

Externals:
  - If an externals definition imports the external into a subdirectory, that
    subdirectory will not be automatically created.
  - Currently, the svn:externals property is not modified or deleted when
    externals are internalized.

Revision renumbering:
  The revision mapping used by ``--renumber-revs`` to ensure that copy
  operations point to the correct source is not propagated across multiple
  invocations of the script. This makes it unsuitable for use on incremental
  dumps.

Testing:
  Unit testing is approximately 80% complete. End-to-end testing has not been
  started yet.

Use as a library
----------------
svndumpmultitool can be used as a library for manipulating SVN dump files. The
main entry point for this is the Lump class, which handles parsing and
serializing data in the SVN dump file format. For a simple example, see the
included svndumpgrab script.

--------------------------------------------------------------------------------

.. [1] Examples of /-separated regexp matching:

   The regexp ``branches/v.*/web`` is used for all the examples.

   - The path ``branches/v1/web`` would be checked in three steps:

     1. ``branches`` matches ``branches``
     2. ``v1`` matches ``v.*``
     3. ``web`` matches ``web``
     4. It's a match!

   - The path ``branches/v1/web/index.html`` would be checked in the same three
     steps. After step 3, all parts of the regexp have been satisfied so it's
     considered a match.

   - The path ``branches/v1/test/web`` would be checked in three steps:

     1. ``branches`` matches ``branches``
     2. ``v1`` matches ``v.*``
     3. ``test`` *does not match* ``web``
     4. No match.

     Note that ``v.*`` is not allowed to match ``v1/test`` because it is matched
     against only one path segment.

   - The path ``test/branches/v1/web`` would be checked in one step:

     1. ``test`` *does not match* ``branches``
     2. No match.

     Note that, unlike a standard regular expression, matching only occurs at
     the beginning of the path.

   - The path ``branches/v1`` would be checked in two steps:

     1. ``branches`` matches ``branches``
     2. ``v1`` matches ``v.*``
     3. Partial match. Include as directory.

.. [2] The Subversion (SVN) revision control system offers very few options for
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
   the contents of the copy source from the repository (``--repo``) and
   generates add operations from those contents to simulate the copy operation.

.. [3] http://svnbook.red-bean.com/en/1.7/svn.advanced.externals.html

.. _`--drop-empty-revs`:
  `Handling of empty revisions (--drop-empty-revs, --renumber-revs)`_
