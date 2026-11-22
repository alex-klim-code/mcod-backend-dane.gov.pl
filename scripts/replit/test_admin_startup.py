"""Isolated diagnostics tests; not substitutes for a live MCOD/VM check."""

import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


class AdminSupervisorTests(unittest.TestCase):
    def run_fixture(self, action):
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory) / "scripts/replit"
            scripts.mkdir(parents=True)
            for name in ("run-admin.sh", "runtime-paths.sh"):
                shutil.copyfile(ROOT / "scripts/replit" / name, scripts / name)
            (scripts / "python.sh").write_text(
                '#!/usr/bin/env bash\n'
                'echo fixture_stdout\n'
                'echo fixture_stderr >&2\n'
                'case "$TEST_ACTION" in\n'
                '  success) exit 0 ;;\n'
                '  failure) exit 23 ;;\n'
                '  signal) kill -TERM $$ ;;\n'
                'esac\n'
            )
            env = dict(os.environ, TEST_ACTION=action)
            env.pop("MCOD_RUNTIME_ROOT", None)
            return subprocess.run(
                ["bash", str(scripts / "run-admin.sh")],
                env=env, capture_output=True, text=True, timeout=10,
            )

    def test_both_child_streams_reach_stderr_with_pid_and_exit(self):
        result = self.run_fixture("success")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        for marker in ("event=before_spawn", "event=process_spawned pid=",
                       "fixture_stdout", "fixture_stderr", "exit_code=0"):
            self.assertIn(marker, result.stderr)
        self.assertLess(result.stderr.index("event=before_spawn"),
                        result.stderr.index("event=process_spawned"))

    def test_failure_status_is_not_changed_to_success(self):
        result = self.run_fixture("failure")
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn("event=process_exit", result.stderr)
        self.assertIn("exit_code=23", result.stderr)

    def test_signal_status_is_preserved(self):
        result = self.run_fixture("signal")
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertIn("exit_code=143", result.stderr)
        self.assertIn("signal_number=15", result.stderr)

    def test_packaged_file_presence_is_reported_without_fake_readiness(self):
        result = self.run_fixture("success")
        self.assertIn("/daphne/cli.py exists=false", result.stderr)
        self.assertNotIn('stage": "listening"', result.stderr)


class AdminBootstrapTests(unittest.TestCase):
    def test_exception_before_daphne_import_is_reported_and_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "daphne"
            package.mkdir()
            (package / "__init__.py").write_text("")
            (package / "cli.py").write_text(
                'raise ImportError("diagnostic_fixture_missing_dependency")\n'
            )
            env = dict(os.environ, PYTHONPATH=directory + os.pathsep + str(ROOT))
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/replit/admin_server.py")],
                env=env, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            for marker in ("entrypoint_enter", "daphne_cli_import_begin",
                           "initialization_exit", "Traceback",
                           "diagnostic_fixture_missing_dependency"):
                self.assertIn(marker, result.stderr)

    def test_blocked_import_dumps_real_stack_without_exiting_on_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "daphne"
            package.mkdir()
            (package / "__init__.py").write_text("")
            (package / "cli.py").write_text("import time\ntime.sleep(60)\n")
            env = dict(
                os.environ, PYTHONPATH=directory + os.pathsep + str(ROOT),
                MCOD_ADMIN_TRACE_SECONDS="0.1",
            )
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts/replit/admin_server.py")],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.communicate(timeout=1)
            finally:
                process.terminate()
                _, stderr = process.communicate(timeout=5)
            self.assertIn("daphne_cli_import_begin", stderr)
            self.assertIn("Timeout", stderr)
            self.assertIn("daphne/cli.py", stderr)
            self.assertNotIn('"stage": "listening"', stderr)

    def test_trace_timer_does_not_exit_process_or_collect_local_variables(self):
        from scripts.replit import startup_diagnostics as diagnostics

        with mock.patch.dict(os.environ, MCOD_STARTUP_DIAGNOSTICS="1"), \
             mock.patch.object(diagnostics.faulthandler, "enable"), \
             mock.patch.object(diagnostics.faulthandler, "dump_traceback_later") as timer, \
             mock.patch("sys.stderr", new_callable=io.StringIO):
            diagnostics.arm_traceback_timer()
        self.assertFalse(timer.call_args.kwargs["exit"])
        self.assertTrue(timer.call_args.kwargs["repeat"])


if __name__ == "__main__":
    unittest.main()
