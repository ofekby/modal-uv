# CUDA Hello World

Use `modal-uv` to develop and run a CUDA hello-world kernel on a remote ephemeral T4 GPU while keeping the local edit loop unchanged.

## Run

```bash
modal-uv exec -- ./scripts/build-and-run.sh
```

Then follow the printed execution ID:

```bash
modal-uv logs fc-...
```

## What It Does

- Uses uv to install CUDA compiler/runtime Python wheels for the playbook.
- Prints `nvcc` and `nvidia-smi` diagnostics.
- Compiles `src/hello.cu`.
- Runs the binary on the remote GPU container.
- Writes the binary and run log to `/mnt/artifacts`.

## Modal Resources

- App: `modal-uv-cuda-hello`
- Volume: `modal-uv-cuda-hello-artifacts`
- Volume mount: `/mnt/artifacts`
- Runtime: T4 GPU, 4 CPUs

## Cleanup

```bash
modal-uv modal -- volume ls modal-uv-cuda-hello-artifacts
modal-uv modal -- app stop modal-uv-cuda-hello
```
