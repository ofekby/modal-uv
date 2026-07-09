# modal-uv Playbooks Design

## Goal

Add three runnable playbooks that demonstrate practical `modal-uv` workflows as self-contained mini-projects:

1. Accelerating a large CPU-bound native build with RocksDB static library compilation.
2. Compiling and running a CUDA hello-world kernel on remote GPU infrastructure.
3. Training a small MNIST CNN on a remote T4 GPU.

Each playbook should be runnable directly with `modal-uv`, use its own Modal app and volume names, and serve as copy-pasteable documentation for users and coding agents.

## Repository Layout

Create one directory per playbook:

```text
playbooks/
  rocksdb-build/
  cuda-hello/
  mnist-cnn/
```

Each directory is a fully self-contained mini-project with:

- `modal-uv.yaml` for app, runtime, image, sync, and volume configuration.
- `pyproject.toml` with a minimal project definition.
- `uv.lock` generated for that project.
- `README.md` with short runnable commands and expected outputs.
- `scripts/` or source files needed by the playbook.
- `.gitignore` for generated state such as `.modal-uv/`, `.venv/`, local artifacts, and caches.

## Playbook 1: RocksDB Static Library Build

Purpose: show how a developer can offload a CPU-heavy native compilation task to Modal without turning the project into a Modal app.

Directory: `playbooks/rocksdb-build/`

Configuration:

- Modal app name: `modal-uv-rocksdb-build`.
- Volume name: `modal-uv-rocksdb-artifacts`, mounted at `/mnt/artifacts`.
- CPU-only runtime with `runtime.cpu: 64`.
- Memory large enough for parallel C++ compilation.
- Python-compatible Debian-based image. The playbook script installs native build tools at runtime because `modal-uv.yaml` currently selects the base image but does not define image build steps.

Command flow:

```bash
modal-uv exec -- ./scripts/build-rocksdb.sh
```

The script will:

- Install or verify build dependencies as needed.
- Clone RocksDB with `git clone --depth 1 https://github.com/facebook/rocksdb.git`.
- Run `PORTABLE=1 make -j"$(nproc)" static_lib`.
- Copy `librocksdb.a` and a short build manifest to `/mnt/artifacts`.

If the full `static_lib` build is too slow or fails due to upstream dependency changes, we will first collect the failure evidence, then choose a smaller native compilation target or a smaller project as a replacement.

## Playbook 2: CUDA Hello World

Purpose: show how a developer can compile and run CUDA code when local CUDA tooling or a local GPU is unavailable.

Directory: `playbooks/cuda-hello/`

Configuration:

- Modal app name: `modal-uv-cuda-hello`.
- Volume name: `modal-uv-cuda-hello-artifacts`, mounted at `/mnt/artifacts`.
- GPU runtime with `runtime.gpu: "T4"`.
- CUDA devel base image that includes Python and `nvcc`, such as a PyTorch CUDA devel image. This avoids relying on unsupported `Image.from_registry(..., add_python=...)` options in `modal-uv.yaml`.
- Modest CPU and memory.

Command flow:

```bash
modal-uv exec -- ./scripts/build-and-run.sh
```

The project will include a small `hello.cu` kernel and a script that:

- Prints CUDA compiler and GPU diagnostics.
- Compiles `hello.cu` with `nvcc`.
- Runs the resulting binary.
- Copies the binary and a run log to `/mnt/artifacts`.

## Playbook 3: MNIST CNN Training

Purpose: show how a developer can train a small neural network on a remote T4 GPU from an ordinary Python project.

Directory: `playbooks/mnist-cnn/`

Configuration:

- Modal app name: `modal-uv-mnist-cnn`.
- Volume name: `modal-uv-mnist-artifacts`, mounted at `/mnt/artifacts`.
- GPU runtime with `runtime.gpu: "T4"`.
- Python 3.12 image compatible with PyTorch and torchvision.
- CPU and memory enough for data loading and training.

Command flow:

```bash
modal-uv run -- python train_mnist.py --epochs 1
```

The training script will:

- Rely on `uv run` to install project dependencies from the playbook `pyproject.toml` and `uv.lock`.
- Download or reuse MNIST under the mounted volume.
- Train a small CNN for 1 epoch by default and allow `--epochs 3`.
- Print GPU availability, device name, loss, and accuracy.
- Save a checkpoint and metrics file to `/mnt/artifacts`.

## Validation

Local validation:

- Ensure each playbook has parseable `modal-uv.yaml`.
- Generate each playbook `uv.lock`.
- Run any lightweight local checks that do not require Modal.

Live validation:

- Run each playbook through `modal-uv` from its own directory.
- Tail logs with `modal-uv logs <execution-id>`.
- Confirm expected artifacts are written into each playbook volume.

Expected live signals:

- RocksDB: `librocksdb.a` exists in `/mnt/artifacts` and the build manifest records CPU count and commit information.
- CUDA hello: `nvcc` succeeds, the binary runs, and the log shows a CUDA-capable device.
- MNIST CNN: training runs on CUDA, prints progress, and writes a checkpoint plus metrics.

## Non-Goals

- Do not add new `modal-uv` product features for these playbooks.
- Do not create a shared playbook runner; each playbook should show normal repo-local `modal-uv` use.
- Do not optimize the examples into production-grade training or build pipelines.
- Do not make the RocksDB fallback decision before trying the full `static_lib` build live.
