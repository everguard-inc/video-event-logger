import ctypes
import sys
from typing import Optional


_xlib_handle = None  # type: Optional[ctypes.CDLL]


def initialize_x11_threads(platform_name: Optional[str] = None) -> bool:
    """Initialize Xlib threading before Qt opens the Linux display."""
    if not (platform_name or sys.platform).startswith("linux"):
        return True

    global _xlib_handle
    try:
        _xlib_handle = ctypes.CDLL("libX11.so.6")
        _xlib_handle.XInitThreads.argtypes = []
        _xlib_handle.XInitThreads.restype = ctypes.c_int
        return bool(_xlib_handle.XInitThreads())
    except (AttributeError, OSError):
        _xlib_handle = None
        return False
