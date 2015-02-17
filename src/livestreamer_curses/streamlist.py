from time import sleep, time, strftime, localtime
import shelve
import shlex
from subprocess import STDOUT, Popen, PIPE
import signal
import select
import struct
from fcntl import ioctl
import termios
from multiprocessing.pool import ThreadPool as Pool
import json
import sys
import curses
import os

from IPython import embed

import livestreamer

PY3 = sys.version_info.major >= 3

if PY3:
    import queue
else:
    import Queue as queue

PROG_STRING    = 'livestreamer-curses'
TITLE_STRING   = 'v{{0}} with Livestreamer v{1}'.format(PROG_STRING, livestreamer.__version__)

ID_FIELD_WIDTH   = 6
NAME_FIELD_WIDTH = 22
RES_FIELD_WIDTH  = 12
VIEWS_FIELD_WIDTH = 7
PLAYING_FIELD_OFFSET = ID_FIELD_WIDTH + NAME_FIELD_WIDTH + RES_FIELD_WIDTH + VIEWS_FIELD_WIDTH + 6

class QueueFull(Exception): pass
class QueueDuplicate(Exception): pass
class ShelveError(Exception): pass

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

    def put(self, stream, cmd):
        """ Spawn a new background process """

        if len(self.q) < self.max_size:
            if stream['id'] in self.q:
                raise QueueDuplicate
            p = self.call(stream, cmd)
            self.q[stream['id']] = p
        else:
            raise QueueFull

    def get_finished(self):
        """ Clean up terminated processes and returns the list of their ids """
        indices  = []
        for idf, v in self.q.items():
            if v.poll() != None:
                indices.append(idf)

        for i in indices:
            self.q.pop(i)
        return indices

    def get_process(self, idf):
        """ Get a process by id, returns None if there is no match """
        return self.q.get(idf)

    def get_stdouts(self):
        """ Get the list of stdout of each process """
        souts = []
        for v in self.q.values():
            souts.append(v.stdout)
        return souts

    def terminate_process(self, idf):
        """ Terminate a process by id """
        try:
            p = self.q.pop(idf)
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

    def play(self, stream, cmd=['livestreamer']):
        full_cmd = list(cmd)
        for k in stream.keys():
            for i, arg in enumerate(full_cmd):
                if k == 'seen':
                    key = 'views'
                else:
                    key = k
                full_cmd[i] = arg.replace('{{'+key+'}}', stream[k].__str__())
        full_cmd.extend([stream['url'], stream['res']])
        return Popen(full_cmd, stdout=PIPE, stderr=STDOUT)

class StreamList(object):

    def __init__(self, filename, config, list_streams=False, init_stream_list=None):
        """ Init and try to load a stream list, nothing about curses yet """

        global TITLE_STRING

        self.db_was_read = False

        # Open the storage (create it if necessary)
        try:
            db_dir = os.path.dirname(filename)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
            f = shelve.open(filename, 'c')
        except Exception:
            raise ShelveError(
                'Database could not be opened, another livestreamer-curses instance might be already running. '
                'Please note that a database created with Python 2.x cannot be used with Python 3.x and vice versa.'
            )

        self.max_id = 0
        if init_stream_list:
            f['streams'] = init_stream_list
            for i, s in enumerate(f['streams']):
                s['id'] = s.get('id') or i
                s['seen'] = s.get('seen') or 0
                s['last_seen'] = s.get('last_seen') or 0
            self.max_id = i
            f.sync()

        # Sort streams by view count
        try:
            self.streams = sorted(f['streams'], key=lambda s:s['seen'], reverse=True)
            for s in self.streams:
                # Max id, needed when adding a new stream
                self.max_id = max(self.max_id, s['id'])
                s['online'] = 2
            if list_streams:
                print(json.dumps(self.streams))
                f.close()
                sys.exit(0)
        except:
            self.streams = []
        self.db_was_read = True
        self.filtered_streams = list(self.streams)
        self.filter = ''
        self.all_streams_offline = None
        self.show_offline_streams = False
        self.config = config

        TITLE_STRING = TITLE_STRING.format(self.config.VERSION)

        self.cmd_list = list(map(shlex.split, self.config.LIVESTREAMER_COMMANDS))
        self.cmd_index = 0
        self.cmd = self.cmd_list[self.cmd_index]

        self.last_autocheck = 0

        self.default_res = self.config.DEFAULT_RESOLUTION

        self.store = f
        self.store.sync()

        self.no_streams = self.streams == []
        self.no_stream_shown = self.no_streams
        self.q = ProcessList(StreamPlayer().play)

        self.livestreamer = livestreamer.Livestreamer()

    def __del__(self):
        """ Stop playing streams and sync storage """
        try:
            self.q.terminate()
            if self.db_was_read:
                self.store['cmd'] = self.cmd
                self.store['streams'] = self.streams
                self.store.close()
        except:
            pass

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
        self.s.keypad(1)

        self.set_screen_size()

        self.pads = {}
        self.offsets = {}

        self.init_help()
        self.init_streams_pad()
        self.current_pad = 'streams'

        self.set_title(TITLE_STRING)

        self.got_g = False

        signal.signal(28, self.resize)

        if self.config.CHECK_ONLINE_ON_START:
            self.check_online_streams()

        self.set_status('Ready')

    def getheightwidth(self):
        """ getwidth() -> (int, int)

        Return the height and width of the console in characters
        https://groups.google.com/forum/#!msg/comp.lang.python/CpUszNNXUQM/QADpl11Z-nAJ"""
        try:
            return int(os.environ["LINES"]), int(os.environ["COLUMNS"])
        except KeyError:
            height, width = struct.unpack(
                "hhhh", ioctl(0, termios.TIOCGWINSZ ,"\000"*8))[0:2]
            if not height:
                return 25, 80
            return height, width

    def resize(self, signum, obj):
        """ handler for SIGWINCH """
        self.s.clear()
        stream_cursor = self.pads['streams'].getyx()[0]
        for pad in self.pads.values():
            pad.clear()
        self.s.refresh()
        self.set_screen_size()
        self.set_title(TITLE_STRING)
        self.init_help()
        self.init_streams_pad()
        self.move(stream_cursor, absolute=True, pad_name='streams', refresh=False)
        self.s.refresh()
        self.show()

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
            try:
                (r, w, x) = select.select(souts, [], [], 1)
            except select.error:
                continue
            if not r:
                if self.config.CHECK_ONLINE_INTERVAL <= 0: continue
                cur_time = int(time())
                time_delta = cur_time - self.last_autocheck
                if time_delta > self.config.CHECK_ONLINE_INTERVAL:
                    self.check_online_streams()
                    self.set_status('Next check at {0}'.format(
                        strftime('%H:%M:%S', localtime(time() + self.config.CHECK_ONLINE_INTERVAL))
                        ))
                continue
            for fd in r:
                if fd != sys.stdin:
                    # Set the new status line only if non-empty
                    msg = fd.readline()
                    if msg:
                        self.set_status(msg[:-1])
                else:
                    # Main event loop
                    c = self.pads[self.current_pad].getch()
                    if c == curses.KEY_UP or c == ord('k'):
                        self.move(-1)
                    elif c == curses.KEY_DOWN or c == ord('j'):
                        self.move(1)
                    elif c == ord('f'):
                        if self.current_pad == 'streams':
                            self.filter_streams()
                    elif c == ord('F'):
                        if self.current_pad == 'streams':
                            self.clear_filter()
                    elif c == ord('g'):
                        if self.got_g:
                            self.move(0, absolute=True)
                            self.got_g = False
                            continue
                        self.got_g = True
                    elif c == ord('G'):
                        self.move(len(self.filtered_streams)-1, absolute=True)
                    elif c == ord('q'):
                        if self.current_pad == 'streams':
                            self.q.terminate()
                            return
                        else:
                            self.show_streams()
                    elif c == 27: # ESC
                        if self.current_pad != 'streams':
                            self.show_streams()
                    if self.current_pad == 'help':
                        continue
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
                    elif c == ord('l'):
                        self.show_commandline()
                    elif c == ord('L'):
                        self.shift_commandline()
                    elif c == ord('a'):
                        self.prompt_new_stream()
                    elif c == ord('d'):
                        self.delete_stream()
                    elif c == ord('o'):
                        self.show_offline_streams ^= True
                        self.refilter_streams()
                    elif c == ord('O'):
                        self.check_online_streams()
                    elif c == ord('h') or c == ord('?'):
                        self.show_help()

    def set_screen_size(self):
        """ Setup screen size and padding

        We have need 2 free lines at the top and 2 free lines at the bottom

        """
        height, width = self.getheightwidth()
        curses.resizeterm(height, width)
        self.pad_x = 0
        self.max_y, self.max_x = (height-1, width-1)
        self.pad_h = height-3
        self.pad_w = width-2*self.pad_x

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

    def set_footer(self, msg, reverse=True):
        """ Set first footer line text """
        self.s.move(self.max_y-1, 0)
        if reverse:
            self.overwrite_line(msg, attr=curses.A_REVERSE)
        else:
            self.overwrite_line(msg, attr=curses.A_NORMAL)

    def clear_footer(self):
        self.s.move(self.max_y-1, 0)
        self.overwrite_line('')

    def init_help(self):
        help_pad_length = 27    # there should be a neater way to do this
        h = curses.newpad(help_pad_length, self.pad_w)
        h.keypad(1)

        h.addstr( 0, 0, 'STREAM MANAGEMENT', curses.A_BOLD)
        h.addstr( 2, 0, '  Enter : start stream')
        h.addstr( 3, 0, '  s     : stop stream')
        h.addstr( 4, 0, '  r     : change stream resolution')
        h.addstr( 5, 0, '  n     : change stream name')
        h.addstr( 6, 0, '  u     : change stream URL')
        h.addstr( 7, 0, '  c     : reset stream view count')
        h.addstr( 8, 0, '  a     : add stream')
        h.addstr( 9, 0, '  d     : delete stream')

        h.addstr(11, 0, '  l     : show command line')
        h.addstr(12, 0, '  L     : cycle command line')

        h.addstr(15, 0, 'NAVIGATION', curses.A_BOLD)
        h.addstr(17, 0, '  j/up  : up one line')
        h.addstr(18, 0, '  k/down: down one line')
        h.addstr(19, 0, '  f     : filter streams')
        h.addstr(20, 0, '  F     : clear filter')
        h.addstr(21, 0, '  o     : toggle offline streams')
        h.addstr(22, 0, '  O     : check for online streams')
        h.addstr(23, 0, '  gg    : go to top')
        h.addstr(24, 0, '  G     : go to bottom')
        h.addstr(25, 0, '  h/?   : show this help')
        h.addstr(26, 0, '  q     : quit')

        self.pads['help'] = h
        self.offsets['help'] = 0

    def show(self):
        funcs = {
            'streams' : self.show_streams,
            'help'    : self.show_help
        }
        funcs[self.current_pad]()

    def show_help(self):
        """ Redraw Help screen and wait for any input to leave """
        self.s.move(1,0)
        self.s.clrtobot()
        self.set_header('Help'.center(self.pad_w))
        self.set_footer(' ESC or \'q\' to return to main menu')
        self.s.refresh()
        self.current_pad = 'help'
        self.refresh_current_pad()

    def init_streams_pad(self, start_row=0):
        """ Create a curses pad and populate it with a line by stream """
        y = 0
        pad = curses.newpad(max(1,len(self.filtered_streams)), self.pad_w)
        pad.keypad(1)
        for s in self.filtered_streams:
            pad.addstr(y, 0, self.format_stream_line(s))
            y+=1
        self.offsets['streams'] = 0
        pad.move(start_row, 0)
        if not self.no_stream_shown:
            pad.chgat(curses.A_REVERSE)
        self.pads['streams'] = pad

    def show_streams(self):
        self.s.move(1,0)
        self.s.clrtobot()
        self.current_pad = 'streams'
        if self.no_stream_shown:
            self.hide_streams_pad()
            if self.no_streams:
                self.s.addstr(5, 5, 'It seems you don\'t have any stream yet')
                self.s.addstr(6, 5, 'Hit \'a\' to add a new one')
                self.s.addstr(8, 5, 'Hit \'?\' for help')
            elif self.all_streams_offline and not self.show_offline_streams:
                self.s.addstr(5, 5, 'All streams are currently offline')
                self.s.addstr(6, 5, 'Hit \'o\' to show offline streams')
                self.s.addstr(7, 5, 'Hit \'O\' to refresh')
                self.s.addstr(9, 5, 'Hit \'?\' for help')
            else:
                self.s.addstr(5, 5, 'No stream matches your filter')
                self.s.addstr(6, 5, 'Hit \'f\' to change filter')
                self.s.addstr(7, 5, 'Hit \'F\' to clear')
                self.s.addstr(8, 5, 'Hit \'o\' to show offline streams')
                self.s.addstr(10, 5, 'Hit \'?\' for help')
        else:
            idf = 'ID'.center(ID_FIELD_WIDTH)
            name = 'Name'.center(NAME_FIELD_WIDTH)
            res = 'Resolution'.center(RES_FIELD_WIDTH)
            views = 'Views'.center(VIEWS_FIELD_WIDTH)
            self.set_header('{0} {1} {2} {3}  Status'.format(idf, name, res, views))
            self.redraw_stream_footer()
            self.redraw_status()
        self.s.refresh()
        if not self.no_stream_shown:
            self.refresh_current_pad()

    def hide_streams_pad(self):
        pad = self.pads.get('streams')
        if pad:
            pad.refresh(0, 0, 2, 0, 2, 0)

    def refresh_current_pad(self):
        pad = self.pads[self.current_pad]
        pad.refresh(self.offsets[self.current_pad], 0, 2, self.pad_x, self.pad_h, self.pad_w)

    def move(self, direction, absolute=False, pad_name=None, refresh=True):
        """ Scroll the current pad

        direction : (int)  move by one in the given direction
                           -1 is up, 1 is down. If absolute is True,
                           go to position direction.
                           Behaviour is affected by cursor_line and scroll_only below
        absolute  : (bool)
        """

        # pad in this lists have the current line highlighted
        cursor_line = [ 'streams' ]

        # pads in this list will be moved screen-wise as opposed to line-wise
        # if absolute is set, will go all the way top or all the way down depending
        # on direction
        scroll_only = [ 'help' ]

        if not pad_name:
            pad_name = self.current_pad
        pad = self.pads[pad_name]
        if pad_name == 'streams' and self.no_streams:
            return
        (row, col) = pad.getyx()
        new_row    = row
        offset = self.offsets[pad_name]
        new_offset = offset
        if pad_name in scroll_only:
            if absolute:
                if direction > 0:
                    new_offset = pad.getmaxyx()[0] - self.pad_h + 1
                else:
                    new_offset = 0
            else:
                if direction > 0:
                    new_offset = min(pad.getmaxyx()[0] - self.pad_h + 1, offset + self.pad_h)
                elif offset > 0:
                    new_offset = max(0, offset - self.pad_h)
        else:
            if absolute and direction >= 0 and direction < pad.getmaxyx()[0]:
                if direction < offset:
                    new_offset = direction
                elif direction > offset + self.pad_h - 2:
                    new_offset = direction - self.pad_h + 2
                new_row = direction
            else:
                if direction == -1 and row > 0:
                    if row == offset:
                        new_offset -= 1
                    new_row = row-1
                elif direction == 1 and row < len(self.filtered_streams)-1:
                    if row == offset + self.pad_h - 2:
                        new_offset += 1
                    new_row = row+1
        if pad_name in cursor_line:
            pad.move(row, 0)
            pad.chgat(curses.A_NORMAL)
        self.offsets[pad_name] = new_offset
        pad.move(new_row, 0)
        if pad_name in cursor_line:
            pad.chgat(curses.A_REVERSE)
        if pad_name == 'streams':
            self.redraw_stream_footer()
        if refresh:
            self.refresh_current_pad()

    def format_stream_line(self, stream):
        idf = '{0} '.format(stream['id']).rjust(ID_FIELD_WIDTH)
        name = ' {0}'.format(stream['name'][:NAME_FIELD_WIDTH-2]).ljust(NAME_FIELD_WIDTH)
        res  = ' {0}'.format(stream['res'][:RES_FIELD_WIDTH-2]).ljust(RES_FIELD_WIDTH)
        views  = '{0} '.format(stream['seen']).rjust(VIEWS_FIELD_WIDTH)
        p = self.q.get_process(stream['id']) != None
        if p:
            indicator = self.config.INDICATORS[4] # playing
        else:
            indicator = self.config.INDICATORS[stream['online']]
        return '{0} {1} {2} {3}   {4}'.format(idf, name, res, views, indicator)

    def redraw_current_line(self):
        """ Redraw the highlighted line """
        if self.no_streams:
            return
        row = self.pads[self.current_pad].getyx()[0]
        s = self.filtered_streams[row]
        pad = self.pads['streams']
        pad.move(row, 0)
        pad.clrtoeol()
        pad.addstr(row, 0, self.format_stream_line(s), curses.A_REVERSE)
        pad.chgat(curses.A_REVERSE)
        pad.move(row, 0)
        self.refresh_current_pad()

    def set_status(self, status):
        self.status = status
        self.redraw_status()

    def redraw_status(self):
        self.s.move(self.max_y, 0)
        self.overwrite_line(self.status[:self.max_x], curses.A_NORMAL)
        self.s.refresh()

    def redraw_stream_footer(self):
        if not self.no_stream_shown:
            row = self.pads[self.current_pad].getyx()[0]
            s = self.filtered_streams[row]
            self.set_footer('{0}/{1} {2} {3}'.format(row+1, len(self.filtered_streams), s['url'], s['res']))
            self.s.refresh()

    def check_stopped_streams(self):
        finished = self.q.get_finished()
        for f in finished:
            for s in self.streams:
                try:
                    i = self.filtered_streams.index(s)
                except ValueError:
                    continue
                if f == s['id']:
                    self.set_footer('Stream {0} has stopped'.format(s['name']))
                    if i == self.pads[self.current_pad].getyx()[0]:
                        attr = curses.A_REVERSE
                    else:
                        attr = curses.A_NORMAL
                    self.pads['streams'].addstr(i, PLAYING_FIELD_OFFSET,
                                                self.config.INDICATORS[s['online']], attr)
                    self.refresh_current_pad()

    def _check_stream(self, url):
        try:
            plugin = self.livestreamer.resolve_url(url)
            avail_streams = plugin.get_streams()
            if avail_streams:
                return 1
            return 0
        except:
            return 3

    def check_online_streams(self):
        self.all_streams_offline = True
        self.set_status(' Checking online streams...')

        done_queue   = queue.Queue()

        def check_stream_managed(args):
            url, queue = args
            status = self._check_stream(url)
            done_queue.put(url)
            return status

        pool = Pool(self.config.CHECK_ONLINE_THREADS)
        args = [(s['url'], done_queue) for s in self.streams]
        statuses = pool.map_async(check_stream_managed, args)
        n_streams = len(self.streams)

        while not statuses.ready():
            sleep(0.1)
            self.set_status(' Checked {0}/{1} streams...'.format(done_queue.qsize(), n_streams))
            self.s.refresh()

        statuses = statuses.get()
        for i, s in enumerate(self.streams):
            s['online'] = statuses[i]
            if s['online']:
                self.all_streams_offline = False

        self.refilter_streams()
        self.last_autocheck = int(time())

        pool.close()

    def prompt_input(self, prompt=''):
        self.s.move(self.max_y, 0)
        self.s.clrtoeol()
        self.s.addstr(prompt)
        curses.curs_set(1)
        curses.echo()
        r = self.s.getstr().decode()
        curses.noecho()
        curses.curs_set(0)
        self.s.move(self.max_y, 0)
        self.s.clrtoeol()
        return r

    def prompt_confirmation(self, prompt='', def_yes=False):
        self.s.move(self.max_y-1, 0)
        self.s.clrtoeol()
        if def_yes:
            hint = '[y]/n'
        else:
            hint = 'y/[n]'
        self.s.addstr('{0} {1} '.format(prompt, hint))
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

    def clear_filter(self):
        self.filter = ''
        self.refilter_streams()

    def filter_streams(self):
        self.filter = self.prompt_input('Filter: ').lower()
        self.refilter_streams()

    def refilter_streams(self, quiet=False):
        self.filtered_streams = []
        for s in self.streams:
            if ((self.show_offline_streams or s['online'] in [1,2])
                and (self.filter in s['name'].lower() or self.filter in s['url'].lower())):
                self.filtered_streams.append(s)
        self.filtered_streams.sort(key=lambda s:s['seen'], reverse=True)
        self.no_stream_shown = len(self.filtered_streams) == 0
        if not quiet:
            self.status = ' Filter: {0} ({1}/{2} matches, {3} showing offline streams)'.format(
                    self.filter or '<empty>', len(self.filtered_streams), len(self.streams),
                    '' if self.show_offline_streams else 'NOT')
        self.init_streams_pad()
        self.redraw_stream_footer()
        self.show_streams()
        self.redraw_status()

    def add_stream(self, name, url, res=None, bump=False):
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
            if not self.streams:
                idf = 1
            else:
                self.max_id += 1
                idf = self.max_id

            s_res = res or self.default_res

            if type(s_res) == str:
                actual_res = s_res
            elif type(s_res) == dict:
                actual_res = DEFAULT_RESOLUTION_HARD
                for k,v in s_res.items():
                    if k in url:
                        actual_res = v
                        break
            elif callable(s_res):
                actual_res = s_res(url) or DEFAULT_RESOLUTION_HARD
            else:
                actual_res = DEFAULT_RESOLUTION_HARD

            self.set_status(' Checking if new stream is online...')
            self.s.refresh()
            online = self._check_stream(url)

            new_stream = {
                    'id'        : idf,
                    'name'      : name,
                    'seen'      : seen,
                    'last_seen' : last_seen,
                    'res'       : actual_res,
                    'url'       : url,
                    'online'    : online
                }
            self.streams.append(new_stream)
            self.no_streams = False
            self.refilter_streams()
            self.sync_store()

    def delete_stream(self):
        if self.no_streams:
            return
        pad = self.pads[self.current_pad]
        s = self.filtered_streams[pad.getyx()[0]]
        if not self.prompt_confirmation('Delete stream {0}?'.format(s['name'])):
            return
        self.filtered_streams.remove(s)
        self.streams.remove(s)
        pad.deleteln()
        self.sync_store()
        if not self.streams:
            self.no_streams = True
        if not self.filtered_streams:
            self.no_stream_shown = True
        if pad.getyx()[0] == len(self.filtered_streams) and not self.no_stream_shown:
            self.move(-1, refresh=False)
            pad.chgat(curses.A_REVERSE)
        self.redraw_current_line()
        self.show_streams()

    def reset_stream(self):
        if self.no_stream_shown:
            return
        pad = self.pads[self.current_pad]
        s = self.filtered_streams[pad.getyx()[0]]
        if not self.prompt_confirmation('Reset stream {0}?'.format(s['name'])):
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
        pad = self.pads[self.current_pad]
        s = self.filtered_streams[pad.getyx()[0]]
        new_val = self.prompt_input('{0} (empty to cancel): '.format(prompt_info[attr]))
        if new_val != '':
            s[attr] = new_val
            self.redraw_current_line()
        self.redraw_status()
        self.redraw_stream_footer()

    def show_commandline(self):
        self.set_footer('{0}/{1} {2}'.format(self.cmd_index+1, len(self.cmd_list), ' '.join(self.cmd)))

    def shift_commandline(self):
        self.cmd_index += 1
        if self.cmd_index == len(self.cmd_list):
            self.cmd_index = 0
        self.cmd = self.cmd_list[self.cmd_index]
        self.show_commandline()

    def prompt_new_stream(self):
        url = self.prompt_input('New stream URL (empty to cancel): ')
        name = url.split('/')[-1]
        if name:
            self.add_stream(name, url)
            self.move(len(self.filtered_streams)-1, absolute=True, refresh=False)
            self.show_streams()

    def play_stream(self):
        if self.no_stream_shown:
            return
        pad = self.pads[self.current_pad]
        s = self.filtered_streams[pad.getyx()[0]]
        try:
            self.q.put(s, self.cmd)
            self.bump_stream(s, throttle=True)
            self.redraw_current_line()
            self.refresh_current_pad()
        except Exception as e:
            if type(e) == QueueDuplicate:
                self.set_footer('This stream is already playing')
            elif type(e) == OSError:
                self.set_footer('/!\ Faulty command line: {0}'.format(e.strerror))
            else:
                raise e

    def stop_stream(self):
        if self.no_stream_shown:
            return
        pad = self.pads[self.current_pad]
        s = self.filtered_streams[pad.getyx()[0]]
        p = self.q.terminate_process(s['id'])
        if p:
            self.redraw_current_line()
            self.redraw_stream_footer()
            self.redraw_status()
