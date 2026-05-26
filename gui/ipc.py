"""
Non-blocking daemon IPC for GUI.
Uses QThread to avoid freezing the UI on socket calls.
"""

import json
import socket

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

SOCKET_PATH = "/tmp/omen-hub.sock"


def send_command(cmd: dict, timeout: float = 2.0) -> dict | None:
    """Synchronous send — use only from worker threads, not the GUI thread."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(SOCKET_PATH)
            s.sendall(json.dumps(cmd).encode())
            data = s.recv(4096).decode()
            return json.loads(data)
    except (ConnectionRefusedError, FileNotFoundError):
        return None
    except OSError:
        return None


class StatusPoller(QObject):
    """
    Polls daemon status on a background thread.
    Emits status_updated with the response dict, or daemon_offline if unreachable.
    """
    status_updated = pyqtSignal(dict)
    daemon_offline  = pyqtSignal()

    @pyqtSlot()
    def poll(self) -> None:
        resp = send_command({"action": "status"})
        if resp and resp.get("ok"):
            self.status_updated.emit(resp)
        else:
            self.daemon_offline.emit()


class SetModeWorker(QObject):
    """Apply mode: power profile + fan control via daemon IPC."""
    done = pyqtSignal(bool)

    def __init__(self, mode: str):
        super().__init__()
        self._mode = mode

    @pyqtSlot()
    def run(self) -> None:
        import subprocess
        from pathlib import Path
        scripts = {
            "silent":      "fmin.sh",
            "balanced":    "fbal.sh",
            "performance": "fmax.sh",
        }
        script = Path(__file__).parent.parent / "scripts" / scripts[self._mode]
        subprocess.run(["/bin/bash", str(script)])
        self.done.emit(True)
