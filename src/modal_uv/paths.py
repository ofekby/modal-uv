"""Path helpers for modal-uv daemon files."""

from __future__ import annotations

from pathlib import Path

REPO_STATE_DIR = ".modal-uv"
DAEMON_PID_FILE = "daemon.pid"
DAEMON_SOCK_FILE = "daemon.sock"
DAEMON_LOG_FILE = "daemon.log"


def repo_state_dir(repo_root: Path) -> Path:
    """Return the repo-local generated state directory."""
    return repo_root / REPO_STATE_DIR


def daemon_paths(repo_root: Path) -> tuple[Path, Path]:
    """Return (pid_path, sock_path) for the daemon."""
    state_dir = repo_state_dir(repo_root)
    return state_dir / DAEMON_PID_FILE, state_dir / DAEMON_SOCK_FILE


def daemon_log_path(repo_root: Path) -> Path:
    """Return the daemon log path for the repo."""
    return repo_state_dir(repo_root) / DAEMON_LOG_FILE


def ensure_repo_state(repo_root: Path) -> None:
    """Create repo-local state and ensure it is ignored by git."""
    repo_state_dir(repo_root).mkdir(parents=True, exist_ok=True)
    _ensure_gitignore_entry(repo_root / ".gitignore")


def _ensure_gitignore_entry(gitignore_path: Path) -> None:
    entry = f"{REPO_STATE_DIR}/"
    if not gitignore_path.exists():
        gitignore_path.write_text(f"{entry}\n", encoding="utf-8")
        return

    content = gitignore_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    if entry in lines or REPO_STATE_DIR in lines:
        return

    separator = "" if content.endswith("\n") or not content else "\n"
    gitignore_path.write_text(f"{content}{separator}{entry}\n", encoding="utf-8")
