#!/usr/bin/env python

from setuptools import setup
from os.path import join, dirname, abspath
from sys import path

srcdir = join(dirname(abspath(__file__)), "src/")
path.insert(0, srcdir)

import livestreamer_curses.main as lsc

setup(name="livestreamer-curses",
      version=lsc.VERSION_STRING,
      description="Livestreamer is CLI program that extracts streams from "
                  "various services and pipes them into a video player of "
                  "choice.",
      url="http://github.com/gapato/livestreamer-curses",
      author="Gaspard Jankowiak",
      author_email="gaspard@oknaj.eu",
      license="MIT",
      packages = [ "livestreamer_curses" ],
      package_dir={ "": "src" },
      entry_points={
          "console_scripts": ["livestreamer-curses=livestreamer_curses.main:main"]
      },
      classifiers=["Operating System :: POSIX",
                   "Environment :: Console :: Curses",
                   "Development Status :: 4 - Beta",
                   "License :: OSI Approved :: MIT License",
                   "Topic :: Utilities"]
)
