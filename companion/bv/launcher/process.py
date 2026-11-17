"""The companion as the launcher's child: started without a console window, its log lines read
from its output, stopped through its stop file, and tied to the launcher - if the launcher dies,
Windows ends the companion too (a job object that kills its process when the last handle closes)."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from ..__main__ import LAUNCHED, RESTART, STATE_FILE, STOP_FILE
from .. import state as companion_state


class Companion:
    RESTART = RESTART
    ALREADY = 4               # another companion runs (bv/__main__.py ALREADY)
    CONFIG_ERROR = 5          # config.json cannot be read: the player's file, not the version, is at fault
    def __init__(self, app_dir: Path, on_line):
        self.app_dir, self.on_line = Path(app_dir), on_line
        self.proc: subprocess.Popen | None = None
        self.exit_code: int | None = None
        self.job = None
        self.lock = threading.Lock()

    # --- start and stop ---------------------------------------------------------------------

    def start(self, args: list[str] | None = None) -> None:
        with self.lock:
            if self.running:
                return
            STATE_FILE.unlink(missing_ok=True)
            python = Path(sys.executable).with_name("python.exe")
            if not python.exists():
                python = Path(sys.executable)
            env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1", **{LAUNCHED: "1"})
            self.exit_code = None
            self.proc = subprocess.Popen([str(python), "-m", "bv", *(args or [])], cwd=self.app_dir, env=env,
                                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self._tie(self.proc)
            threading.Thread(target=self._read, args=(self.proc,), daemon=True, name="companion-out").start()
            threading.Thread(target=self._read_err, args=(self.proc,), daemon=True, name="companion-err").start()

    def stop(self, timeout: float = 8.0) -> None:
        """Ask the companion to stop (it saves who has which voice), and end it if it does not."""
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        try:
            STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
            STOP_FILE.touch()
        except OSError:
            pass
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
        STOP_FILE.unlink(missing_ok=True)

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def poll(self) -> int | None:
        """The exit code once the companion has ended (and its output is read), else None."""
        if self.proc is None:
            return self.exit_code
        code = self.proc.poll()
        if code is not None:
            self.exit_code = code
        return code

    def state(self) -> dict:
        return companion_state.read(STATE_FILE)

    @staticmethod
    def wants_restart(code: int | None) -> bool:
        return code == RESTART

    # --- inside -----------------------------------------------------------------------------

    def _read(self, proc: subprocess.Popen) -> None:
        with proc.stdout:                # read to its end, then closed: the pipe is this reader's alone
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    self.on_line(line)

    def _read_err(self, proc: subprocess.Popen) -> None:
        """The companion's stderr apart from its log lines: Python's own stderr it turns into log lines
        itself, so what comes here is what libraries write below Python (onnxruntime, Rust downloaders)
        - often a bar without a line end, which on one pipe glued itself to the next log line and hid it."""
        from datetime import datetime

        from ..logs import raw_line
        with proc.stderr:
            for raw in proc.stderr:
                line = raw_line(raw.decode("utf-8", "replace"), datetime.now())
                if line:
                    self.on_line(line)

    def _tie(self, proc: subprocess.Popen) -> None:
        """The companion ends with the launcher. Programs the companion starts (Battle.net) are not
        tied: SILENT_BREAKAWAY lets them out of the job."""
        if sys.platform != "win32":
            return
        try:
            import win32api
            import win32con
            import win32job
            if self.job is None:
                self.job = win32job.CreateJobObject(None, "")
                info = win32job.QueryInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation)
                info["BasicLimitInformation"]["LimitFlags"] |= (win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                                                               | win32job.JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK)
                win32job.SetInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation, info)
            handle = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, proc.pid)
            win32job.AssignProcessToJobObject(self.job, handle)
        except Exception as e:  # noqa: BLE001 - without it the companion may outlive a killed launcher
            self.on_line(f"{time.strftime('%H:%M:%S')} [лаунчер] не удалось привязать компаньон к лаунчеру: {e}")
