"""Inspect and recover the current Windows session's screenshot UI."""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path


def _libraries():
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                               wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    return user, kernel


def _process_path(kernel, process):
    path = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(path))
    if kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
        return Path(path.value)
    return None


def snipping_window_state() -> tuple[bool, bool]:
    """Return (capture overlay visible, standalone Snipping Tool visible)."""
    if sys.platform != "win32":
        return False, False
    user, kernel = _libraries()
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    state = [False, False]

    @callback_type
    def inspect(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not process:
            return True
        try:
            path = _process_path(kernel, process)
        finally:
            kernel.CloseHandle(process)
        if path is not None and path.name.lower() == "screenclippinghost.exe":
            state[0] = True
        elif path is not None and path.name.lower() == "snippingtool.exe":
            name = ctypes.create_unicode_buffer(256)
            user.GetClassNameW(hwnd, name, len(name))
            if "snipper" in name.value.lower() and any(part in name.value.lower() for part in ("toolbar", "capture", "overlay")):
                state[0] = True
            else:
                state[1] = True
        return True

    if not user.EnumWindows(inspect, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return tuple(state)


def wake_windows_snipping():
    """Starting the tool itself also wakes hosts whose protocol activation stalled."""
    if sys.platform != "win32":
        raise OSError("系统截图仅支持 Windows。")
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "SnippingTool.exe"
    os.startfile(str(executable))


def repair_windows_snipping() -> int:
    """Restart only an invisible system clipping host in our own session."""
    if sys.platform != "win32" or any(snipping_window_state()):
        return 0
    _, kernel = _libraries()

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                    ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
                    ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priority", wintypes.LONG),
                    ("flags", wintypes.DWORD), ("name", wintypes.WCHAR * 260)]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for function in (kernel.Process32FirstW, kernel.Process32NextW):
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        function.restype = wintypes.BOOL
    kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    session = wintypes.DWORD()
    if not kernel.ProcessIdToSessionId(kernel.GetCurrentProcessId(), ctypes.byref(session)):
        raise ctypes.WinError(ctypes.get_last_error())
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    repaired = 0
    system_apps = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "SystemApps"
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        available = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            other_session = wintypes.DWORD()
            if (entry.name.lower() == "screenclippinghost.exe"
                    and kernel.ProcessIdToSessionId(entry.pid, ctypes.byref(other_session))
                    and other_session.value == session.value):
                process = kernel.OpenProcess(0x1001, False, entry.pid)  # QUERY_LIMITED_INFORMATION | TERMINATE
                if process:
                    try:
                        path = _process_path(kernel, process)
                        # Recheck immediately before termination; never interrupt an active snip.
                        if (path is not None and path.name.lower() == "screenclippinghost.exe"
                                and path.is_relative_to(system_apps) and not any(snipping_window_state())):
                            repaired += bool(kernel.TerminateProcess(process, 1))
                    finally:
                        kernel.CloseHandle(process)
            available = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return repaired
