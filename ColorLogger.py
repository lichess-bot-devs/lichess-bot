"""
@file: Colorer.py

Script which allows colored logging output with multiplattform support.
The script is based on this post and was slightly adjusted:
# https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output

'Here is a solution that should work on any platform. If it doesn't just tell me and I will update it.

How it works: on platform supporting ANSI escapes is using them (non-Windows) and on Windows
it does use API calls to change the console colors.

The script does hack the logging.StreamHandler.emit method from standard library adding a wrapper to it.'

by Sorin & Dave
"""

import logging
import sys
import platform


def add_coloring_to_emit_windows(fn):
    # patch Python code to add color support to logging.StreamHandler

    # add methods we need to the class
    def _out_handle(self):
        import ctypes
        return ctypes.windll.kernel32.GetStdHandle(self.STD_OUTPUT_HANDLE)

    # noinspection PyUnusedLocal
    out_handle = property(_out_handle)

    def _set_color(self, code):
        import ctypes
        # Constants from the Windows API
        self.STD_OUTPUT_HANDLE = -11
        hdl = ctypes.windll.kernel32.GetStdHandle(self.STD_OUTPUT_HANDLE)
        ctypes.windll.kernel32.SetConsoleTextAttribute(hdl, code)

    setattr(logging.StreamHandler, '_set_color', _set_color)

    # noinspection PyPep8Naming,PyUnusedLocal
    def new(*args):
        FOREGROUND_BLUE = 0x0001  # text color contains blue.
        FOREGROUND_GREEN = 0x0002  # text color contains green.
        FOREGROUND_RED = 0x0004  # text color contains red.
        FOREGROUND_INTENSITY = 0x0008  # text color is intensified.
        FOREGROUND_WHITE = FOREGROUND_BLUE | FOREGROUND_GREEN | FOREGROUND_RED
        # winbase.h
        STD_INPUT_HANDLE = -10
        STD_OUTPUT_HANDLE = -11
        STD_ERROR_HANDLE = -12

        # wincon.h
        FOREGROUND_BLACK = 0x0000
        FOREGROUND_BLUE = 0x0001
        FOREGROUND_GREEN = 0x0002
        FOREGROUND_CYAN = 0x0003
        FOREGROUND_RED = 0x0004
        FOREGROUND_MAGENTA = 0x0005
        FOREGROUND_YELLOW = 0x0006
        FOREGROUND_GREY = 0x0007
        FOREGROUND_INTENSITY = 0x0008  # foreground color is intensified.

        BACKGROUND_BLACK = 0x0000
        BACKGROUND_BLUE = 0x0010
        BACKGROUND_GREEN = 0x0020
        BACKGROUND_CYAN = 0x0030
        BACKGROUND_RED = 0x0040
        BACKGROUND_MAGENTA = 0x0050
        BACKGROUND_YELLOW = 0x0060
        BACKGROUND_GREY = 0x0070
        BACKGROUND_INTENSITY = 0x0080  # background color is intensified.

        levelno = args[1].levelno
        if levelno >= 50:
            color = BACKGROUND_YELLOW | FOREGROUND_RED | FOREGROUND_INTENSITY | BACKGROUND_INTENSITY
        elif levelno >= 40:
            color = FOREGROUND_RED | FOREGROUND_INTENSITY
        elif levelno >= 30:
            color = FOREGROUND_YELLOW | FOREGROUND_INTENSITY
        elif levelno >= 20:
            color = FOREGROUND_GREEN
        elif levelno >= 10:
            color = FOREGROUND_MAGENTA
        else:
            color = FOREGROUND_WHITE
        # noinspection PyProtectedMember
        args[0]._set_color(color)

        ret = fn(*args)
        # noinspection PyProtectedMember
        args[0]._set_color(FOREGROUND_WHITE)
        # print "after"
        return ret

    return new


def add_coloring_to_emit_ansi(fn):
    # add methods we need to the class
    def new(*args):
        levelno = args[1].levelno
        if levelno >= 50:
            color = '\x1b[31m'  # red
        elif levelno >= 40:
            color = '\x1b[31m'  # red
        elif levelno >= 30:
            color = '\x1b[33m'  # yellow
        elif levelno >= 20:
            color = '\x1b[94m'  # light blue
        elif levelno >= 10:
            color = '\x1b[32m'  # green
            # color = '\x1b[90m' # bright black
            #
            # #'\x1b[35m' # pink
        else:
            color = '\x1b[0m'  # normal
        args[1].msg = f'{color}  {args[1].msg}\x1b[0m'  # normal
        # print "after"
        return fn(*args)

    return new


def enable_color_logging(debug_lvl=logging.DEBUG):
    if platform.system() == 'Windows':
        # Windows does not support ANSI escapes and we are using API calls to set the console color
        logging.StreamHandler.emit = add_coloring_to_emit_windows(logging.StreamHandler.emit)
    else:
        # all non-Windows platforms are supporting ANSI escapes so we use them
        logging.StreamHandler.emit = add_coloring_to_emit_ansi(logging.StreamHandler.emit)

    root = logging.getLogger()
    root.setLevel(debug_lvl)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(debug_lvl)

    # FORMAT from https://github.com/xolox/python-coloredlogs
    FORMAT = '%(asctime)s %(name)s[%(process)d] \033[1m%(levelname)s\033[0m %(message)s'
    formatter = logging.Formatter(FORMAT, "%Y-%m-%d %H:%M:%S")

    ch.setFormatter(formatter)
