## Livestreamer-curses

Livestreamer-curses is a limited front-end to Chrippa's [Livestreamer](https://github.com/chrippa/livestreamer) for UNIX systems.
With it you can manage a list of your favorite streams and play them (several at a time if your connection can handle it).

![screenshot](http://s14.postimg.org/ctfx2bvbl/main.png)

### Usage

Install using `pip install livestreamer-curses` which will provide the `livestreamer-curses` command

To change the way to call `livestreamer`, use the configuration file (default: `~/.livestreamer-cursesrc`).
See sample file for usage.

### Changelog

* v1.1.0 (25 May 2014)
    * Feature: Added a way to check and filter offline streams. Use `O` to refresh and `o` to toggle showing offline. See also `CHECK_ONLINE_ON_START` option to perform this check when starting `livestreamer-curses`.
    * Bugfixes: Better handling of special keys and configuration file

* v1.0.0 (24 Feb. 2014)
    * *Backward incompatible changes*: change project structure to accomodate
      for distutils
    * Feature: Added `-d` and  `-f` options for custom database and config
      file locations, respectively.

* v0.32 (23 Feb. 2014)
    * Buxgix: Actually use selected command line (how did I miss this?!)

* v0.31 (09 Jan. 2014)
    * Buxgix: Streams are now properly sorted when filtering

* v0.3 (09 Jan. 2014)
    * Feature: .livestreamer-cursesrc file which comes with 2 configuration options, see livestreamer-cursesrc.sample

* v0.2 (22 Dec. 2013)
    * Feature: filter streams with `f` key, clear it with `F`

### Dependencies

* [Livestreamer](https://github.com/chrippa/livestreamer)
