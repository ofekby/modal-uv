# Modal-UV Direct Sync Design

**Date:** 2026-06-06
**Status:** Approved
**Scope:** Use direct Modal client calls and async execution IDs for `modal-uv`.

## Problem

The previous `modal-uv` flow depended on an external archive sync before running `uv`. This added a separate prerequisite and still did not provide the desired execution workflow: launch now, return an execution ID, tail logs separately, and abort separately.

## Goals

- Use direct file sync for `modal-uv` execution.
- Use `modal_uv.sync` file tracking for local file selection.
- Use two Modal client calls for each execution: one planning call with file metadata and one spawned execution call with missing/stale file contents.
- Keep remote file state only in the warm container filesystem.
- Return a Modal function call ID immediately from `modal-uv run`.
- Add `modal-uv logs <execution_id>` and `modal-uv abort <execution_id>` commands.
- Print subprocess stdout/stderr directly to Modal logs.
- Allow only one execution at a time.

## Non-Goals

- No bucket mount, tar.gz archive, or external sync prerequisite for `modal-uv`.
- No client-side `.last-received-files-state.csv`.
- No persistent remote sync state across cold starts.
- No content hashes for changed-file detection.
- No custom server-side job registry; the Modal function call ID is the execution ID.

## Architecture

```text
modal-uv run -- <uv args>
    │
    ├─ scan local files with modal_uv.sync tracking behavior
    │
    ├─ Worker.plan_sync.remote(manifest)
    │      ├─ load /tmp/work/.last-received-files-state.csv if present
    │      ├─ delete remote files that are no longer tracked locally
    │      ├─ compute missing/stale files by path, size, mtime_ns
    │      └─ return missing/stale paths
    │
    ├─ read missing/stale local file bytes
    │
    └─ Worker.sync_and_run.spawn(manifest, files, uv_args)
           ├─ write uploaded files to /tmp/work
           ├─ update /tmp/work/.last-received-files-state.csv
           ├─ run uv run --link-mode copy <uv args>
           ├─ print stdout/stderr directly to Modal logs
           ├─ commit Modal volume for direct writes to /mnt/volume
           └─ return subprocess exit code
```

## File Tracking

The client uses `modal_uv.sync` tracking:

- Built-in ignores for `.git/`, `.venv/`, `node_modules/`, Python caches, and tool caches.
- `.s3-sync-ignore` for repo-local gitignore-style exclusions.
- `iter_sync_files(repo_root, TrackingConfig())` for the final tracked file list.

## Sync State

Remote state file:

```text
/tmp/work/.last-received-files-state.csv
```

Rows contain:

```text
path,size,mtime_ns
```

The file is stored only in the warm container filesystem. It is not written to the Modal volume. If Modal replaces the container, the file is absent and the next `modal-uv run` uploads all tracked files.

## Sync Protocol

### First Call: `plan_sync.remote(manifest)`

Input manifest rows contain:

```text
path,size,mtime_ns
```

The worker will:

1. Ensure `/tmp/work` exists.
2. Load `/tmp/work/.last-received-files-state.csv` if present.
3. Delete files in `/tmp/work` that are present in the stored remote state but absent from the incoming manifest.
4. Remove empty parent directories created by deleted files when safe.
5. Return paths that are missing remotely or whose `size` or `mtime_ns` differs.

Deletion is intentionally performed in `plan_sync.remote()` before the spawned run begins, so the second call only needs to upload stale files and execute.

### Second Call: `sync_and_run.spawn(manifest, files, args)`

Uploaded file records contain:

```text
path,size,mtime_ns,content_bytes
```

The worker will:

1. Write each uploaded file under `/tmp/work`, creating parent directories.
2. Set file mtimes to match the uploaded `mtime_ns` when possible.
3. Update `/tmp/work/.last-received-files-state.csv` to match the full current manifest passed from the client after all uploaded files are written.
4. Run `uv run --link-mode copy <args>` with `cwd=/tmp/work`.
5. Let stdout and stderr flow directly to Modal logs.
6. Commit the Modal volume after execution to persist direct writes to `/mnt/volume`.
7. Return the subprocess exit code.

## Execution IDs

`modal-uv run` will call `Worker.sync_and_run.spawn(...)` and print the returned `FunctionCall.object_id`.

Example output:

```text
Execution ID: fc-...
Tail logs: modal-uv logs fc-...
Abort: modal-uv abort fc-...
```

The command returns immediately after printing the ID. It does not wait for execution completion.

## Logs Command

`modal-uv logs <execution_id>` tails Modal logs filtered to the spawned function call.

Implementation should use the Modal CLI because public Python log APIs are not stable:

```bash
modal app logs <app_name> --function-call <execution_id> --follow
```

The command should propagate the Modal CLI exit code.

## Abort Command

`modal-uv abort <execution_id>` will reconstruct the function call handle and cancel it:

```python
function_call = modal.FunctionCall.from_id(execution_id)
function_call.cancel(terminate_containers=True)
```

Using `terminate_containers=True` favors quick abort behavior. Because sync state is warm-container-only, terminating the container is acceptable; the next run will upload all tracked files again if needed.

## Concurrency

The worker keeps `@modal.concurrent(max_inputs=1)`. This allows only one worker input to execute at a time in the warm container. Additional executions should not overlap with an active run.

The first planning call and second spawned call are sequential from the client perspective. If another client tries to run concurrently, Modal's single-input concurrency setting serializes worker inputs.

## Configuration Changes

`modal-uv.yaml` no longer needs the `s3` section for `modal-uv` execution. Existing `volume`, `gpu`, `work_dir`, and `image` settings remain relevant.

The deployed Modal app no longer needs:

- bucket mounts
- external storage secrets for source sync
- archive path helpers
- tar extraction logic

## Error Handling

- Missing local files during upload preparation: fail before spawning and report the path.
- Invalid remote paths: reject absolute paths and paths containing `..`.
- `plan_sync.remote()` failure: fail `modal-uv run` without spawning execution.
- `sync_and_run.spawn()` startup failure: report the Modal exception and exit non-zero.
- `logs` command failure: propagate `modal app logs` stderr and exit code.
- `abort` command failure: report Modal cancellation errors and exit non-zero.

## Testing Strategy

- Unit-test manifest creation from tracked files using `modal_uv.sync` ignore/include behavior.
- Unit-test CSV load/save round trips for `path,size,mtime_ns`.
- Unit-test `plan_sync` comparison behavior: all missing, unchanged, stale by size, stale by mtime, and deleted extras.
- Unit-test path safety validation for upload and delete paths.
- Unit-test CLI `run` with mocked Modal calls: `plan_sync.remote()` result, uploaded payload construction, and `sync_and_run.spawn()` ID printing.
- Unit-test CLI `logs` command construction.
- Unit-test CLI `abort` with mocked `modal.FunctionCall.from_id()`.
- Integration-test deployed `modal-uv run -- python -m lab`, then `modal-uv logs <id>` and `modal-uv abort <id>` on a long-running command.

## Migration

1. Remove external archive sync code from `deploy.py` and `modal_uv` config usage.
2. Delete the old sync package and tests.
3. Update `modal-uv.yaml` to remove external sync settings.
4. Redeploy the Modal app.
5. Run `modal-uv run -- python -m lab` directly.
