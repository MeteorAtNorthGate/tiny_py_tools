"""Recovery must never terminate a visible capture or a foreign process."""
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from sop_studio.windows_snipping import repair_windows_snipping


class WindowsRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("sop_studio.windows_snipping.sys.platform", "win32"))
        self.enterContext(patch.dict(os.environ, {"SystemRoot": r"C:\Windows"}))
        self.state = self.enterContext(patch("sop_studio.windows_snipping.snipping_window_state", return_value=(False, False)))
        self.kernel = Mock()
        self.kernel.CreateToolhelp32Snapshot.return_value = 99
        self.kernel.GetCurrentProcessId.return_value = 100
        self.kernel.OpenProcess.side_effect = lambda access, inherit, pid: pid + 1000
        self.kernel.TerminateProcess.return_value = True
        self.libraries = self.enterContext(patch("sop_studio.windows_snipping._libraries", return_value=(Mock(), self.kernel)))

    def processes(self, entries, sessions, paths):
        remaining = iter(entries)

        def next_entry(snapshot, pointer):
            entry = next(remaining, None)
            if entry is None:
                return False
            pointer._obj.pid, pointer._obj.name = entry
            return True

        def session_id(pid, pointer):
            pointer._obj.value = sessions.get(pid, 1)
            return True

        self.kernel.Process32FirstW.side_effect = next_entry
        self.kernel.Process32NextW.side_effect = next_entry
        self.kernel.ProcessIdToSessionId.side_effect = session_id
        self.enterContext(patch("sop_studio.windows_snipping._process_path", side_effect=lambda kernel, process: paths.get(process - 1000)))

    def test_visible_capture_or_tool_prevents_any_process_cleanup(self):
        for visible in [(True, False), (False, True)]:
            with self.subTest(visible=visible):
                self.state.return_value = visible
                self.assertEqual(repair_windows_snipping(), 0)
        self.libraries.assert_not_called()

    def test_cleanup_is_limited_to_system_host_in_current_session(self):
        self.processes([(1, "ScreenClippingHost.exe"), (2, "ScreenClippingHost.exe"),
                        (3, "ScreenClippingHost.exe"), (4, "SnippingTool.exe")],
                       {1: 2},
                       {2: Path(r"C:\Other\ScreenClippingHost.exe"),
                        3: Path(r"C:\Windows\SystemApps\Windows.Core\ScreenClippingHost.exe")})
        self.assertEqual(repair_windows_snipping(), 1)
        self.kernel.TerminateProcess.assert_called_once_with(1003, 1)
        self.assertEqual(self.kernel.OpenProcess.call_count, 2)
        self.kernel.CloseHandle.assert_any_call(1002)
        self.kernel.CloseHandle.assert_any_call(1003)
        self.kernel.CloseHandle.assert_any_call(99)

    def test_capture_appearing_during_inspection_prevents_termination(self):
        self.processes([(3, "ScreenClippingHost.exe")], {},
                       {3: Path(r"C:\Windows\SystemApps\Windows.Core\ScreenClippingHost.exe")})
        self.state.side_effect = [(False, False), (True, False)]
        self.assertEqual(repair_windows_snipping(), 0)
        self.kernel.TerminateProcess.assert_not_called()
        self.kernel.CloseHandle.assert_any_call(1003)
        self.kernel.CloseHandle.assert_any_call(99)


if __name__ == "__main__":
    unittest.main()
