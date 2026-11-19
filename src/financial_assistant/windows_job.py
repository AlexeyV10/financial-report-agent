"""Own one trusted worker tree with an unnamed Windows Job Object."""

import ctypes
from ctypes import wintypes
import os


_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "read_operations", "write_operations", "other_operations",
        "read_transferred", "write_transferred", "other_transferred",
    )]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", _IoCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


def _kernel_api():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                               ctypes.c_void_p, wintypes.DWORD)
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


class WindowsJob:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows Job Objects unavailable")
        self._kernel = _kernel_api()
        # NULL attributes create a non-inheritable handle, NULL name avoids sharing it.
        self._handle = self._kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.basic.flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._kernel.SetInformationJobObject(self._handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                                    ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def attach(self, worker):
        # CPython Popen retains the exact CreateProcess handle until cleanup.
        # A PID lookup could refer to a different process after ID reuse.
        process_handle = getattr(worker, "_handle", None)
        if not self._handle or not process_handle:
            raise OSError("Worker process handle unavailable")
        if not self._kernel.AssignProcessToJobObject(self._handle, int(process_handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self._handle:
            if not self._kernel.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = None
