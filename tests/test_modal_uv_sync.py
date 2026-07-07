from __future__ import annotations

from pathlib import Path

import pytest

from modal_uv.sync import (
    FilePayload,
    FileState,
    TrackingConfig,
    build_manifest,
    load_state_csv,
    plan_sync,
    save_state_csv,
    uv_run_command,
    uv_run_env,
)


def _config(include: tuple[str, ...] = ("**/*",), ignore: tuple[str, ...] = ()) -> TrackingConfig:
    return TrackingConfig(include=include, ignore=ignore)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_manifest_uses_configured_sync_ignore(tmp_path: Path) -> None:
    _write(tmp_path / "src/app.py", "print('hi')")
    _write(tmp_path / "src/app.log", "ignore me")
    _write(tmp_path / ".git/config", "ignore me")

    manifest = build_manifest(tmp_path, _config(include=("src/**",), ignore=("*.log",)))

    assert [item.path for item in manifest] == ["src/app.py"]
    assert manifest[0].size == len("print('hi')")
    assert manifest[0].mtime_ns > 0


def test_build_manifest_ignores_modal_uv_state_dir(tmp_path: Path) -> None:
    _write(tmp_path / "src/app.py", "print('hi')")
    _write(tmp_path / ".modal-uv/deployment.py", "generated")

    manifest = build_manifest(tmp_path, _config())

    assert [item.path for item in manifest] == ["src/app.py"]


def test_build_manifest_does_not_read_s3_sync_ignore(tmp_path: Path) -> None:
    _write(tmp_path / "src/app.py", "print('hi')")
    _write(tmp_path / "src/app.log", "do not ignore")
    _write(tmp_path / ".s3-sync-ignore", "*.log\n")

    manifest = build_manifest(tmp_path, _config(include=("src/**",)))

    assert [item.path for item in manifest] == ["src/app.log", "src/app.py"]


def test_build_manifest_ignores_node_modules_directories(tmp_path: Path) -> None:
    _write(tmp_path / "src/app.py", "print('hi')")
    _write(tmp_path / "node_modules/pkg/index.js", "ignore me")
    _write(tmp_path / ".opencode/node_modules/pkg/index.js", "ignore me")

    manifest = build_manifest(tmp_path, _config())

    assert [item.path for item in manifest] == ["src/app.py"]


def test_build_manifest_ignores_local_environment_and_lock_files(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[project]\nname = 'demo'\n")
    _write(tmp_path / "uv.lock", "local lock")
    _write(tmp_path / ".env", "SECRET=value")

    manifest = build_manifest(tmp_path, _config())

    assert [item.path for item in manifest] == ["pyproject.toml"]


def test_uv_run_command_uses_container_image_dependencies() -> None:
    command = uv_run_command(["python", "-m", "lab"])

    assert command == ["uv", "run", "--link-mode", "copy", "python", "-m", "lab"]


def test_uv_run_env_adds_src_to_pythonpath(tmp_path: Path) -> None:
    env = uv_run_env(tmp_path, {"PYTHONPATH": "/existing"})

    assert env["PYTHONPATH"] == f"{tmp_path / 'src'}:/existing"


def test_state_csv_round_trips_paths_size_and_mtime(tmp_path: Path) -> None:
    path = tmp_path / "state.csv"
    state = [
        FileState(path="src/a.py", size=10, mtime_ns=100),
        FileState(path="nested/data.csv", size=20, mtime_ns=200),
    ]

    save_state_csv(path, state)

    assert load_state_csv(path) == state


def test_plan_sync_returns_missing_and_stale_paths_and_deletes_extras(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    _write(work_dir / "old.py", "old")
    _write(work_dir / "stale.py", "old stale")
    _write(work_dir / "same.py", "same")
    save_state_csv(
        work_dir / ".last-received-files-state.csv",
        [
            FileState(path="old.py", size=3, mtime_ns=1),
            FileState(path="stale.py", size=9, mtime_ns=1),
            FileState(path="same.py", size=4, mtime_ns=1),
        ],
    )

    missing = plan_sync(
        work_dir,
        [
            FileState(path="missing.py", size=7, mtime_ns=1),
            FileState(path="stale.py", size=10, mtime_ns=1),
            FileState(path="same.py", size=4, mtime_ns=1),
        ],
    )

    assert missing == ["missing.py", "stale.py"]
    assert not (work_dir / "old.py").exists()
    assert (work_dir / "same.py").exists()


def test_plan_sync_rejects_unsafe_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe path"):
        plan_sync(tmp_path, [FileState(path="../escape.py", size=1, mtime_ns=1)])


def test_file_payload_writes_bytes_and_preserves_state(tmp_path: Path) -> None:
    payload = FilePayload(
        path="src/app.py",
        size=5,
        mtime_ns=1_700_000_000_000_000_000,
        content=b"hello",
    )

    payload.write_to(tmp_path)

    written = tmp_path / "src/app.py"
    assert written.read_bytes() == b"hello"
    assert written.stat().st_size == 5
    assert written.stat().st_mtime_ns == payload.mtime_ns
