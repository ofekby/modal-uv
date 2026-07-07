from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from pathlib import Path

import pathspec

STATE_FILE_NAME = ".last-received-files-state.csv"
BUILTIN_IGNORE_PATTERNS = (
    ".git/",
    ".venv/",
    "node_modules/",
    "**/node_modules/",
    "**/__pycache__/",
    "**/*.py[cod]",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    ".mypy/",
    ".env",
    "uv.lock",
    ".modal-uv/",
)


@dataclass(frozen=True)
class TrackingConfig:
    include: tuple[str, ...] = ("**/*",)
    ignore: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileState:
    path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class FilePayload:
    path: str
    size: int
    mtime_ns: int
    content: bytes

    def write_to(self, root: Path) -> None:
        destination = safe_join(root, self.path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.content)
        if destination.stat().st_size != self.size:
            raise ValueError(f"size mismatch for {self.path}")
        os.utime(destination, ns=(self.mtime_ns, self.mtime_ns))


def build_manifest(repo_root: Path, config: TrackingConfig) -> list[FileState]:
    manifest: list[FileState] = []
    for relative_path in iter_sync_files(repo_root, config):
        stat = (repo_root / relative_path).stat()
        manifest.append(
            FileState(
                path=relative_path.as_posix(),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
        )
    return manifest


def uv_run_command(args: list[str]) -> list[str]:
    return ["uv", "run", "--link-mode", "copy"] + args


def uv_run_env(work_dir: Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    src_path = str(work_dir / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_path}:{existing_pythonpath}" if existing_pythonpath else src_path
    return env


def iter_sync_files(repo_root: Path, config: TrackingConfig) -> tuple[Path, ...]:
    matcher = IgnoreMatcher.load(config.ignore)
    files: list[str] = []

    for dirpath, dirnames, filenames in os.walk(repo_root, topdown=True):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not matcher.is_ignored(
                Path(os.path.relpath(os.path.join(dirpath, dirname), repo_root))
            )
        ]

        for filename in sorted(filenames):
            absolute_path = os.path.join(dirpath, filename)
            rel_posix = os.path.relpath(absolute_path, repo_root).replace(os.sep, "/")

            if matcher.is_ignored(Path(rel_posix)):
                continue
            if not is_included(rel_posix, config.include):
                continue
            files.append(rel_posix)

    return tuple(Path(path) for path in sorted(files))


@dataclass(frozen=True)
class IgnoreMatcher:
    spec: pathspec.PathSpec

    @classmethod
    def load(cls, ignore_patterns: tuple[str, ...] = ()) -> IgnoreMatcher:
        patterns: list[str] = list(BUILTIN_IGNORE_PATTERNS)
        patterns.extend(ignore_patterns)
        return cls(pathspec.PathSpec.from_lines("gitignore", patterns))

    def is_ignored(self, relative_path: Path) -> bool:
        return self.spec.match_file(relative_path.as_posix())


def is_included(rel_posix: str, include_patterns: tuple[str, ...]) -> bool:
    return any(
        pattern == "**/*" or Path(rel_posix).match(pattern) or rel_posix == pattern
        for pattern in include_patterns
    )


def load_state_csv(path: Path) -> list[FileState]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return [
            FileState(
                path=str(row["path"]),
                size=int(row["size"]),
                mtime_ns=int(row["mtime_ns"]),
            )
            for row in reader
        ]


def save_state_csv(path: Path, state: list[FileState]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["path", "size", "mtime_ns"])
        writer.writeheader()
        for item in state:
            writer.writerow(
                {"path": item.path, "size": str(item.size), "mtime_ns": str(item.mtime_ns)}
            )


def plan_sync(work_dir: Path, manifest: list[FileState]) -> list[str]:
    work_dir.mkdir(parents=True, exist_ok=True)
    for item in manifest:
        validate_relative_path(item.path)

    t = time.monotonic()
    state_path = work_dir / STATE_FILE_NAME
    previous = {item.path: item for item in load_state_csv(state_path)}
    current = {item.path: item for item in manifest}
    diff = time.monotonic() - t

    t = time.monotonic()
    for path in sorted(set(previous) - set(current), reverse=True):
        delete_path = safe_join(work_dir, path)
        if delete_path.exists() and delete_path.is_file():
            delete_path.unlink()
            remove_empty_parents(delete_path.parent, work_dir)
    sweep = time.monotonic() - t

    t = time.monotonic()
    missing: list[str] = []
    for item in manifest:
        previous_item = previous.get(item.path)
        if (
            previous_item is None
            or previous_item.size != item.size
            or previous_item.mtime_ns != item.mtime_ns
        ):
            missing.append(item.path)
    compare = time.monotonic() - t

    print(
        f"[modal-uv] plan_sync detail: diff={diff:.6f}s, "
        f"sweep={sweep:.6f}s, compare={compare:.6f}s",
        flush=True,
    )
    return missing


def safe_join(root: Path, relative_path: str) -> Path:
    validate_relative_path(relative_path)
    return root / relative_path


def validate_relative_path(relative_path: str) -> None:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts or not relative_path:
        raise ValueError(f"unsafe path: {relative_path}")


def remove_empty_parents(path: Path, stop_at: Path) -> None:
    stop_at = stop_at.resolve()
    current = path
    while current.resolve() != stop_at and stop_at in current.resolve().parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
