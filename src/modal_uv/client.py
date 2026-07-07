"""Client for communicating with the modal-uv daemon via httpx over Unix socket."""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from modal_uv.paths import daemon_log_path, daemon_paths

DAEMON_STARTUP_TIMEOUT = 10.0
REQUEST_TIMEOUT = 60.0


def ensure_daemon(config_path: Path, repo_root: Path) -> httpx.Client:
    """Ensure a daemon is running and return an httpx client."""
    pid_path, sock_path = daemon_paths(repo_root)

    if not _daemon_alive(pid_path, sock_path):
        _spawn_daemon(config_path, repo_root)
        _wait_for_socket(sock_path)

    transport = httpx.HTTPTransport(uds=str(sock_path))
    return httpx.Client(transport=transport, timeout=REQUEST_TIMEOUT)


def send_request(client: httpx.Client, path: str, request: dict) -> dict:
    """Send a JSON POST to a path and receive a JSON response."""
    resp = client.post(f"http://localhost{path}", json=request)
    resp.raise_for_status()
    return resp.json()


def stop_daemon(repo_root: Path) -> bool:
    """Stop the daemon if running. Returns True if a daemon was stopped."""
    pid_path, sock_path = daemon_paths(repo_root)

    if not pid_path.exists():
        return False

    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError):
        _cleanup(pid_path, sock_path)
        return False

    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, 15)

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and sock_path.exists():
        time.sleep(0.05)

    _cleanup(pid_path, sock_path)
    return True


def daemon_status(repo_root: Path) -> dict | None:
    """Return daemon status or None if not running."""
    pid_path, sock_path = daemon_paths(repo_root)

    if not _daemon_alive(pid_path, sock_path):
        return None

    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError):
        return None

    return {"pid": pid, "socket": str(sock_path)}


def _daemon_alive(pid_path: Path, sock_path: Path) -> bool:
    if not pid_path.exists() or not sock_path.exists():
        return False
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        _cleanup(pid_path, sock_path)
        return False


def _spawn_daemon(config_path: Path, repo_root: Path) -> None:
    log_path = daemon_log_path(repo_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as log_file:
        subprocess.Popen(
            [sys.executable, "-m", "modal_uv.daemon", str(config_path), str(repo_root)],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _wait_for_socket(sock_path: Path) -> None:
    deadline = time.monotonic() + DAEMON_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if sock_path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"daemon socket not created within {DAEMON_STARTUP_TIMEOUT}s")


def _cleanup(pid_path: Path, sock_path: Path) -> None:
    pid_path.unlink(missing_ok=True)
    sock_path.unlink(missing_ok=True)
