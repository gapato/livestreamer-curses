#!/usr/bin/python
# coding: utf-8

# The MIT License (MIT)
# Copyright (c) 2013 Gaspard Jankowiak
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import curses
import argparse
import sys
import os
import imp
import json

from . import config

from .streamlist import StreamList

def main():
    global config

    parser = argparse.ArgumentParser(description='Livestreamer curses frontend.')
    try:
        arg_type = unicode
    except:
        arg_type = str
    parser.add_argument('-d', type=arg_type, metavar='database', help=u'default: ' + config.DB_DEFAULT_PATH,
                       default=os.path.join(config.DB_DEFAULT_PATH))
    parser.add_argument('-f', type=arg_type, metavar='configfile', help=u'default: ' + config.RC_DEFAULT_PATH,
                        default=os.path.join(config.RC_DEFAULT_PATH))
    parser.add_argument('-p', action='store', type=arg_type, metavar='JSON file', help='load (overwrite) database with data from this file. Use - for stdin')
    parser.add_argument('-l', action='store_true', help='print the list of streams and exit')
    args = parser.parse_args()

    rc_filename = args.f
    if os.path.exists(rc_filename):
        try:
            config = imp.load_source(config.__name__, rc_filename)
        except Exception as e:
            sys.stderr.write('Failed to read rc file, error was:\n{0}\n'.format(str(e)))
            sys.exit(1)

    init_stream_list = []
    if args.p:
        if args.p == '-':
            buf = sys.stdin
        elif os.path.exists(args.p):
            buf = open(args.p)
        else:
            IOError("No such file or directory: '{0}'".format(args.p))
        init_stream_list = json.load(buf)
        if not isinstance(init_stream_list, list):
            raise ValueError('The stream list must be provided as a valid JSON array')

        keys = {'name':arg_type, 'url':arg_type, 'res':arg_type}
        def check_stream(s):
            for k, t in keys.items():
                try:
                    if not isinstance(s[k], t):
                        return False
                except:
                    return False
            return True
        init_stream_list = list(filter(check_stream, init_stream_list))

    l = StreamList(args.d, config, list_streams=args.l, init_stream_list=init_stream_list)
    if not args.l:
        curses.wrapper(l)

if __name__ == '__main__':
    main()
