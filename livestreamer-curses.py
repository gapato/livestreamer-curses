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

import curses.wrapper
from time import sleep, time
import sys
import os
import shelve
import signal
from subprocess import call, STDOUT, Popen, PIPE
from select import select

DEFAULT_RES='480p'

ID_FIELD_WIDTH   = 6
NAME_FIELD_WIDTH = 22
RES_FIELD_WIDTH  = 12
VIEWS_FIELD_WIDTH = 7
PLAYING_FIELD_OFFSET = ID_FIELD_WIDTH + NAME_FIELD_WIDTH + RES_FIELD_WIDTH + VIEWS_FIELD_WIDTH + 6

class QueueFull(Exception): pass
class QueueDuplicate(Exception): pass

class ProcessList(object):
    """ Small class to store and handle calls to a given callable """

    def __init__(self, f, max_size=10):
        """ Create a ProcessList

        f        : callable for which a process will be spawned for each call to put
        max_size : the maximum size of the ProcessList

        """
        self.q        = {}
        self.max_size = max_size
        self.call     = f

    def __del__(self):
        self.terminate()

    def full(self):
        """ Check is the List is full, returns a bool """
        return len(self.q) == self.max_size

    def empty(self):
        """ Check is the List is full, returns a bool """
        return len(self.q) == 0

    def put(self, id, *args):
        """ Spawn a new background process

        id   : int, id of the process,
               unique among the queue or will raise QueueDuplicate
        args : optional arguments to pass to the callable

        """

        if len(self.q) < self.max_size:
            if self.q.has_key(id):
                raise QueueDuplicate
            p = self.call(*args)
            self.q[id] = p
        else:
            raise QueueFull

    def get_finished(self):
        """ Clean up terminated processes and returns the list of their ids """
        indices  = []
        for id, v in self.q.items():
            if v.poll() != None:
                indices.append(id)

        for i in indices:
            self.q.pop(i)
        return indices

    def get_process(self, id):
        """ Get a process by id, returns None if there is no match """
        return self.q.get(id)

    def get_stdouts(self):
        """ Get the list of stdout of each process """
        souts = []
        for v in self.q.values():
            souts.append(v.stdout)
        return souts

    def terminate_process(self, id):
        """ Terminate a process by id """
        try:
            p = self.q.pop(id)
            p.terminate()
            return p
        except:
            return None

    def terminate(self):
        """ Terminate all processes """
        for w in self.q.values():
            try:
                w.terminate()
            except:
                pass

        self.q = {}

class StreamPlayer(object):
    """ Provides a callable to play a given url """
    @classmethod
    def play(self, url, res):
        return Popen(["livestreamer", url, res], stdout=PIPE, stderr=STDOUT)

class StreamList(object):

    def __init__(self, filename):
        """ Init and try to load a stream list, nothing about curses yet """

        # Open the storage (create it if necessary
        f = shelve.open(filename, 'c')
        self.max_id = 0

        # Sort streams by view count
        if f.has_key('streams'):
            self.streams = sorted(f['streams'], key=lambda s:s['seen'], reverse=True)
            for s in self.streams:
                # Max id, needed when adding a new stream
                self.max_id = max(self.max_id, s['id'])
        else:
            self.streams = []

        self.store = f

        self.no_streams = self.streams == []
        self.q = ProcessList(StreamPlayer.play)

    def __del__(self):
        """ Stop playing streams and sync storage """
        self.q.terminate()
        self.store['streams'] = self.streams
        self.store.close()

    def __call__(self, s):
        # Terminal initialization
        self.init(s)
        # Main event loop
        self.run()

    def init(self, s):
        """ Initialize the text interface """

        # Hide cursor
        curses.curs_set(0)

        self.s = s
        self.get_screen_size()

        self.set_title('Livestreamer-curses v0.1')
        self.set_footer('Ready')

        self.init_help()
        self.init_streams_pad()

        self.got_g = False
        self.status = ''

    def run(self):
        """ Main event loop """

        # Show stream list
        self.show_streams()

        while True:
            self.s.refresh()

            # See if any stream has ended
            self.check_stopped_streams()

            # Wait on stdin or on the streams output
            souts = self.q.get_stdouts()
            souts.append(sys.stdin)
            (r, w, x) = select(souts, [], [], 1)
            for fd in r:
                if fd != sys.stdin:
                    # Set the new status line only if non-empty
                    msg = fd.readline()
                    if len(msg) > 0:
                        self.status = msg[:-1]
                        self.redraw_status()
                else:
                    # Main event loop
                    c = self.streams_pad.getch()
                    if c == curses.KEY_UP or c == ord('k') or c == 65:
                        self.move(-1)
                    elif c == curses.KEY_DOWN or c == ord('j') or c == 66:
                        self.move(1)
                    elif c == ord('g'):
                        if self.got_g:
                            self.move(0, absolute=True)
                            self.got_g = False
                            continue
                        self.got_g = True
                    elif c == ord('G'):
                        self.move(len(self.streams)-1, absolute=True)
                    elif c == 10:
                        self.play_stream()
                    elif c == ord('s'):
                        self.stop_stream()
                    elif c == ord('c'):
                        self.reset_stream()
                    elif c == ord('n'):
                        self.edit_stream('name')
                    elif c == ord('r'):
                        self.edit_stream('res')
                    elif c == ord('u'):
                        self.edit_stream('url')
                    elif c == ord('a'):
                        self.prompt_new_stream()
                    elif c == ord('d'):
                        self.delete_stream()
                    elif c == ord('h') or c == ord('?'):
                        self.show_help()
                        self.show_streams()
                    elif c == ord('q'):
                        self.q.terminate()
                        return
                    elif c == curses.KEY_RESIZE:
                        self.get_screen_size()
                        self.init_help()
                        self.init_streams_pad()
                        self.show_streams()
                    else:
                        self.set_footer(' Got unknown key : {}'.format(str(c)))

    def get_screen_size(self):
        """ Setup screen size and padding

        We have need 2 free lines at the top and 2 free lines at the bottom

        """
        max_y, max_x = self.s.getmaxyx()
        self.pad_x = 0
        self.max_y, self.max_x = (max_y - 1, max_x -1)
        self.pad_w = max_x-1*self.pad_x
        self.pad_h = max_y-3

    def overwrite_line(self, msg, attr=curses.A_NORMAL):
        self.s.clrtoeol()
        self.s.addstr(msg, attr)
        self.s.chgat(attr)

    def set_title(self, msg):
        """ Set first header line text """
        self.s.move(0, 0)
        self.overwrite_line(msg, curses.A_REVERSE)

    def set_header(self, msg):
        """ Set second head line text """
        self.s.move(1, 0)
        self.overwrite_line(msg, attr=curses.A_NORMAL)

    def set_footer(self, msg):
        """ Set first footer line text """
        self.s.move(self.max_y-1, 0)
        self.overwrite_line(msg, attr=curses.A_REVERSE)

    def init_help(self):
        h = curses.newpad(self.pad_h, self.pad_w)

        h.addstr( 0, 0, 'STREAM MANAGEMENT', curses.A_BOLD)
        h.addstr( 2, 0, '  Enter : start stream')
        h.addstr( 3, 0, '  s     : stop stream')
        h.addstr( 4, 0, '  r     : change stream resolution')
        h.addstr( 5, 0, '  n     : change stream name')
        h.addstr( 6, 0, '  u     : change stream URL')
        h.addstr( 7, 0, '  c     : reset stream view count')
        h.addstr( 8, 0, '  a     : add stream')
        h.addstr( 9, 0, '  d     : delete stream')

        h.addstr(12, 0, 'NAVIGATION', curses.A_BOLD)
        h.addstr(14, 0, '  j/up  : up one line')
        h.addstr(15, 0, '  k/down: down one line')
        h.addstr(16, 0, '  gg    : go to top')
        h.addstr(17, 0, '  G     : go to bottom')
        h.addstr(18, 0, '  h/?   : show this help')
        h.addstr(19, 0, '  q     : quit')

        self.help_pad = h

    def show_help(self):
        """ Redraw Help screen and wait for any input to leave """
        self.s.move(1,0)
        self.s.clrtobot()
        self.set_header('Help'.center(self.pad_w))
        self.set_footer(' Press any key to return to main menu')
        self.s.refresh()
        self.help_pad.refresh(0, 0, 2, 0, self.pad_h, self.pad_h)
        self.help_pad.getch()

    def init_streams_pad(self):
        """ Create a curses pad and populate it with a line by stream """
        y = 0
        p = curses.newpad(max(1,len(self.streams)), self.pad_w)
        for s in self.streams:
            p.addstr(y, 0, self.format_stream_line(s))
            y+=1
        self.row = 0
        self.top_row = 0
        p.move(self.row, 0)
        if not self.no_streams:
            p.chgat(curses.A_REVERSE)
        self.streams_pad = p

    def show_streams(self):
        self.s.move(1,0)
        self.s.clrtobot()
        if not self.no_streams:
            id = 'ID'.center(ID_FIELD_WIDTH)
            name = 'Name'.center(NAME_FIELD_WIDTH)
            res = 'Resolution'.center(RES_FIELD_WIDTH)
            views = 'Views'.center(VIEWS_FIELD_WIDTH)
            self.set_header('{}|{}|{}|{}| Status'.format(id, name, res, views))
            self.redraw_stream_footer()
            self.redraw_status()
        else:
            self.s.addstr(5, 5, 'It seems you don\'t have any stream yet,')
            self.s.addstr(6, 5, 'hit \'a\' to add a new one.')
            self.s.addstr(8, 5, 'Hit \'?\' for help.')
            self.set_footer(' Ready')
        self.s.refresh()
        self.refresh_streams_pad()

    def refresh_streams_pad(self):
        self.streams_pad.refresh(self.top_row, 0, 2, self.pad_x, self.pad_h, self.pad_w)

    def move(self, direction, absolute=False):
        """ Scroll the stream pad

        direction : (int)  if absolute is True, go to position direction
                           otherwise move by one in the given direction
                           -1 is up, 1 is down
        absolute  : (bool)
        """
        if self.no_streams:
            return
        self.streams_pad.move(self.row, 0)
        self.streams_pad.chgat(curses.A_NORMAL)
        if absolute and direction >= 0 and direction < len(self.streams):
            if direction < self.top_row:
                self.top_row = direction
            elif direction > self.top_row + self.pad_h - 2:
                self.top_row = direction - self.pad_h + 2
            self.row = direction
        else:
            if direction == -1 and self.row > 0:
                if self.row == self.top_row:
                    self.top_row -= 1
                self.row -= 1
            elif direction == 1 and self.row < len(self.streams)-1:
                if self.row == self.top_row + self.pad_h - 2:
                    self.top_row += 1
                self.row += 1
        self.streams_pad.move(self.row, 0)
        self.streams_pad.chgat(curses.A_REVERSE)
        self.refresh_streams_pad()
        s = self.streams[self.row]
        self.redraw_stream_footer()
        self.redraw_status()

    def format_stream_line(self, stream):
        id = '{} '.format(stream['id']).rjust(ID_FIELD_WIDTH)
        name = ' {}'.format(stream['name']).ljust(NAME_FIELD_WIDTH)
        res  = ' {}'.format(stream['res']).ljust(RES_FIELD_WIDTH)
        views  = '{} '.format(stream['seen']).rjust(VIEWS_FIELD_WIDTH)
        p = self.q.get_process(stream['id']) != None
        if p:
            indicator = '>'
        else:
            indicator = ' '
        return '{}|{}|{}|{}|  {}'.format(id, name, res, views, indicator)

    def redraw_current_line(self):
        """ Redraw the highlighted line """
        if self.no_streams:
            return
        s = self.streams[self.row]
        self.streams_pad.move(self.row, 0)
        self.streams_pad.clrtoeol()
        self.streams_pad.addstr(self.row, 0, self.format_stream_line(s), curses.A_REVERSE)
        self.streams_pad.chgat(curses.A_REVERSE)
        self.refresh_streams_pad()

    def redraw_status(self):
        self.s.move(self.max_y, 0)
        self.overwrite_line(self.status, curses.A_NORMAL)

    def redraw_stream_footer(self):
        if not self.no_streams:
            s = self.streams[self.row]
            self.set_footer('{}/{} {} {}'.format(self.row+1, len(self.streams), s['url'], s['res']))
            self.s.refresh

    def check_stopped_streams(self):
        finished = self.q.get_finished()
        for f in finished:
            for i in range(len(self.streams)):
                s = self.streams[i]
                if f == s['id']:
                    self.set_footer('Stream {} has stopped'.format(s['name']))
                    if i == self.row:
                        attr = curses.A_REVERSE
                    else:
                        attr = curses.A_NORMAL
                    self.streams_pad.addch(i, PLAYING_FIELD_OFFSET, ' ', attr)
                    self.refresh_streams_pad()

    def prompt_input(self, prompt=''):
        self.s.move(self.max_y-1, 0)
        self.s.clrtoeol()
        self.s.addstr(prompt)
        curses.curs_set(1)
        curses.echo()
        r = self.s.getstr()
        curses.noecho()
        curses.curs_set(0)
        self.s.move(self.max_y-1, 0)
        self.s.clrtoeol()
        return r

    def prompt_confirmation(self, prompt='', def_yes=False):
        self.s.move(self.max_y-1, 0)
        self.s.clrtoeol()
        if def_yes:
            hint = '[y]/n'
        else:
            hint = 'y/[n]'
        self.s.addstr('{} {} '.format(prompt, hint))
        curses.curs_set(1)
        curses.echo()
        r = self.s.getch()
        curses.noecho()
        curses.curs_set(0)
        self.s.move(self.max_y-1, 0)
        self.s.clrtoeol()
        if r == ord('y'):
            return True
        elif r == ord('n'):
            return False
        else:
            return def_yes

    def sync_store(self):
        self.store['streams'] = self.streams
        self.store.sync()

    def bump_stream(self, stream, throttle=False):
        t = int(time())

        # only bump if stream was last started some time ago
        if throttle and  t - stream['last_seen'] < 60*1:
            return
        stream['seen'] += 1
        stream['last_seen'] = t
        self.sync_store()

    def find_stream(self, sel, key='id'):
        for s in self.streams:
            if s[key] == sel:
                return s
        return None

    def add_stream(self, name, url, res=DEFAULT_RES, bump=False):
        ex_stream = self.find_stream(url, key='url')
        if ex_stream:
            if bump:
                self.bump_stream(ex_stream)
        else:
            if bump:
                seen = 1
                last_seen = int(time())
            else:
                seen = last_seen = 0
            if len(self.streams) == 0:
                id = 1
            else:
                self.max_id += 1
                id = self.max_id
            new_stream = {
                    'id'        : id,
                    'name'      : name,
                    'seen'      : seen,
                    'last_seen' : last_seen,
                    'res'       : res,
                    'url'       : url
                }
            self.streams.append(new_stream)
            self.no_streams = False
            try: self.init_streams_pad()
            except: pass
            self.sync_store()

    def delete_stream(self):
        if self.no_streams:
            return
        s = self.streams.pop(self.row)
        if not self.prompt_confirmation('Delete stream {}?'.format(s['name'])):
            return
        self.streams_pad.deleteln()
        self.sync_store()
        if len(self.streams) == 0:
            self.no_streams = True
        if self.row == len(self.streams) and not self.no_streams:
            self.move(-1)
            self.streams_pad.chgat(curses.A_REVERSE)
        self.redraw_current_line()
        self.show_streams()

    def reset_stream(self):
        if self.no_streams:
            return
        s = self.streams[self.row]
        if not self.prompt_confirmation('Reset stream {}?'.format(s['name'])):
            return
        s['seen']      = 0
        s['last_seen'] = 0
        self.redraw_current_line()
        self.sync_store()

    def edit_stream(self, attr):
        prompt_info = {
                'name'      : 'Name',
                'url'       : 'URL',
                'res'       : 'Resolution'
                }
        if self.no_streams:
            return
        s = self.streams[self.row]
        new_val = self.prompt_input('{} (empty to cancel): '.format(prompt_info[attr]))
        if new_val != '':
            s[attr] = new_val
            self.redraw_current_line()
        self.redraw_status()
        self.redraw_stream_footer()

    def prompt_new_stream(self):
        url = self.prompt_input('New stream URL (empty to cancel): ')
        name = url.split('/')[-1]
        if len(name) > 0:
            self.add_stream(name, url)
            self.move(len(self.streams)-1, absolute=True)
            self.show_streams()

    def play_stream(self):
        if self.no_streams:
            return
        s = self.streams[self.row]
        try:
            self.q.put(s['id'], s['url'], s['res'])
            self.bump_stream(s, throttle=True)
            self.redraw_current_line()
            self.refresh_streams_pad()
        except:
            self.set_footer('This stream is already playing')

    def stop_stream(self):
        if self.no_streams:
            return
        s = self.streams[self.row]
        p = self.q.terminate_process(s['id'])
        if p:
            self.redraw_current_line()
            self.redraw_stream_footer()
            self.redraw_status()

l = StreamList('{}/.livestreamer-curses.db'.format(os.environ['HOME']))
curses.wrapper(l)
