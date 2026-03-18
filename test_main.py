import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import main


def test_ping_server():
    expected_output = "Pong! The DevOps MCP Server is fully operational."
    assert main.ping_server() == expected_output


def test_get_jenkins_logs_requires_configuration(monkeypatch):
    monkeypatch.setattr(main, "JENKINS_URL", "")
    monkeypatch.setattr(main, "JENKINS_USER", "")
    monkeypatch.setattr(main, "JENKINS_TOKEN", "")

    result = main.get_jenkins_logs("demo-job", "lastBuild")
    assert "Jenkins is not configured" in result


def test_get_jenkins_logs_success_with_default_build(monkeypatch):
    monkeypatch.setattr(main, "JENKINS_URL", "http://jenkins.local:8080")
    monkeypatch.setattr(main, "JENKINS_USER", "demo")
    monkeypatch.setattr(main, "JENKINS_TOKEN", "token")

    response = Mock()
    response.text = "build output"
    response.raise_for_status = Mock()
    fake_session = SimpleNamespace(get=Mock(return_value=response))
    monkeypatch.setattr(main, "_HTTP_SESSION", fake_session)

    result = main.get_jenkins_logs("my-job", "")

    assert result == "build output"
    called_url = fake_session.get.call_args.args[0]
    assert called_url.endswith("/job/my-job/lastBuild/consoleText")


def test_get_terraform_plan_rejects_path_outside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    monkeypatch.setattr(main, "WORKSPACE_ROOT", workspace.resolve())

    result = main.get_terraform_plan(str(outside_dir.resolve()))
    assert "outside of WORKSPACE_ROOT" in result


def test_get_terraform_plan_success(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    tf_dir = workspace / "terraform"
    tf_dir.mkdir(parents=True)
    monkeypatch.setattr(main, "WORKSPACE_ROOT", workspace.resolve())

    completed = subprocess.CompletedProcess(
        args=["terraform", "plan"],
        returncode=0,
        stdout="plan ok",
        stderr="",
    )
    run_mock = Mock(return_value=completed)
    monkeypatch.setattr(main.subprocess, "run", run_mock)

    result = main.get_terraform_plan("terraform")

    assert result == "plan ok"
    assert run_mock.call_args.kwargs["cwd"] == str(tf_dir.resolve())


def test_read_code_context_success(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target_file = workspace / "config.txt"
    target_file.write_text("safe-content", encoding="utf-8")
    monkeypatch.setattr(main, "WORKSPACE_ROOT", workspace.resolve())

    result = main.read_code_context("config.txt")
    assert result == "safe-content"


def test_read_code_context_blocks_symlink(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    real_file = workspace / "real.txt"
    real_file.write_text("value", encoding="utf-8")
    symlink_file = workspace / "link.txt"
    symlink_file.symlink_to(real_file)
    monkeypatch.setattr(main, "WORKSPACE_ROOT", workspace.resolve())

    result = main.read_code_context("link.txt")
    assert "Symbolic links are not allowed" in result


def test_read_code_context_truncates_large_file(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target_file = workspace / "large.txt"
    target_file.write_text("A" * 50, encoding="utf-8")
    monkeypatch.setattr(main, "WORKSPACE_ROOT", workspace.resolve())
    monkeypatch.setattr(main, "MAX_FILE_LENGTH", 10)

    result = main.read_code_context("large.txt")
    assert result.startswith("A" * 10)
    assert "[FILE TRUNCATED]" in result
