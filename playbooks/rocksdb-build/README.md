# RocksDB Static Library Build

Use `modal-uv` to offload a CPU-heavy native compilation job to a 64 CPU Modal container.

## Run

```bash
modal-uv exec -- ./scripts/build-rocksdb.sh
```

Then follow the printed execution ID:

```bash
modal-uv logs fc-...
```

## What It Does

- Clones RocksDB with `git clone --depth 1 https://github.com/facebook/rocksdb.git`.
- Runs `PORTABLE=1 make -j"$(nproc)" static_lib`.
- Writes `librocksdb.a` and `rocksdb-build-manifest.txt` to `/mnt/artifacts`.

## Modal Resources

- App: `modal-uv-rocksdb-build`
- Volume: `modal-uv-rocksdb-artifacts`
- Volume mount: `/mnt/artifacts`
- Runtime: CPU-only, 64 CPUs

## Cleanup

Use Modal's CLI through `modal-uv` if you want to inspect or clean up resources:

```bash
modal-uv modal -- volume ls modal-uv-rocksdb-artifacts
modal-uv modal -- app stop modal-uv-rocksdb-build
```
