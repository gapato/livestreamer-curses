## Livestreamer-curses

Livestreamer-curses is a limited front-end to Chrippa's [Livestreamer](https://github.com/chrippa/livestreamer) for UNIX systems.
With it you can manage a list of your favorite streams and play them (several at a time if your connection can handle it).

![screenshot](http://s14.postimg.org/ctfx2bvbl/main.png)

### Usage

Clone this repo and run `python livestreamer-curses.py`. This will initialize the database in `$HOME/.livestreamer-curses.db`
and ask you to add streams.

Hit `l` to show the current livestreamer command line options, _i.e._ how will livestreamer by called. To edit it, hit `L`.
The stream URL and resolution will be appended automatically. For example, to use a different player (on a Mac, for example, I guess),
hit `L` and type `livestreamer -p /path/to/your/player`.

**Note:** livestreamer (or whatever program you set) will be called via python's `subprocess.Popen` without shell support.
That means that you cannot use redirections (`>`) or pipes (`|`).

### Changelog

#### v0.2 (22 Dec. 2013)
* Feature: filter streams with `f` key, clear it with `F`

### Dependencies

* [Livestreamer](https://github.com/chrippa/livestreamer)
