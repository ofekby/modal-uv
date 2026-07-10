"""Tests for modal-uv config loading."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from modal_uv.config import ConfigError, load_config, resolve_project
from modal_uv.paths import daemon_log_path, daemon_paths, ensure_repo_state


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "modal-uv.yaml"
    path.write_text(dedent(content))
    return path


def test_minimal_valid_yaml(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          gpu: "T4"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(path)
    assert config.app_name == "test-app"
    assert not hasattr(config, "gpu")
    assert config.runtime.gpu == "T4"
    assert config.volumes[0].name == "test-volume"


def test_resolve_project_walks_up_from_nested_directory(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    nested = tmp_path / "src" / "package"
    nested.mkdir(parents=True)

    project = resolve_project(start=nested)

    assert project.repo_root == tmp_path
    assert project.config_path == path


def test_resolve_project_uses_config_parent_when_explicit(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()

    project = resolve_project(path, start=unrelated)

    assert project.repo_root == tmp_path
    assert project.config_path == path


def test_resolve_project_missing_yaml_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="modal-uv.yaml"):
        resolve_project(start=tmp_path)


def test_daemon_paths_live_under_modal_uv_state_dir(tmp_path: Path) -> None:
    pid_path, sock_path = daemon_paths(tmp_path)

    assert pid_path == tmp_path / ".modal-uv" / "daemon.pid"
    assert sock_path == tmp_path / ".modal-uv" / "daemon.sock"
    assert daemon_log_path(tmp_path) == tmp_path / ".modal-uv" / "daemon.log"


def test_ensure_repo_state_creates_state_dir_and_gitignore(tmp_path: Path) -> None:
    ensure_repo_state(tmp_path)

    assert (tmp_path / ".modal-uv").is_dir()
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == ".modal-uv/\n"


def test_ensure_repo_state_appends_gitignore_entry(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".venv/\n", encoding="utf-8")

    ensure_repo_state(tmp_path)

    assert gitignore.read_text(encoding="utf-8") == ".venv/\n.modal-uv/\n"


def test_ensure_repo_state_does_not_duplicate_gitignore_entry(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".modal-uv/\n", encoding="utf-8")

    ensure_repo_state(tmp_path)
    ensure_repo_state(tmp_path)

    assert gitignore.read_text(encoding="utf-8") == ".modal-uv/\n"


def test_full_yaml(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "my-app"
        work_dir: "/custom/work"

        volumes:
          - name: "my-volume"
            mount_path: "/custom/cache"

        runtime:
          gpu: "A100"
          cpu: 2.5
          memory: 4096
          scaledown_window_seconds: 120

        image:
          base_image: "python:3.11-slim"

        sync:
          ignore:
            - data/**
            - "*.ckpt"
        """,
    )
    config = load_config(path)
    assert config.app_name == "my-app"
    assert config.work_dir == Path("/custom/work")
    assert config.volumes[0].name == "my-volume"
    assert config.volumes[0].mount_path == Path("/custom/cache")
    assert config.runtime.gpu == "A100"
    assert config.runtime.cpu == 2.5
    assert config.runtime.memory == 4096
    assert config.runtime.scaledown_window_seconds == 120
    assert config.image.add_python_version is None
    assert config.image.base_image == "python:3.11-slim"
    assert config.sync.ignore == ("data/**", "*.ckpt")


def test_missing_yaml_fails(tmp_path: Path) -> None:
    path = tmp_path / "modal-uv.yaml"
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(path)


def test_invalid_gpu_fails(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          gpu: "INVALID"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    with pytest.raises(ConfigError, match="gpu"):
        load_config(path)


def test_missing_app_name_fails(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        runtime:
          gpu: "T4"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    with pytest.raises(ConfigError, match="app_name"):
        load_config(path)


def test_missing_volume_name_fails(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - mount_path: "/custom/cache"
        """,
    )
    with pytest.raises(ConfigError, match="each volume must have a name"):
        load_config(path)


def test_defaults_applied(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
        """,
    )
    config = load_config(path)
    assert config.runtime.gpu is None
    assert config.runtime.cpu is None
    assert config.runtime.memory is None
    assert config.work_dir == Path("/root/work")
    assert config.volumes[0].mount_path == Path("/root/.cache")
    assert config.image.add_python_version is None
    assert config.image.base_image == "python:3.12-slim"
    assert config.sync.ignore == ()
    assert config.volumes[0].commit_interval_seconds == 30
    assert config.runtime.scaledown_window_seconds == 300
    assert config.runtime.exec is None


def test_runtime_exec_is_configurable(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          exec: "bash"
        """,
    )
    config = load_config(path)
    assert config.runtime.exec == "bash"


def test_blank_runtime_exec_normalizes_to_none(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          exec: "  "
        """,
    )
    config = load_config(path)
    assert config.runtime.exec is None


def test_commit_interval_seconds_is_configurable(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            commit_interval_seconds: 60
        """,
    )
    config = load_config(path)
    assert config.volumes[0].commit_interval_seconds == 60


def test_commit_interval_seconds_must_be_positive(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            commit_interval_seconds: 0
        """,
    )

    with pytest.raises(ConfigError, match="commit_interval_seconds"):
        load_config(path)


def test_scaledown_window_seconds_must_be_positive(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          scaledown_window_seconds: 0
        """,
    )

    with pytest.raises(ConfigError, match="scaledown_window_seconds"):
        load_config(path)


def test_preload_is_not_part_of_public_config(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(path)

    assert not hasattr(config, "preload")


def test_sync_ignore_trims_blank_entries(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        sync:
          ignore:
            - " data/** "
            - ""
            - "*.ckpt"
        """,
    )
    config = load_config(path)

    assert config.sync.ignore == ("data/**", "*.ckpt")


def test_env_does_not_override_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          gpu: "T4"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    monkeypatch.setenv("MODAL_UV_GPU", "A100")
    config = load_config(path)
    assert config.runtime.gpu == "T4"


def test_a100_80gb_gpu_is_allowed(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          gpu: "a100-80gb"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(path)
    assert config.runtime.gpu == "A100-80GB"


def test_gpu_case_normalized(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          gpu: "a100"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(path)
    assert config.runtime.gpu == "A100"


def test_runtime_cpu_must_be_positive(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          cpu: 0
        """,
    )

    with pytest.raises(ConfigError, match="cpu"):
        load_config(path)


def test_runtime_memory_must_be_positive(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          memory: 0
        """,
    )

    with pytest.raises(ConfigError, match="memory"):
        load_config(path)


def test_python_version_field_raises_error(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        image:
          python_version: "3.12"
          base_image: "python:3.12-slim"
        """,
    )

    with pytest.raises(ConfigError, match="python_version"):
        load_config(path)


def test_known_python_image_does_not_require_add_python(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        image:
          base_image: "python:3.12-slim"
        """,
    )
    config = load_config(path)
    assert config.image.add_python_version is None


def test_known_python_image_rejects_add_python_version(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        image:
          base_image: "python:3.12-slim"
          add_python_version: "3.12"
        """,
    )

    with pytest.raises(ConfigError, match="add_python_version"):
        load_config(path)


def test_pytorch_image_treated_as_known_python(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        image:
          base_image: "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime"
        """,
    )
    config = load_config(path)
    assert config.image.add_python_version is None


def test_unknown_image_requires_add_python_version(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        image:
          base_image: "nvidia/cuda:12.4.0-devel-ubuntu22.04"
        """,
    )

    with pytest.raises(ConfigError, match="add_python_version"):
        load_config(path)


def test_unknown_image_with_inherit_add_python(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        image:
          base_image: "my-custom/image:latest"
          add_python_version: "inherit"
        """,
    )
    config = load_config(path)
    assert config.image.add_python_version == "inherit"


def test_unknown_image_with_semver_add_python(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        image:
          base_image: "nvidia/cuda:12.4.0-devel-ubuntu22.04"
          add_python_version: "3.12"
        """,
    )
    config = load_config(path)
    assert config.image.add_python_version == "3.12"
