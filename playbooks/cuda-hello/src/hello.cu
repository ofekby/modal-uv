#include <cuda_runtime.h>

#include <cstdio>

__global__ void hello_kernel() {
  printf("hello from CUDA block %d thread %d\n", blockIdx.x, threadIdx.x);
}

int main() {
  int device_count = 0;
  cudaError_t status = cudaGetDeviceCount(&device_count);
  if (status != cudaSuccess) {
    std::fprintf(stderr, "cudaGetDeviceCount failed: %s\n", cudaGetErrorString(status));
    return 1;
  }

  std::printf("cuda devices: %d\n", device_count);
  hello_kernel<<<1, 4>>>();
  status = cudaDeviceSynchronize();
  if (status != cudaSuccess) {
    std::fprintf(stderr, "cudaDeviceSynchronize failed: %s\n", cudaGetErrorString(status));
    return 1;
  }

  std::printf("cuda hello completed\n");
  return 0;
}
