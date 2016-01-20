#!/usr/bin/python2.7

# Copyright 2013 Google Inc. All Rights Reserved.
#
# Use of this source code is governed by a MIT-style
# license that can be found in the LICENSE file or at
# http://opensource.org/licenses/MIT

"""Print the specified revisions."""

from __future__ import absolute_import

import argparse
import sys

from svndumpmultitool import svndump


def main(argv):
  args = ParseArgs(argv)

  revs = None
  maxrev = None
  if args.revisions:
    revs = StringToIntSet(args.revisions)
    maxrev = max(revs)

  revnum = None
  rev_action_num = None
  record = svndump.ReadRecord(sys.stdin)
  while record:
    if 'Revision-number' in record.headers:
      # Revision header Record
      revnum = int(record.headers['Revision-number'])
      rev_action_num = 0
      if Includes(revs, revnum):
        record.Write(sys.stdout, None)
      elif revnum > maxrev:
        break
    elif revnum is not None and Includes(revs, revnum):
      # Action Record in an included revision
      record.headers['Record-index'] = str(rev_action_num)
      record.Write(sys.stdout, None)
      rev_action_num += 1
    record = svndump.ReadRecord(sys.stdin)


def ParseArgs(argv):
  arg_parser = argparse.ArgumentParser(
      description='Grab specified revisions.')
  arg_parser.add_argument('revisions', type=str, nargs='?',
                          help='Revisions to dump, as in "5-6,9"')
  return arg_parser.parse_args(args=argv[1:])


def Includes(container, item):
  return container is None or item in container


def StringToIntSet(string):
  """Convert a string into a set of ints.

  Examples:
  5 -> set(5)
  5-7 -> set(5,6,7)
  5,7-9 -> set(5,7,8,9)

  Args:
    string: the string

  Returns:
    a set of all ints included by string
  """
  included = set()
  for part in string.split(','):
    if '-' in part:
      first, last = part.split('-')
      included.update(xrange(int(first), int(last) + 1))
    else:
      included.add(int(part))
  return included


if __name__ == '__main__':
  main(sys.argv)
