Livestreamer-curses
-------------------

Livestreamer-curses is a limited front-end to Chrippa's
`Livestreamer <https://github.com/chrippa/livestreamer>`__ for UNIX
systems. With it you can manage a list of your favorite streams and play
them (several at a time if your connection can handle it).

.. figure:: http://s30.postimg.org/j310vhhkh/screenshot.png
   :alt: screenshot

   screenshot

Usage
~~~~~

Install using ``pip install livestreamer-curses`` which will provide the
``livestreamer-curses`` command

To change the way to call ``livestreamer``, use the configuration file
(see ``livestreamer-curses -h`` for default location). See sample file for configuration options.

Changelog
~~~~~~~~~

-  v1.5.2 (2015-02-18)

   - Bugfixes: Fix imports

-  v1.5.0 (2015-02-17)

   - Feature: Periodically check if streams are online (foreground and blocking, for now). Corresponding configuration variable: ``CHECK_ONLINE_INTERVAL``

-  v1.4.0 (2014-11-13)

   - Feature: Templatable command line

-  v1.3.0 (2014-09-25)

   -  Feature: Follow XDG specification, *you need to move your old rc and .db files, use -h flag to see where*
   -  Feature: Add options to overwrite/dump the database from a/to a file

   -  Bugfix: dbm issue on Mac OS X

-  v1.2.0 (2014-05-29)

   -  Feature: Python 3 support

   -  Bugfixes: Window resizing

-  v1.1.0 (2014-05-25)

   -  Feature: Added a way to check and filter offline streams. Use ``O`` to refresh and ``o`` to toggle showing offline. See also ``CHECK_ONLINE_ON_START`` option to perform this check when starting ``livestreamer-curses``.

   -  Bugfixes: Better handling of special keys and configuration file

-  v1.0.0 (2014-02-24)

   -  *Backward incompatible changes*: change project structure to
      accomodate for distutils
   -  Feature: Added ``-d`` and ``-f`` options for custom database and
      config file locations, respectively.

-  v0.32 (2014-02-23)

   -  Buxgix: Actually use selected command line (how did I miss this?!)

-  v0.31 (2014-01-09)

   -  Buxgix: Streams are now properly sorted when filtering

-  v0.3 (2014-01-09)

   -  Feature: .livestreamer-cursesrc file which comes with 2
      configuration options, see livestreamer-cursesrc.sample

-  v0.2 (2013-12-22)

   -  Feature: filter streams with ``f`` key, clear it with ``F``

Dependencies
~~~~~~~~~~~~

-  `Livestreamer <https://github.com/chrippa/livestreamer>`__

