# MNIST CNN On T4

Use `modal-uv` to train a small CNN on MNIST with a remote T4 GPU.

## Run

```bash
modal-uv run -- python train_mnist.py --epochs 1
```

Then follow the printed execution ID:

```bash
modal-uv logs fc-...
```

For a slightly longer run:

```bash
modal-uv run -- python train_mnist.py --epochs 3
```

## What It Does

- Installs PyTorch and torchvision with `uv run`.
- Downloads or reuses MNIST under `/mnt/artifacts/data`.
- Trains a small CNN on the remote GPU.
- Writes `mnist-cnn.pt` and `mnist-metrics.json` to `/mnt/artifacts`.

## Modal Resources

- App: `modal-uv-mnist-cnn`
- Volume: `modal-uv-mnist-artifacts`
- Volume mount: `/mnt/artifacts`
- Runtime: T4 GPU, 4 CPUs

## Cleanup

```bash
modal-uv modal -- volume ls modal-uv-mnist-artifacts
modal-uv modal -- app stop modal-uv-mnist-cnn
```
