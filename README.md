## Livestreamer-curses

Livestreamer-curses is a limited front-end to Chrippa's [Livestreamer](https://github.com/chrippa/livestreamer) for UNIX systems.
With it you can manage a list of your favorite streams and play them (several at a time if your connection can handle it).

![screenshot](http://s14.postimg.org/ctfx2bvbl/main.png)

### Usage

Clone this repo and run `python livestreamer-curses.py`. This will initialize the database in `$HOME/.livestreamer-curses.db`
and ask you to add streams.

To change the way to call `livestreamer`, use the configuration file (location hardcoded as `$HOME/.livestreamer-cursesrc` for now).
See sample file for usage.

### Planned features
* Custom locations for configuration file, streams database.
* ...

### Changelog

* v0.31 (09 Jan. 2014)
    * Buxgix: Streams are now properly sorted when filtering

* v0.3 (09 Jan. 2014)
    * Feature: .livestreamer-cursesrc file which comes with 2 configuration options, see livestreamer-cursesrc.sample

* v0.2 (22 Dec. 2013)
    * Feature: filter streams with `f` key, clear it with `F`

### Dependencies

* [Livestreamer](https://github.com/chrippa/livestreamer)
