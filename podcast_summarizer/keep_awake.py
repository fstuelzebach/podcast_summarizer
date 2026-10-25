"""Stop Windows from sleeping mid-run.

A PC woken by a scheduled task falls back asleep after ~2 minutes unless a
process asks for "system required" (same mechanism as olymp-capital's
scheduler). No-op on other platforms.
"""
import sys
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextmanager
def keep_awake():
    if sys.platform != "win32":
        yield
        return
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)
