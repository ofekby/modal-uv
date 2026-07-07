# Modal-UV Python In-Process Execution Design

**Date:** 2026-06-06
**Status:** Approved
**Scope:** Add `modal-uv py` for warm in-process Python module/file execution after direct sync.

## Problem

`modal-uv run -- python -m lab` launches a new Python subprocess for each execution. Even with `uv run --no-sync`, repeated PyTorch jobs pay the Python, PyTorch import, CUDA library loading, and CUDA context initialization costs every time. Benchmark probes showed empty Python startup through `uv run --no-sync` takes about 50ms, while importing PyTorch and touching CUDA takes about 3 seconds.

## Goals

- Add a Python-specific command that reuses the warm Modal worker process.
- Support both Python module and file execution shapes:

```bash
modal-uv py -m lab
modal-uv py path/to/script.py --arg value
```

- Keep the existing direct sync protocol before execution.
- Resolve imports only after synced files are written.
- Preserve async execution IDs, `modal-uv logs <id>`, and `modal-uv abort <id>`.
- Let stdout/stderr flow directly to Modal logs.
- Keep imported modules cached across warm executions for speed.

## Non-Goals

- Do not replace `modal-uv run`; arbitrary commands still use subprocess execution.
- Do not implement automatic module reload for already-imported user modules.
- Do not support package dependency installation at runtime; dependencies remain image-build responsibility.
- Do not add a custom log transport; continue using Modal function-call logs.

## CLI

Add command:

```bash
modal-uv py [PYTHON_ARGS]...
```

Supported forms:

```bash
modal-uv py -m lab
modal-uv py path/to/script.py --arg value
```

`modal-uv py` follows the same launch UX as `modal-uv run`:

```text
Execution ID: fc-...
Tail logs: modal-uv logs fc-...
Abort: modal-uv abort fc-...
```

## Data Flow

1. Client builds the local file manifest with `modal_uv.sync` tracking.
2. Client calls `Worker.plan_sync.remote(manifest)`.
3. Worker deletes remote files that are no longer tracked and returns missing/stale paths.
4. Client uploads missing/stale file payloads.
5. Client calls `Worker.sync_and_run_python.spawn(manifest, payloads, python_args)`.
6. Worker writes payloads to `/tmp/work` and updates `.last-received-files-state.csv`.
7. Worker resolves imports after sync, executes module/file in-process, commits the Modal volume, and returns an exit code.

## Worker Execution Semantics

Before execution, the worker will:

- Ensure `/tmp/work` exists.
- Write uploaded files.
- Update `/tmp/work/.last-received-files-state.csv`.
- Set the current working directory to `/tmp/work` for the execution duration.
- Ensure `/tmp/work/src` and `/tmp/work` are present at the front of `sys.path`.
- Call `importlib.invalidate_caches()` after syncing files and before resolving imports.
- Patch `sys.argv` for the execution duration.

Module form:

```python
runpy.run_module(module_name, run_name="__main__", alter_sys=True)
```

File form:

```python
runpy.run_path(str(work_dir / script_path), run_name="__main__")
```

The worker will catch `SystemExit` and convert exit codes:

- `SystemExit(0)` or `SystemExit(None)` -> `0`
- `SystemExit(<int>)` -> that integer
- `SystemExit(<non-int>)` -> print the value to stderr and return `1`
- Other exceptions propagate to Modal and mark the function call failed.

## Import Cache Policy

The command intentionally keeps modules in `sys.modules` after execution. This allows warm executions to reuse expensive imports like `torch` and keep CUDA context warm.

After every sync, `importlib.invalidate_caches()` makes new files and packages discoverable. Already-imported modules are not reloaded automatically. If a user edits already-imported code and needs the new version, they should restart/replace the warm container. A future `--reload` option can be added if needed, but it is out of scope for this design.

## Error Handling

- Missing `-m` module name fails before spawning.
- Missing file path fails before spawning if it is not in the local repo.
- Unsafe file paths are rejected by existing path validation.
- Unsupported empty `modal-uv py` invocation fails with a clear CLI error.
- Runtime exceptions are printed by Modal and surfaced through function-call result failure.

## Testing Strategy

- Unit-test CLI parsing for `modal-uv py -m lab` and `modal-uv py script.py --arg`.
- Unit-test `py` uses the same manifest, `plan_sync`, payload build, spawn, and execution ID printing path as `run`.
- Unit-test Python argument parsing into module versus file execution requests.
- Unit-test in-process module execution patches `sys.argv`, cwd, and `sys.path`.
- Unit-test in-process file execution patches `sys.argv`, cwd, and `sys.path`.
- Unit-test `SystemExit` conversion.
- Integration-test warm repeated `modal-uv py -m lab` to verify later runs avoid the PyTorch import/CUDA startup cost.
