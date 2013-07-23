#!/usr/bin/python2.7

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

"""Print the specified revisions."""

import argparse
import sys

import svndumpmultitool


def main(argv):
  args = ParseArgs(argv)

  revs = None
  maxrev = None
  if args.revisions:
    revs = StringToIntSet(args.revisions)
    maxrev = max(revs)

  revnum = None
  rev_action_num = None
  lump = svndumpmultitool.Lump.Read(sys.stdin)
  while lump:
    if 'Revision-number' in lump.headers:
      # Revision header lump
      revnum = int(lump.headers['Revision-number'])
      rev_action_num = 0
      if Includes(revs, revnum):
        lump.Write(sys.stdout, None)
      elif revnum > maxrev:
        break
    elif revnum is not None and Includes(revs, revnum):
      # Action lump in an included revision
      lump.headers['Lump-index'] = str(rev_action_num)
      lump.Write(sys.stdout, None)
      rev_action_num += 1
    lump = svndumpmultitool.Lump.Read(sys.stdin)


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
