# Modal-UV Playbooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three self-contained runnable playbooks that demonstrate CPU compilation acceleration, remote CUDA compilation, and remote T4 GPU training with `modal-uv`.

**Architecture:** Each playbook is an ordinary mini-project under `playbooks/<name>/` with its own `modal-uv.yaml`, `pyproject.toml`, `uv.lock`, README, scripts, app name, and volume name. The playbooks do not share a runner and do not require changes to `modal-uv` product code unless live validation exposes a blocking product bug.

**Tech Stack:** Python 3.12, uv, modal-uv, Modal volumes, shell scripts, Make, CUDA/nvcc, PyTorch, torchvision, pytest/Ruff/ty for repository verification.

**Spec Reference:** `docs/superpowers/specs/2026-07-10-modal-uv-playbooks-design.md`

**Plan Constraint:** Per user request, this plan intentionally avoids explicit implementation code. It uses goals, definitions of done, constraints, exact files, validation commands, and pseudocode-style behavior descriptions only.

---

## Global Constraints

- Keep this scoped to playbook files and documentation.
- Do not add a shared playbook runner.
- Do not add new `modal-uv` product features unless live validation proves a product bug blocks the approved playbooks.
- Do not choose arbitrary CUDA base images; custom images must start the Modal Worker successfully and avoid the serialized function Python-version mismatch seen with incompatible images.
- Prefer Python 3.12-compatible base images because the repository and Modal deployment currently run from Python 3.12.
- Use independent Modal app names and independent Modal volume names for each playbook.
- Keep each README short, copy-pasteable, and honest about expected runtime and artifacts.
- Run the full RocksDB `static_lib` build first; only choose an alternative after observing evidence that it is too slow or unsuitable.
- Do not commit implementation changes until the playbooks have at least passed local validation.
- Capture live execution IDs and important log findings while validating.

## File Structure

- Create `playbooks/rocksdb-build/.gitignore`: ignore `.modal-uv/`, `.venv/`, local build outputs, and caches.
- Create `playbooks/rocksdb-build/README.md`: explain purpose, command, expected artifacts, logs, and cleanup.
- Create `playbooks/rocksdb-build/modal-uv.yaml`: configure `modal-uv-rocksdb-build`, `modal-uv-rocksdb-artifacts`, CPU-only runtime, memory, image, sync ignores.
- Create `playbooks/rocksdb-build/pyproject.toml`: minimal uv project metadata.
- Create `playbooks/rocksdb-build/uv.lock`: generated lockfile.
- Create `playbooks/rocksdb-build/scripts/build-rocksdb.sh`: install/verify build dependencies, clone RocksDB, build `static_lib`, persist artifacts.
- Create `playbooks/cuda-hello/.gitignore`: ignore `.modal-uv/`, `.venv/`, local build outputs, and caches.
- Create `playbooks/cuda-hello/README.md`: explain purpose, command, expected output, artifacts, and cleanup.
- Create `playbooks/cuda-hello/modal-uv.yaml`: configure `modal-uv-cuda-hello`, `modal-uv-cuda-hello-artifacts`, T4 GPU runtime, CUDA-capable image, sync ignores.
- Create `playbooks/cuda-hello/pyproject.toml`: minimal uv project metadata.
- Create `playbooks/cuda-hello/uv.lock`: generated lockfile.
- Create `playbooks/cuda-hello/src/hello.cu`: CUDA hello-world kernel source.
- Create `playbooks/cuda-hello/scripts/build-and-run.sh`: print diagnostics, compile with `nvcc`, run binary, persist outputs.
- Create `playbooks/mnist-cnn/.gitignore`: ignore `.modal-uv/`, `.venv/`, local data, checkpoints, and caches.
- Create `playbooks/mnist-cnn/README.md`: explain purpose, command, expected metrics, artifacts, and cleanup.
- Create `playbooks/mnist-cnn/modal-uv.yaml`: configure `modal-uv-mnist-cnn`, `modal-uv-mnist-artifacts`, T4 GPU runtime, Python/PyTorch-compatible image, sync ignores.
- Create `playbooks/mnist-cnn/pyproject.toml`: minimal uv project metadata with PyTorch and torchvision dependencies.
- Create `playbooks/mnist-cnn/uv.lock`: generated lockfile.
- Create `playbooks/mnist-cnn/train_mnist.py`: train a small CNN for 1-3 epochs and persist checkpoint/metrics.
- Optionally modify `README.md`: add a short pointer to the new `playbooks/` directory if implementation time permits.

---

### Task 1: Create The Playbook Directory Skeletons

**Files:**
- Create: `playbooks/rocksdb-build/.gitignore`
- Create: `playbooks/rocksdb-build/README.md`
- Create: `playbooks/rocksdb-build/modal-uv.yaml`
- Create: `playbooks/rocksdb-build/pyproject.toml`
- Create: `playbooks/rocksdb-build/scripts/build-rocksdb.sh`
- Create: `playbooks/cuda-hello/.gitignore`
- Create: `playbooks/cuda-hello/README.md`
- Create: `playbooks/cuda-hello/modal-uv.yaml`
- Create: `playbooks/cuda-hello/pyproject.toml`
- Create: `playbooks/cuda-hello/src/hello.cu`
- Create: `playbooks/cuda-hello/scripts/build-and-run.sh`
- Create: `playbooks/mnist-cnn/.gitignore`
- Create: `playbooks/mnist-cnn/README.md`
- Create: `playbooks/mnist-cnn/modal-uv.yaml`
- Create: `playbooks/mnist-cnn/pyproject.toml`
- Create: `playbooks/mnist-cnn/train_mnist.py`

**Goal:** Establish all three playbooks as independent uv projects with the expected file layout.

**Behavior Pseudocode:**
- RocksDB script flow: prepare dependencies, create a temporary source directory, clone RocksDB shallowly, build with all available CPUs, copy `librocksdb.a` plus a manifest to `/mnt/artifacts`.
- CUDA script flow: report `python`, `nvcc`, and GPU diagnostics, compile the CUDA source, run the binary, copy the binary plus run log to `/mnt/artifacts`.
- MNIST script flow: parse epoch count, select CUDA device, download/reuse MNIST under `/mnt/artifacts`, train for the requested epochs, save metrics and checkpoint to `/mnt/artifacts`.

**Steps:**
- [ ] Create the three playbook directories and subdirectories.
- [ ] Add `.gitignore` files that prevent generated Modal state, virtual environments, data, checkpoints, and local artifacts from being committed.
- [ ] Add minimal `pyproject.toml` files for all three playbooks.
- [ ] Add `modal-uv.yaml` files with distinct app names and volume names.
- [ ] Add placeholder-free READMEs with command, expected output, artifact location, and cleanup guidance.
- [ ] Add the RocksDB shell script and make it executable.
- [ ] Add the CUDA source and shell script, and make the script executable.
- [ ] Add the MNIST training script.

**Definition of Done:**
- All planned paths exist.
- Each playbook is understandable without reading another playbook.
- Each playbook uses its own app name and volume name.
- No generated `.modal-uv/`, `.venv/`, dataset, checkpoint, binary, or build-output files are tracked.

---

### Task 2: Lock Dependencies And Run Local Static Checks

**Files:**
- Create: `playbooks/rocksdb-build/uv.lock`
- Create: `playbooks/cuda-hello/uv.lock`
- Create: `playbooks/mnist-cnn/uv.lock`
- Modify: playbook files from Task 1 if local checks find issues.

**Goal:** Ensure each playbook is a complete uv project and catches obvious syntax/config mistakes before Modal runs.

**Steps:**
- [ ] Run `uv lock` in `playbooks/rocksdb-build`.
- [ ] Run `uv lock` in `playbooks/cuda-hello`.
- [ ] Run `uv lock` in `playbooks/mnist-cnn`.
- [ ] Run shell syntax checks for the RocksDB and CUDA scripts.
- [ ] Run a local Python syntax check for `playbooks/mnist-cnn/train_mnist.py`.
- [ ] Run `uv run ruff format --check .` at the repository root.
- [ ] Run `uv run ruff check .` at the repository root.
- [ ] Run `uv run ty check` at the repository root.
- [ ] Run `uv run pytest` at the repository root.

**Definition of Done:**
- All three lockfiles are present.
- Shell scripts pass syntax checks.
- The MNIST script parses under Python.
- Repository verification passes or any failures are clearly unrelated and documented.

---

### Task 3: Preflight Modal Image Compatibility

**Files:**
- Modify: `playbooks/cuda-hello/modal-uv.yaml` if the first CUDA image choice fails Modal startup.
- Modify: `playbooks/mnist-cnn/modal-uv.yaml` if the first PyTorch image choice fails Modal startup.
- Modify: `playbooks/*/README.md` if image selection affects expected output or runtime.

**Goal:** Verify selected base images can start `modal-uv` Workers before running expensive jobs.

**Steps:**
- [ ] From `playbooks/rocksdb-build`, run a minimal `modal-uv exec` smoke command that prints Python version and CPU count.
- [ ] From `playbooks/cuda-hello`, run a minimal `modal-uv exec` smoke command that prints Python version, CUDA compiler availability, and GPU diagnostics.
- [ ] From `playbooks/mnist-cnn`, run a minimal `modal-uv run` smoke command that imports Python and prints the runtime Python version.
- [ ] If any playbook fails before user code starts, inspect logs with `modal-uv logs <execution-id>` and adjust only the image/config needed for that playbook.
- [ ] If no compatible CUDA/Python base image is available through current `modal-uv.yaml` capabilities, stop and report the blocker before changing product code.

**Definition of Done:**
- All selected images can start a Modal Worker.
- CUDA playbook image exposes `nvcc` and a CUDA-capable device when run with T4.
- MNIST playbook image can execute `uv run` without Modal deserialization or Python-version startup failures.
- Any image changes are reflected in the relevant README.

---

### Task 4: Live Validate RocksDB Static Library Build

**Files:**
- Modify: `playbooks/rocksdb-build/scripts/build-rocksdb.sh` if live validation exposes missing dependencies or artifact path issues.
- Modify: `playbooks/rocksdb-build/modal-uv.yaml` if CPU, memory, timeout, or image settings need adjustment.
- Modify: `playbooks/rocksdb-build/README.md` with observed runtime and artifact notes.

**Goal:** Prove the CPU-compilation playbook can build RocksDB `static_lib` remotely and persist the result to a volume.

**Steps:**
- [ ] From `playbooks/rocksdb-build`, run `modal-uv exec -- ./scripts/build-rocksdb.sh`.
- [ ] Record the execution ID printed by `modal-uv`.
- [ ] Follow logs with `modal-uv logs <execution-id>`.
- [ ] Confirm the logs show the remote CPU count, RocksDB clone, `PORTABLE=1`, and `make -j` using available CPUs.
- [ ] Confirm `librocksdb.a` and the manifest are copied to `/mnt/artifacts`.
- [ ] If the full build is too slow or fails due to RocksDB-specific upstream behavior, collect the error and ask whether to switch to a smaller native build target or replacement project.

**Definition of Done:**
- Full RocksDB `static_lib` has been attempted live.
- Success case: `librocksdb.a` is in the Modal volume and README records the verified command.
- Failure case: logs identify the concrete blocker and no fallback is chosen without user approval.

---

### Task 5: Live Validate CUDA Hello World

**Files:**
- Modify: `playbooks/cuda-hello/src/hello.cu` if live validation exposes a CUDA portability issue.
- Modify: `playbooks/cuda-hello/scripts/build-and-run.sh` if diagnostics, compiler flags, or artifact paths need adjustment.
- Modify: `playbooks/cuda-hello/modal-uv.yaml` if image, GPU, CPU, or memory settings need adjustment.
- Modify: `playbooks/cuda-hello/README.md` with observed output and artifact notes.

**Goal:** Prove the CUDA playbook can compile and run a CUDA kernel on a remote T4 GPU.

**Steps:**
- [ ] From `playbooks/cuda-hello`, run `modal-uv exec -- ./scripts/build-and-run.sh`.
- [ ] Record the execution ID printed by `modal-uv`.
- [ ] Follow logs with `modal-uv logs <execution-id>`.
- [ ] Confirm logs show `nvcc` availability.
- [ ] Confirm logs show a CUDA-capable T4 device or equivalent Modal-provided GPU diagnostics.
- [ ] Confirm the compiled binary runs and prints a successful hello-world result.
- [ ] Confirm the binary and run log are copied to `/mnt/artifacts`.

**Definition of Done:**
- CUDA source compiles remotely with `nvcc`.
- Binary runs successfully on the remote GPU container.
- Artifacts persist to the playbook volume.
- README records the verified command and expected signal.

---

### Task 6: Live Validate MNIST CNN Training

**Files:**
- Modify: `playbooks/mnist-cnn/train_mnist.py` if live validation exposes dependency, data path, device, checkpoint, or metrics issues.
- Modify: `playbooks/mnist-cnn/pyproject.toml` and `playbooks/mnist-cnn/uv.lock` if dependency versions need adjustment.
- Modify: `playbooks/mnist-cnn/modal-uv.yaml` if image, GPU, CPU, or memory settings need adjustment.
- Modify: `playbooks/mnist-cnn/README.md` with observed output and artifact notes.

**Goal:** Prove the MNIST playbook trains a small CNN on a remote T4 GPU and persists training artifacts.

**Steps:**
- [ ] From `playbooks/mnist-cnn`, run `modal-uv run -- python train_mnist.py --epochs 1`.
- [ ] Record the execution ID printed by `modal-uv`.
- [ ] Follow logs with `modal-uv logs <execution-id>`.
- [ ] Confirm logs show CUDA availability and the selected GPU device name.
- [ ] Confirm logs show at least one completed training epoch.
- [ ] Confirm logs show validation loss or accuracy.
- [ ] Confirm checkpoint and metrics files are written to `/mnt/artifacts`.
- [ ] Optionally run `modal-uv run -- python train_mnist.py --epochs 3` if the 1-epoch validation is fast and stable.

**Definition of Done:**
- One-epoch training succeeds on a remote GPU.
- Metrics and checkpoint persist to the Modal volume.
- README records the verified command and expected signal.
- Three-epoch command is documented as optional unless it has been live-validated.

---

### Task 7: Documentation, Final Verification, And Commit Readiness

**Files:**
- Modify: `README.md` only if adding a concise pointer to `playbooks/` is useful.
- Modify: `playbooks/*/README.md` based on live validation facts.
- Review: all created playbook files.

**Goal:** Make the playbooks ready to commit with accurate docs and evidence-backed validation notes.

**Steps:**
- [ ] Review every README and remove unverified claims.
- [ ] Ensure every README includes app name, volume name, command, logs command, artifact path, and cleanup hint.
- [ ] Ensure live execution IDs and observed outcomes are available for the final user summary.
- [ ] Run `uv run ruff format --check .`.
- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run ty check`.
- [ ] Run `uv run pytest`.
- [ ] Run `git status --short` and confirm only intended files are changed.
- [ ] Prepare a commit message, but do not commit unless the user explicitly asks.

**Definition of Done:**
- All three playbooks are self-contained.
- All local verification passes.
- Each live playbook run either succeeds or has a user-approved fallback decision.
- Final summary can name exact commands run, execution IDs, and artifact outcomes.

---

## Self-Review Notes

- Spec coverage: The plan covers all three playbooks, self-contained mini-project files, independent app/volume names, local validation, live validation, RocksDB full-build-first policy, CUDA compile/run, and MNIST T4 training.
- Placeholder scan: The plan contains no unresolved placeholder markers and no explicit implementation code snippets.
- Scope check: The three playbooks are independent but intentionally grouped because the user requested them as one repository playbook set and each is independently testable.
- Risk noted: CUDA and PyTorch base images must be verified against Modal Worker startup constraints before relying on them for live demos.
