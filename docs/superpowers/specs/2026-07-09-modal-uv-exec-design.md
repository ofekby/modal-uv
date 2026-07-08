# Modal-UV Exec Command Design

**Date:** 2026-07-09

**Scope:** Remove the redundant `modal-uv shell` command and add an asynchronous `modal-uv exec -- ...` command for raw shell execution in the synced Modal container.

## Goals

- Remove `modal-uv shell` because `modal-uv modal -- shell ...` already provides the Modal CLI shell escape hatch.
- Add `modal-uv exec -- <command...>` for shell-style remote commands.
- Preserve the same asynchronous lifecycle as `modal-uv run`: print an execution ID immediately, then inspect with `modal-uv logs <id>` or cancel with `modal-uv abort <id>`.
- Keep `modal-uv run -- ...` as the uv-managed project execution path.
- Resolve the default shell inside the Modal container, not on the local machine.
- Support an optional manually configured `runtime.exec` shell without adding it to the generated default config template.

## Non-Goals

- Do not add an interactive replacement for `modal-uv shell`.
- Do not make `exec` run through `uv run`.
- Do not add automatic installation of shells such as `bash` or `zsh`; users who configure a shell must provide it in the image.
- Do not change the behavior of `modal-uv logs`, `modal-uv abort`, or `modal-uv modal -- ...`.

## CLI Behavior

The CLI command surface changes as follows:

- `modal-uv run -- <args...>` remains uv-managed execution.
- `modal-uv exec -- <command...>` performs shell execution in the synced Modal work directory.
- `modal-uv shell` is removed from CLI help and command registration.
- `modal-uv modal -- shell ...` remains available for users who want Modal's native interactive shell.

`exec` accepts the command after `--`. The local CLI joins those arguments with `shlex.join` before sending the request to the daemon. The remote shell receives that string with `-c`.

Examples:

```bash
modal-uv exec -- nvidia-smi
modal-uv exec -- ls -la '&&' pwd
modal-uv exec -- 'ls -la && nvidia-smi'
```

All three examples should spawn remote work and print:

```text
Execution ID: fc-...
Tail logs: modal-uv logs fc-...
Abort: modal-uv abort fc-...
```

## Configuration

`runtime.exec` is optional:

```yaml
runtime:
  exec: bash
```

If omitted, `runtime.exec` is `None` in the loaded config. It should not appear in `modal-uv init` output or the example generated template by default.

Remote shell resolution for `exec` mode is:

```python
shell = runtime_exec or os.environ.get("SHELL") or "/bin/sh"
```

This resolution must happen inside the Modal worker so the container's environment decides `$SHELL`. Local `$SHELL` must not influence the default unless the user explicitly passes it through config.

`runtime.exec` affects execution behavior and is embedded in the deployed Worker configuration. It is part of deployment parameters and the deployment fingerprint.

## Daemon And Worker Protocol

The existing sync and spawn path remains the shared transport for both modes.

The daemon spawn request adds an execution mode:

- `run`: current behavior.
- `exec`: shell execution behavior.

The Worker can keep a single `sync_and_run` method, but it branches on the mode after syncing files and writing the remote state CSV.

For `run` mode, the Worker runs the existing command:

```python
subprocess.run(uv_run_command(args), cwd=work_dir, env=uv_run_env(Path(work_dir)))
```

For `exec` mode, the Worker resolves the shell and runs it directly without uv:

```python
subprocess.run([shell, "-c", command], cwd=work_dir, env=uv_run_env(Path(work_dir)))
```

`uv_run_env` remains useful in both modes because it adds the synced `src/` directory to `PYTHONPATH`.

## Data Flow

For `modal-uv exec -- nvidia-smi`:

1. CLI discovers the repo root and loads `modal-uv.yaml`.
2. CLI ensures the deployment is current, matching current `run` behavior.
3. CLI builds the sync manifest.
4. CLI sends the same plan-sync request used by `run`.
5. CLI sends a spawn request with mode `exec` and command `nvidia-smi`.
6. Daemon calls the existing Modal Worker method asynchronously.
7. Worker syncs files and state.
8. Worker resolves `runtime.exec`, remote `$SHELL`, or `/bin/sh`.
9. Worker runs the shell directly with `-c`.
10. CLI prints the function call ID plus `logs` and `abort` hints immediately.

## Error Handling

- Missing or invalid config fails before spawning remote work, as with `run`.
- Missing configured shell fails inside the remote execution and is visible through `modal-uv logs <id>`.
- Empty `exec` command should fail locally with a clear CLI error rather than spawning a no-op remote call.
- Unknown execution mode should fail in the Worker with a clear error.
- `KeyboardInterrupt` handling for local command startup should match `run`; spawned remote executions remain cancellable with `modal-uv abort`.

## Testing

Unit tests should cover:

- `modal-uv shell` is absent from help.
- `modal-uv exec` is present in help.
- `exec` prints the same execution ID, logs hint, and abort hint as `run`.
- `exec` sends mode `exec` to the daemon spawn path.
- `run` sends mode `run` or preserves equivalent default behavior.
- `runtime.exec` parses as optional and defaults to `None`.
- `runtime.exec` can be configured manually.
- The default generated YAML omits `runtime.exec`.
- Deployment parameters/fingerprint include `runtime.exec`.
- Worker `run` mode uses `uv run --link-mode copy`.
- Worker `exec` mode uses the resolved shell directly and does not invoke `uv run`.
- Worker `exec` mode falls back from configured shell to remote `$SHELL` to `/bin/sh`.

## Open Decisions

No open product decisions remain for this scope.
