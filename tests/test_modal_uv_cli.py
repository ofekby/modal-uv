"""Tests for modal-uv CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from shlex import join as shell_join
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from modal_uv.cli import app
from modal_uv.deployment import DeploymentBroken, DeploymentMissing
from modal_uv.sync import FileState

runner = CliRunner()


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "modal-uv.yaml"
    path.write_text(dedent(content))
    return path


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout
    assert " py " not in result.stdout
    assert "logs" in result.stdout
    assert "abort" in result.stdout
    assert "exec" in result.stdout
    assert "│ shell" not in result.stdout
    assert "status" in result.stdout
    assert "daemon-stop" in result.stdout
    assert "daemon-status-cmd" in result.stdout


@patch("modal_uv.cli._ensure_deployment_with_notice")
@patch("modal_uv.cli._compute_expected_fingerprint", return_value="expected-fp")
@patch("modal_uv.cli.send_request")
@patch("modal_uv.cli.ensure_daemon")
def test_run_prints_spawned_execution_id(
    mock_ensure: MagicMock,
    mock_send: MagicMock,
    mock_fp: MagicMock,
    mock_deploy: MagicMock,
    tmp_path: Path,
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('hi')", encoding="utf-8")

    with (
        patch("modal_uv.cli.load_config") as mock_load,
        patch("modal_uv.cli.build_manifest") as mock_manifest,
    ):
        mock_config = MagicMock()
        mock_config.app_name = "test-app"
        mock_load.return_value = mock_config
        mock_manifest.return_value = [FileState(path="src/app.py", size=11, mtime_ns=100)]

        mock_conn = MagicMock()
        mock_ensure.return_value = mock_conn
        mock_send.side_effect = [
            {"status": "ok", "result": ["src/app.py"]},
            {"status": "ok", "execution_id": "fc-123"},
        ]

        result = runner.invoke(
            app, ["run", "--config", str(yaml_path), "--", "python", "-m", "lab"]
        )

    assert result.exit_code == 0
    assert "Execution ID: fc-123" in result.stdout
    assert "Tail logs: modal-uv logs fc-123" in result.stdout
    assert "Abort: modal-uv abort fc-123" in result.stdout
    assert mock_send.call_count == 2
    spawn_payload = mock_send.call_args_list[1].args[2]
    assert spawn_payload["mode"] == "run"


@patch("modal_uv.cli._ensure_deployment_with_notice")
@patch("modal_uv.cli._compute_expected_fingerprint", return_value="expected-fp")
@patch("modal_uv.cli.send_request")
@patch("modal_uv.cli.ensure_daemon")
@patch("modal_uv.cli.build_manifest")
def test_run_discovers_repo_root_from_nested_cwd(
    mock_manifest: MagicMock,
    mock_ensure: MagicMock,
    mock_send: MagicMock,
    mock_fp: MagicMock,
    mock_deploy: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_yaml(
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
    monkeypatch.chdir(nested)
    mock_manifest.return_value = [FileState(path="src/app.py", size=11, mtime_ns=100)]
    mock_ensure.return_value = MagicMock()
    mock_send.side_effect = [
        {"status": "ok", "result": []},
        {"status": "ok", "execution_id": "fc-nested"},
    ]

    result = runner.invoke(app, ["run", "--", "pytest"])

    assert result.exit_code == 0
    assert mock_manifest.call_args.args[0] == tmp_path
    assert mock_ensure.call_args.args == (config_path, tmp_path)
    assert (tmp_path / ".modal-uv").is_dir()
    assert ".modal-uv/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


@patch("modal_uv.cli._ensure_deployment_with_notice")
@patch("modal_uv.cli._compute_expected_fingerprint", return_value="expected-fp")
@patch("modal_uv.cli.send_request")
@patch("modal_uv.cli.ensure_daemon")
@patch("modal_uv.cli.build_manifest")
def test_run_passes_sync_ignore_to_manifest(
    mock_manifest: MagicMock,
    mock_ensure: MagicMock,
    mock_send: MagicMock,
    mock_fp: MagicMock,
    mock_deploy: MagicMock,
    tmp_path: Path,
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        sync:
          ignore:
            - "data/**"
        """,
    )
    mock_manifest.return_value = [FileState(path="src/app.py", size=11, mtime_ns=100)]
    mock_ensure.return_value = MagicMock()
    mock_send.side_effect = [
        {"status": "ok", "result": []},
        {"status": "ok", "execution_id": "fc-ignore"},
    ]

    result = runner.invoke(app, ["run", "--config", str(yaml_path), "--", "pytest"])

    assert result.exit_code == 0
    tracking_config = mock_manifest.call_args.args[1]
    assert tracking_config.ignore == ("data/**",)


@patch("modal_uv.cli._ensure_deployment_with_notice")
@patch("modal_uv.cli._compute_expected_fingerprint", return_value="expected-fp")
@patch("modal_uv.cli.send_request")
@patch("modal_uv.cli.ensure_daemon")
def test_run_fails_before_spawn_when_daemon_returns_error(
    mock_ensure: MagicMock,
    mock_send: MagicMock,
    mock_fp: MagicMock,
    mock_deploy: MagicMock,
    tmp_path: Path,
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )

    with (
        patch("modal_uv.cli.load_config") as mock_load,
        patch("modal_uv.cli.build_manifest") as mock_manifest,
    ):
        mock_config = MagicMock()
        mock_config.app_name = "test-app"
        mock_load.return_value = mock_config
        mock_manifest.return_value = [FileState(path="missing.py", size=1, mtime_ns=1)]

        mock_conn = MagicMock()
        mock_ensure.return_value = mock_conn
        mock_send.return_value = {"status": "error", "message": "file not found"}

        result = runner.invoke(app, ["run", "pytest", "--config", str(yaml_path)])

    assert result.exit_code == 1


@patch("modal_uv.cli._ensure_deployment_with_notice")
@patch("modal_uv.cli.stop_daemon")
@patch("modal_uv.cli._compute_expected_fingerprint", return_value="expected-fp")
@patch("modal_uv.cli.send_request")
@patch("modal_uv.cli.ensure_daemon")
@patch("modal_uv.cli.build_manifest")
def test_run_restarts_daemon_on_fingerprint_mismatch(
    mock_manifest: MagicMock,
    mock_ensure: MagicMock,
    mock_send: MagicMock,
    mock_fp: MagicMock,
    mock_stop: MagicMock,
    mock_deploy: MagicMock,
    tmp_path: Path,
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    mock_manifest.return_value = [FileState(path="src/app.py", size=11, mtime_ns=100)]
    mock_ensure.return_value = MagicMock()
    mock_send.side_effect = [
        {"status": "restart_needed"},
        {"status": "ok", "result": []},
        {"status": "ok", "execution_id": "fc-restart"},
    ]

    result = runner.invoke(app, ["run", "--config", str(yaml_path), "--", "pytest"])

    assert result.exit_code == 0
    assert "Execution ID: fc-restart" in result.stdout
    assert "restarting daemon" in result.stderr
    mock_stop.assert_called_once_with(tmp_path)
    assert mock_send.call_count == 3
    first_call = mock_send.call_args_list[0]
    assert first_call.args[2]["expected_fingerprint"] == "expected-fp"


@patch("modal_uv.cli._ensure_deployment_with_notice")
@patch("modal_uv.cli.stop_daemon")
@patch("modal_uv.cli._compute_expected_fingerprint", return_value="expected-fp")
@patch("modal_uv.cli.send_request")
@patch("modal_uv.cli.ensure_daemon")
@patch("modal_uv.cli.build_manifest")
def test_run_fails_when_restart_still_returns_restart_needed(
    mock_manifest: MagicMock,
    mock_ensure: MagicMock,
    mock_send: MagicMock,
    mock_fp: MagicMock,
    mock_stop: MagicMock,
    mock_deploy: MagicMock,
    tmp_path: Path,
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    mock_manifest.return_value = [FileState(path="src/app.py", size=11, mtime_ns=100)]
    mock_ensure.return_value = MagicMock()
    mock_send.side_effect = [
        {"status": "restart_needed"},
        {"status": "restart_needed"},
    ]

    result = runner.invoke(app, ["run", "--config", str(yaml_path), "--", "pytest"])

    assert result.exit_code == 1
    mock_stop.assert_called_once_with(tmp_path)
    result = runner.invoke(app, ["run", "pytest", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 1


@patch("modal_uv.cli._wait_for_deployment_ready")
@patch("modal_uv.cli.deploy_generated_artifact")
@patch("modal_uv.cli.query_deployed_fingerprint", side_effect=DeploymentMissing("no app"))
def test_deploy_notice_printed_when_app_missing(
    mock_query: MagicMock, mock_deploy: MagicMock, mock_wait: MagicMock, tmp_path: Path
) -> None:
    from modal_uv.cli import _ensure_deployment_with_notice
    from modal_uv.config import load_config

    _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(tmp_path / "modal-uv.yaml")

    _ensure_deployment_with_notice(config, tmp_path)

    mock_deploy.assert_called_once()
    assert (tmp_path / ".modal-uv" / "deployment.py").exists()


@patch("modal_uv.cli._wait_for_deployment_ready")
@patch("modal_uv.cli.deploy_generated_artifact")
@patch("modal_uv.cli.query_deployed_fingerprint", side_effect=DeploymentBroken("crash"))
def test_deploy_notice_printed_when_app_broken(
    mock_query: MagicMock, mock_deploy: MagicMock, mock_wait: MagicMock, tmp_path: Path
) -> None:
    from modal_uv.cli import _ensure_deployment_with_notice
    from modal_uv.config import load_config

    _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(tmp_path / "modal-uv.yaml")

    _ensure_deployment_with_notice(config, tmp_path)

    mock_deploy.assert_called_once()


@patch("modal_uv.cli._kill_app_containers")
@patch("modal_uv.cli._wait_for_deployment_ready")
@patch("modal_uv.cli.deploy_generated_artifact")
@patch("modal_uv.cli.query_deployed_fingerprint", return_value="stale-fp")
def test_redeploy_notice_printed_when_fingerprint_mismatches(
    mock_query: MagicMock,
    mock_deploy: MagicMock,
    mock_wait: MagicMock,
    mock_kill: MagicMock,
    tmp_path: Path,
) -> None:
    from modal_uv.cli import _ensure_deployment_with_notice
    from modal_uv.config import load_config

    _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(tmp_path / "modal-uv.yaml")

    _ensure_deployment_with_notice(config, tmp_path)

    mock_deploy.assert_called_once()
    mock_kill.assert_called_once_with("test-app")


@patch("modal_uv.cli._wait_for_deployment_ready")
@patch("modal_uv.cli.deploy_generated_artifact")
@patch("modal_uv.cli.query_deployed_fingerprint", side_effect=DeploymentMissing("no app"))
def test_kill_containers_not_called_on_first_deploy(
    mock_query: MagicMock,
    mock_deploy: MagicMock,
    mock_wait: MagicMock,
    tmp_path: Path,
) -> None:
    from modal_uv.cli import _ensure_deployment_with_notice
    from modal_uv.config import load_config

    _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(tmp_path / "modal-uv.yaml")

    with patch("modal_uv.cli._kill_app_containers") as mock_kill:
        _ensure_deployment_with_notice(config, tmp_path)

    mock_kill.assert_not_called()


@patch("modal_uv.cli.subprocess")
def test_kill_app_containers_accepts_lowercase_modal_json_keys(
    mock_subprocess: MagicMock,
) -> None:
    from modal_uv.cli import _kill_app_containers

    mock_subprocess.run.side_effect = [
        MagicMock(
            returncode=0,
            stdout=json.dumps(
                [{"description": "test-app", "state": "deployed", "app_id": "app-123"}]
            ),
        ),
        MagicMock(
            returncode=0,
            stdout=json.dumps([{"container_id": "ct-123", "app_id": "app-123"}]),
        ),
        MagicMock(returncode=0, stdout="", stderr=""),
    ]

    _kill_app_containers("test-app")

    stop_call = mock_subprocess.run.call_args_list[2]
    assert stop_call.args[0][-1] == "ct-123"


@patch("modal_uv.cli.deploy_generated_artifact")
@patch("modal_uv.cli.query_deployed_fingerprint")
def test_no_deploy_when_fingerprint_matches(
    mock_query: MagicMock, mock_deploy: MagicMock, tmp_path: Path
) -> None:
    from modal_uv.cli import _compute_expected_fingerprint, _ensure_deployment_with_notice
    from modal_uv.config import load_config

    _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(tmp_path / "modal-uv.yaml")
    expected_fp = _compute_expected_fingerprint(config, tmp_path)
    mock_query.return_value = expected_fp

    _ensure_deployment_with_notice(config, tmp_path)

    mock_deploy.assert_not_called()


@patch("modal_uv.cli._wait_for_deployment_ready")
@patch("modal_uv.cli.deploy_generated_artifact")
@patch("modal_uv.cli.query_deployed_fingerprint", side_effect=DeploymentMissing("no app"))
def test_verbose_flag_passed_to_deploy(
    mock_query: MagicMock, mock_deploy: MagicMock, mock_wait: MagicMock, tmp_path: Path
) -> None:
    from modal_uv.cli import _ensure_deployment_with_notice
    from modal_uv.config import load_config

    _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    config = load_config(tmp_path / "modal-uv.yaml")

    _ensure_deployment_with_notice(config, tmp_path, verbose=True)

    mock_deploy.assert_called_once()
    assert mock_deploy.call_args.kwargs["verbose"] is True


@patch("modal_uv.cli._ensure_deployment_with_notice")
@patch("modal_uv.cli._compute_expected_fingerprint", return_value="expected-fp")
@patch("modal_uv.cli.send_request")
@patch("modal_uv.cli.ensure_daemon")
@patch("modal_uv.cli.build_manifest")
def test_exec_prints_spawned_execution_id_and_sends_exec_mode(
    mock_manifest: MagicMock,
    mock_ensure: MagicMock,
    mock_send: MagicMock,
    mock_fp: MagicMock,
    mock_deploy: MagicMock,
    tmp_path: Path,
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )

    mock_manifest.return_value = [FileState(path="src/app.py", size=11, mtime_ns=100)]
    mock_ensure.return_value = MagicMock()
    mock_send.side_effect = [
        {"status": "ok", "result": []},
        {"status": "ok", "execution_id": "fc-exec"},
    ]

    result = runner.invoke(app, ["exec", "--config", str(yaml_path), "--", "nvidia-smi"])

    assert result.exit_code == 0
    assert "Execution ID: fc-exec" in result.stdout
    assert "Tail logs: modal-uv logs fc-exec" in result.stdout
    assert "Abort: modal-uv abort fc-exec" in result.stdout
    spawn_payload = mock_send.call_args_list[1].args[2]
    assert spawn_payload["mode"] == "exec"
    assert spawn_payload["args"] == ["nvidia-smi"]


@patch("modal_uv.cli._ensure_deployment_with_notice")
@patch("modal_uv.cli._compute_expected_fingerprint", return_value="expected-fp")
@patch("modal_uv.cli.send_request")
@patch("modal_uv.cli.ensure_daemon")
@patch("modal_uv.cli.build_manifest")
def test_exec_shell_joins_multiple_tokens(
    mock_manifest: MagicMock,
    mock_ensure: MagicMock,
    mock_send: MagicMock,
    mock_fp: MagicMock,
    mock_deploy: MagicMock,
    tmp_path: Path,
) -> None:
    yaml_path = _write_yaml(tmp_path, 'app_name: "test-app"\n')
    mock_manifest.return_value = []
    mock_ensure.return_value = MagicMock()
    mock_send.side_effect = [
        {"status": "ok", "result": []},
        {"status": "ok", "execution_id": "fc-join"},
    ]

    result = runner.invoke(
        app, ["exec", "--config", str(yaml_path), "--", "ls", "-la", "&&", "pwd"]
    )

    assert result.exit_code == 0
    spawn_payload = mock_send.call_args_list[1].args[2]
    assert spawn_payload["args"] == [shell_join(["ls", "-la", "&&", "pwd"])]


def test_exec_requires_command(tmp_path: Path) -> None:
    yaml_path = _write_yaml(tmp_path, 'app_name: "test-app"\n')

    result = runner.invoke(app, ["exec", "--config", str(yaml_path)])

    assert result.exit_code != 0
    assert "exec command required" in result.stderr


@patch("modal_uv.cli.subprocess")
def test_status_shows_app(mock_subprocess: MagicMock, tmp_path: Path) -> None:
    yaml_path = _write_yaml(
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

    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = json.dumps(
        [{"Description": "test-app", "State": "running", "App ID": "app-123"}]
    )

    result = runner.invoke(app, ["status", "--config", str(yaml_path)])

    assert result.exit_code == 0
    assert "test-app" in result.stdout


@patch("modal_uv.cli.subprocess")
def test_status_accepts_lowercase_modal_json_keys(
    mock_subprocess: MagicMock, tmp_path: Path
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )

    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = json.dumps(
        [{"description": "test-app", "state": "deployed", "app_id": "app-123"}]
    )

    result = runner.invoke(app, ["status", "--config", str(yaml_path)])

    assert result.exit_code == 0
    assert "test-app" in result.stdout
    assert "deployed" in result.stdout
    assert "app-123" in result.stdout


@patch("modal_uv.cli.subprocess")
def test_status_no_app_found(mock_subprocess: MagicMock, tmp_path: Path) -> None:
    yaml_path = _write_yaml(
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

    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = json.dumps(
        [{"Description": "other-app", "State": "running", "App ID": "app-456"}]
    )

    result = runner.invoke(app, ["status", "--config", str(yaml_path)])

    assert result.exit_code == 1
    assert "No app found" in result.stdout


def test_status_config_error_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["status", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 1


@patch("modal.FunctionCall")
@patch("modal_uv.cli.subprocess")
def test_logs_tails_function_call_logs(
    mock_subprocess: MagicMock, mock_fc_class: MagicMock, tmp_path: Path
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    mock_process = MagicMock()
    mock_process.poll.return_value = None
    mock_subprocess.Popen.return_value = mock_process
    mock_fc_class.from_id.return_value.get.return_value = 0

    result = runner.invoke(app, ["logs", "fc-123", "--config", str(yaml_path)])

    assert result.exit_code == 0
    mock_subprocess.Popen.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "modal",
            "app",
            "logs",
            "test-app",
            "--function-call",
            "fc-123",
            "--follow",
        ]
    )
    mock_fc_class.from_id.assert_called_once_with("fc-123")
    mock_fc_class.from_id.return_value.get.assert_called_once_with()
    mock_process.terminate.assert_called_once_with()
    mock_process.wait.assert_called_once_with(timeout=5)


@patch("modal.FunctionCall")
def test_abort_cancels_function_call(mock_fc_class: MagicMock, tmp_path: Path) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )
    function_call = MagicMock()
    mock_fc_class.from_id.return_value = function_call

    result = runner.invoke(app, ["abort", "fc-123", "--config", str(yaml_path)])

    assert result.exit_code == 0
    mock_fc_class.from_id.assert_called_once_with("fc-123")
    function_call.cancel.assert_called_once_with()


@patch("modal_uv.cli.stop_daemon")
def test_daemon_stop_reports_stopped(mock_stop: MagicMock, tmp_path: Path) -> None:
    mock_stop.return_value = True
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )

    result = runner.invoke(app, ["daemon-stop", "--config", str(yaml_path)])

    assert result.exit_code == 0
    assert "stopped" in result.stdout.lower()


@patch("modal_uv.cli.daemon_status")
def test_daemon_status_shows_info(mock_status: MagicMock, tmp_path: Path) -> None:
    mock_status.return_value = {"pid": 12345, "socket": "/tmp/test.sock"}
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )

    result = runner.invoke(app, ["daemon-status-cmd", "--config", str(yaml_path)])

    assert result.exit_code == 0
    assert "12345" in result.stdout


def test_help_lists_onboard_update_install_skill() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "onboard" in result.stdout
    assert "update" in result.stdout
    assert "install-skill" in result.stdout


@patch("modal_uv.cli._open_url")
@patch("modal_uv.cli.install_to_all_present")
def test_onboard_runs_modal_oauth_then_installs_skills(
    mock_install: MagicMock, mock_open_url: MagicMock
) -> None:
    mock_install.return_value = [Path("/fake/skills/SKILL.md")]

    oauth_lines = [
        "Was not able to launch web browser\n",
        "Please go to this URL manually and complete the flow:\n",
        "\n",
        "https://modal.com/token-flow/tf-test123\n",
    ]

    with patch("modal_uv.cli.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = iter(oauth_lines)
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0
    mock_popen.assert_called_once()
    cmd = mock_popen.call_args.args[0]
    assert cmd[:4] == [sys.executable, "-m", "modal", "token"]
    mock_open_url.assert_called_once_with("https://modal.com/token-flow/tf-test123")
    mock_install.assert_called_once()


@patch("modal_uv.cli._open_url")
@patch("modal_uv.cli.install_to_all_present")
def test_onboard_fails_when_modal_oauth_fails(
    mock_install: MagicMock, mock_open_url: MagicMock
) -> None:
    with patch("modal_uv.cli.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["some error\n"])
        mock_proc.returncode = 1
        mock_proc.wait.return_value = 1
        mock_popen.return_value = mock_proc

        result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 1
    mock_install.assert_not_called()


def test_open_url_returns_true_when_wslview_available() -> None:
    from modal_uv.cli import _open_url

    with (
        patch("shutil.which", side_effect=lambda name: name == "wslview"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        assert _open_url("https://example.com") is True
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0] == ["wslview", "https://example.com"]


def test_open_url_falls_back_to_cmd_exe_when_no_wslview() -> None:
    from modal_uv.cli import _open_url

    with (
        patch("shutil.which", side_effect=lambda name: name == "cmd.exe"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        assert _open_url("https://example.com") is True
        mock_run.assert_called_once()
        assert mock_run.call_args.args[0] == ["cmd.exe", "/c", "start", "", "https://example.com"]


def test_open_url_falls_back_to_webbrowser() -> None:
    from modal_uv.cli import _open_url

    with (
        patch("shutil.which", return_value=None),
        patch("webbrowser.open") as mock_webbrowser,
    ):
        mock_webbrowser.return_value = True
        assert _open_url("https://example.com") is True
        mock_webbrowser.assert_called_once_with("https://example.com")


def test_open_url_returns_false_when_nothing_works() -> None:
    from modal_uv.cli import _open_url

    with (
        patch("shutil.which", return_value=None),
        patch("webbrowser.open") as mock_webbrowser,
    ):
        mock_webbrowser.return_value = False
        assert _open_url("https://example.com") is False


@patch("modal_uv.cli.subprocess")
@patch("modal_uv.cli.install_to_all_present")
def test_update_runs_pip_install_then_installs_skills(
    mock_install: MagicMock, mock_subprocess: MagicMock
) -> None:
    mock_subprocess.run.return_value.returncode = 0
    mock_install.return_value = [Path("/fake/skills/SKILL.md")]

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert mock_subprocess.run.call_args.args[0] == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "modal-uv",
    ]
    mock_install.assert_called_once()


@patch("modal_uv.cli.subprocess")
@patch("modal_uv.cli.install_to_all_present")
def test_update_fails_when_pip_install_fails(
    mock_install: MagicMock, mock_subprocess: MagicMock
) -> None:
    mock_subprocess.run.return_value.returncode = 1

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 1
    mock_install.assert_not_called()


@patch("modal_uv.cli.install_to_agent")
def test_install_skill_with_known_agent_name(mock_install: MagicMock) -> None:
    mock_install.return_value = Path("/fake/SKILL.md")

    result = runner.invoke(app, ["install-skill", "opencode"])

    assert result.exit_code == 0
    mock_install.assert_called_once_with("opencode")


@patch("modal_uv.cli.install_to_dir")
def test_install_skill_with_explicit_path(mock_install: MagicMock, tmp_path: Path) -> None:
    mock_install.return_value = tmp_path / "SKILL.md"

    result = runner.invoke(app, ["install-skill", str(tmp_path)])

    assert result.exit_code == 0
    mock_install.assert_called_once_with(tmp_path)


def test_init_creates_default_config_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    config_file = tmp_path / "modal-uv.yaml"
    assert config_file.exists()
    content = config_file.read_text(encoding="utf-8")
    assert "app_name:" in content
    assert tmp_path.name in content
    assert "runtime:" in content
    assert 'gpu: "T4"' in content
    assert "cpu:" not in content
    assert "memory:" not in content
    assert "scaledown_window_seconds: 300" in content
    assert "exec:" not in content
    assert (tmp_path / ".modal-uv").is_dir()
    assert ".modal-uv/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_init_preserves_existing_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "modal-uv.yaml"
    config_file.write_text(
        'app_name: "existing-app"\n'
        'volumes:\n  - name: "existing-vol"\n    mount_path: "/mnt/volume"\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    content = config_file.read_text(encoding="utf-8")
    assert "existing-app" in content
    assert "existing-vol" in content
    assert (tmp_path / ".modal-uv").is_dir()
    assert ".modal-uv/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_help_lists_init() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "modal" in result.stdout


@patch("modal_uv.cli.subprocess")
def test_modal_passthrough_delegates_to_modal_module(mock_subprocess: MagicMock) -> None:
    mock_subprocess.run.return_value.returncode = 0

    result = runner.invoke(app, ["modal", "--", "volume", "ls"])

    assert result.exit_code == 0
    mock_subprocess.run.assert_called_once_with([sys.executable, "-m", "modal", "volume", "ls"])


@patch("modal_uv.cli.subprocess")
def test_modal_passthrough_propagates_nonzero_exit(mock_subprocess: MagicMock) -> None:
    mock_subprocess.run.return_value.returncode = 42

    result = runner.invoke(app, ["modal", "--", "app", "list"])

    assert result.exit_code == 42


def test_modal_passthrough_requires_args() -> None:
    result = runner.invoke(app, ["modal"])

    assert result.exit_code != 0


def test_help_lists_doctor_whoami() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "whoami" in result.stdout


def test_doctor_without_config_reports_no_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "modal-uv.yaml" in result.stdout
    assert "not found" in result.stdout.lower()


@patch("modal_uv.cli.subprocess")
def test_doctor_with_config_checks_auth_volume_app(
    mock_subprocess: MagicMock, tmp_path: Path
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )

    def fake_run(cmd, **kwargs):
        if "profile" in cmd and "current" in cmd:
            return MagicMock(returncode=0, stdout="authenticated as user@example.com\n")
        if "volume" in cmd and "ls" in cmd:
            return MagicMock(returncode=0, stdout="test-volume\n")
        if "app" in cmd and "list" in cmd:
            return MagicMock(
                returncode=0,
                stdout=json.dumps(
                    [{"Description": "test-app", "State": "running", "App ID": "app-123"}]
                ),
            )
        return MagicMock(returncode=1, stdout="", stderr="unknown")

    mock_subprocess.run.side_effect = fake_run

    with (
        patch("modal_uv.cli.load_config") as mock_load,
        patch("modal_uv.cli.ensure_repo_state"),
    ):
        mock_config = MagicMock()
        mock_config.app_name = "test-app"
        mock_vol = MagicMock()
        mock_vol.name = "test-volume"
        mock_config.volumes = [mock_vol]
        mock_load.return_value = mock_config

        result = runner.invoke(app, ["doctor", "--config", str(yaml_path)])

    assert result.exit_code == 0
    assert "Auth" in result.stdout
    assert "Volume" in result.stdout
    assert "App" in result.stdout
    assert "test-app" in result.stdout
    commands = [call.args[0] for call in mock_subprocess.run.call_args_list]
    assert any(command[-2:] == ["profile", "current"] for command in commands)
    assert any(command[-3:] == ["volume", "ls", "test-volume"] for command in commands)


@patch("modal_uv.cli.subprocess")
def test_doctor_accepts_lowercase_modal_app_json_keys(
    mock_subprocess: MagicMock, tmp_path: Path
) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )

    def fake_run(cmd, **kwargs):
        if "profile" in cmd and "current" in cmd:
            return MagicMock(returncode=0, stdout="authenticated as user@example.com\n")
        if "volume" in cmd and "ls" in cmd:
            return MagicMock(returncode=0, stdout="test-volume\n")
        if "app" in cmd and "list" in cmd:
            return MagicMock(
                returncode=0,
                stdout=json.dumps(
                    [{"description": "test-app", "state": "deployed", "app_id": "app-123"}]
                ),
            )
        return MagicMock(returncode=1, stdout="", stderr="unknown")

    mock_subprocess.run.side_effect = fake_run

    with (
        patch("modal_uv.cli.load_config") as mock_load,
        patch("modal_uv.cli.ensure_repo_state"),
    ):
        mock_config = MagicMock()
        mock_config.app_name = "test-app"
        mock_vol = MagicMock()
        mock_vol.name = "test-volume"
        mock_config.volumes = [mock_vol]
        mock_load.return_value = mock_config

        result = runner.invoke(app, ["doctor", "--config", str(yaml_path)])

    assert result.exit_code == 0
    assert "App (test-app): deployed (deployed)" in result.stdout


@patch("modal_uv.cli.subprocess")
def test_doctor_reports_auth_failure(mock_subprocess: MagicMock, tmp_path: Path) -> None:
    yaml_path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
        """,
    )

    def fake_run(cmd, **kwargs):
        if "profile" in cmd and "current" in cmd:
            return MagicMock(returncode=1, stdout="", stderr="not authenticated\n")
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_subprocess.run.side_effect = fake_run

    with (
        patch("modal_uv.cli.load_config") as mock_load,
        patch("modal_uv.cli.ensure_repo_state"),
    ):
        mock_config = MagicMock()
        mock_config.app_name = "test-app"
        mock_vol = MagicMock()
        mock_vol.name = "test-volume"
        mock_config.volumes = [mock_vol]
        mock_load.return_value = mock_config

        result = runner.invoke(app, ["doctor", "--config", str(yaml_path)])

    assert result.exit_code == 0
    assert "not authenticated" in result.stdout.lower() or "fail" in result.stdout.lower()


@patch("modal_uv.cli.subprocess")
def test_whoami_shows_authenticated_user(mock_subprocess: MagicMock) -> None:
    mock_subprocess.run.return_value = MagicMock(
        returncode=0, stdout="authenticated as user@example.com\n"
    )

    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 0
    assert "user@example.com" in result.stdout
    mock_subprocess.run.assert_called_once()
    assert mock_subprocess.run.call_args.args[0][:4] == [
        sys.executable,
        "-m",
        "modal",
        "profile",
    ]


@patch("modal_uv.cli.subprocess")
def test_whoami_reports_not_authenticated(mock_subprocess: MagicMock) -> None:
    mock_subprocess.run.return_value = MagicMock(
        returncode=1, stdout="", stderr="not authenticated\n"
    )

    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 0
    assert "not authenticated" in result.stdout.lower()
