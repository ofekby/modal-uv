#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_DIR="/mnt/artifacts"
BUILD_DIR="/tmp/cuda-hello-build"
LOG_FILE="${ARTIFACT_DIR}/cuda-hello.log"

mkdir -p "${ARTIFACT_DIR}" "${BUILD_DIR}"

exec > >(tee "${LOG_FILE}") 2>&1

echo "[cuda] python: $(python3 --version 2>&1)"
export PATH="/usr/local/cuda/bin:${PATH}"
echo "[cuda] nvcc: $(which nvcc)"
nvcc --version

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi
else
  echo "[cuda] nvidia-smi not found"
fi

nvcc -o "${BUILD_DIR}/hello" src/hello.cu

"${BUILD_DIR}/hello"
cp "${BUILD_DIR}/hello" "${ARTIFACT_DIR}/cuda-hello"
ls -lh "${ARTIFACT_DIR}/cuda-hello" "${LOG_FILE}"
echo "[cuda] done"
