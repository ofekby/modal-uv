#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_DIR="/mnt/artifacts"
WORK_ROOT="/tmp/rocksdb-build"
SOURCE_DIR="${WORK_ROOT}/rocksdb"

mkdir -p "${ARTIFACT_DIR}" "${WORK_ROOT}"

echo "[rocksdb] python: $(python --version 2>&1)"
echo "[rocksdb] cpu count: $(nproc)"
echo "[rocksdb] installing build dependencies"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  ca-certificates \
  git \
  build-essential \
  make \
  libbz2-dev \
  libgflags-dev \
  liblz4-dev \
  libsnappy-dev \
  libzstd-dev \
  zlib1g-dev

rm -rf "${SOURCE_DIR}"
git clone --depth 1 https://github.com/facebook/rocksdb.git "${SOURCE_DIR}"

cd "${SOURCE_DIR}"
ROCKSDB_COMMIT="$(git rev-parse HEAD)"
echo "[rocksdb] commit: ${ROCKSDB_COMMIT}"
echo "[rocksdb] running: PORTABLE=1 make -j\"$(nproc)\" static_lib"
PORTABLE=1 make -j"$(nproc)" static_lib

cp librocksdb.a "${ARTIFACT_DIR}/librocksdb.a"
{
  echo "rocksdb_commit=${ROCKSDB_COMMIT}"
  echo "portable=1"
  echo "make_jobs=$(nproc)"
  echo "artifact=${ARTIFACT_DIR}/librocksdb.a"
  echo "built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "${ARTIFACT_DIR}/rocksdb-build-manifest.txt"

ls -lh "${ARTIFACT_DIR}/librocksdb.a" "${ARTIFACT_DIR}/rocksdb-build-manifest.txt"
echo "[rocksdb] done"
