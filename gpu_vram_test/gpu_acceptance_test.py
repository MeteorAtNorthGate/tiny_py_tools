from __future__ import annotations

import argparse
import gc
import math
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass

try:
    import torch
except Exception as exc:
    print("Cannot import PyTorch:", exc)
    print("Please run run_windows_test.ps1 first.")
    raise SystemExit(2)

GIB = 1024 ** 3
MIB = 1024 ** 2


def gib(n: int | float) -> float:
    return float(n) / GIB


def run_cmd(cmd: list[str]) -> str:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return (cp.stdout + cp.stderr).strip()
    except Exception as exc:
        return f"<Command execution failed: {exc}>"


def print_header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def device_summary() -> tuple[int, int]:
    print_header("1) Environment & Device Identification")
    print("Python:", sys.version.replace("\n", " "))
    print("System:", platform.platform())
    print("PyTorch:", torch.__version__)
    print("PyTorch CUDA runtime:", torch.version.cuda)
    print("cuDNN:", torch.backends.cudnn.version())
    print("CUDA available:", torch.cuda.is_available())

    if not torch.cuda.is_available():
        raise RuntimeError("torch.cuda.is_available() is False. CUDA/PyTorch is not working properly.")

    idx = torch.cuda.current_device()
    prop = torch.cuda.get_device_properties(idx)
    free_b, total_b = torch.cuda.mem_get_info(idx)

    print("GPU:", prop.name)
    print("Compute capability:", f"{prop.major}.{prop.minor}")
    print("VRAM (PyTorch total):", f"{gib(prop.total_memory):.2f} GiB")
    print("Current free VRAM:", f"{gib(free_b):.2f} GiB")
    print("Multiprocessors:", prop.multi_processor_count)
    print("\n[nvidia-smi -L]")
    print(run_cmd(["nvidia-smi", "-L"]))
    print("\n[nvidia-smi summary]")
    print(run_cmd([
        "nvidia-smi",
        "--query-gpu=name,uuid,pci.bus_id,driver_version,memory.total,vbios_version",
        "--format=csv,noheader"
    ]))
    return free_b, total_b


def basic_correctness() -> None:
    print_header("2) PyTorch CUDA / cuBLAS / cuDNN Basic Correctness")

    torch.manual_seed(20260727)
    torch.set_float32_matmul_precision("highest")
    torch.backends.cuda.matmul.allow_tf32 = False
    device = "cuda"

    # FP32 GEMM 与 CPU 参考值对比。
    n = 768
    a_cpu = torch.randn((n, n), dtype=torch.float32)
    b_cpu = torch.randn((n, n), dtype=torch.float32)
    ref = a_cpu @ b_cpu
    a = a_cpu.to(device)
    b = b_cpu.to(device)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    out = a @ b
    torch.cuda.synchronize()
    dt = time.perf_counter() - t0
    out_cpu = out.cpu()
    max_abs = (out_cpu - ref).abs().max().item()
    max_rel = ((out_cpu - ref).abs() / ref.abs().clamp_min(1e-5)).max().item()
    print(f"FP32 matmul: {dt:.3f}s, max_abs={max_abs:.6g}, max_rel={max_rel:.6g}")
    if not torch.allclose(out_cpu, ref, rtol=2e-4, atol=2e-3):
        raise RuntimeError("FP32 matrix multiplication result differs from CPU reference.")

    # FP16 / Tensor Core 路径。
    n2 = 2048
    a16 = torch.randn((n2, n2), device=device, dtype=torch.float16)
    b16 = torch.randn((n2, n2), device=device, dtype=torch.float16)
    out16 = a16 @ b16
    if not torch.isfinite(out16).all().item():
        raise RuntimeError("FP16 matrix multiplication produced NaN/Inf.")
    print("FP16 matmul: PASS")

    # cuDNN 卷积路径。
    conv = torch.nn.Conv2d(64, 128, kernel_size=3, padding=1, bias=False).to(
        device=device, dtype=torch.float16
    )
    x = torch.randn((8, 64, 128, 128), device=device, dtype=torch.float16)
    y = conv(x)
    torch.cuda.synchronize()
    if not torch.isfinite(y).all().item():
        raise RuntimeError("cuDNN convolution produced NaN/Inf.")
    print("cuDNN Conv2d: PASS")

    del a_cpu, b_cpu, ref, a, b, out, out_cpu, a16, b16, out16, conv, x, y
    gc.collect()
    torch.cuda.empty_cache()


@dataclass
class VramResult:
    allocated_bytes: int
    target_bytes: int
    chunks: int
    rounds: int


def vram_full_read_write(
    fraction: float = 0.80,
    reserve_gib: float = 1.75,
    chunk_mib: int = 256,
    rounds: int = 2,
) -> VramResult:
    print_header("3) VRAM Large-Capacity Block Write + Full Readback Verification")

    torch.cuda.empty_cache()
    gc.collect()
    free_b, total_b = torch.cuda.mem_get_info()
    reserve_b = int(reserve_gib * GIB)
    target_b = min(int(total_b * fraction), max(0, free_b - reserve_b))
    chunk_b = chunk_mib * MIB

    print(f"Total VRAM: {gib(total_b):.2f} GiB")
    print(f"Test target: {gib(target_b):.2f} GiB "
          f"({fraction * 100:.1f}% cap, {reserve_gib:.2f} GiB reserve)")
    print(f"Chunk size: {chunk_mib} MiB; rounds: {rounds}")
    if target_b < int(total_b * 0.80):
        print("Warning: Insufficient free VRAM. Please close browsers, games, screen recording, and other GPU programs before retrying.")

    chunks: list[torch.Tensor] = []
    allocated = 0
    try:
        while allocated < target_b:
            this_b = min(chunk_b, target_b - allocated)
            this_b = (this_b // 256) * 256
            if this_b <= 0:
                break
            chunks.append(torch.empty(this_b, device="cuda", dtype=torch.uint8))
            allocated += this_b
            if len(chunks) % 8 == 0 or allocated >= target_b:
                print(f"Allocated: {gib(allocated):.2f} GiB / {gib(target_b):.2f} GiB")
        torch.cuda.synchronize()
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        print(f"Allocation stopped at {gib(allocated):.2f} GiB (OOM), continuing with allocated region.")

    minimum_ok = min(int(total_b * 0.88), max(0, free_b - reserve_b - chunk_b))
    if allocated < minimum_ok:
        raise RuntimeError(
            f"Only successfully allocated {gib(allocated):.2f} GiB, "
            f"below the minimum expected {gib(minimum_ok):.2f} GiB for this environment."
        )

    # 先写完所有块，再统一读回；可以发现地址别名/虚假容量映射。
    for rnd in range(rounds):
        print(f"\nRound {rnd + 1}/{rounds}: writing all VRAM blocks")
        for i, tensor in enumerate(chunks):
            pattern = (i * 37 + rnd * 101 + 13) & 0xFF
            tensor.fill_(pattern)
            if (i + 1) % 16 == 0 or i + 1 == len(chunks):
                print(f"  Write {i + 1}/{len(chunks)}")
        torch.cuda.synchronize()

        print(f"Round {rnd + 1}/{rounds}: full block readback and verification")
        total_errors = 0
        for i, tensor in enumerate(chunks):
            pattern = (i * 37 + rnd * 101 + 13) & 0xFF
            errors = int(torch.count_nonzero(tensor != pattern).item())
            total_errors += errors
            if errors:
                print(f"  Block {i}: ERROR, byte errors={errors}")
            if (i + 1) % 16 == 0 or i + 1 == len(chunks):
                print(f"  Verify {i + 1}/{len(chunks)}, cumulative errors={total_errors}")
        torch.cuda.synchronize()
        if total_errors:
            raise RuntimeError(
                f"VRAM verification failed: round {rnd + 1} found {total_errors} byte errors."
            )
        print(f"Round {rnd + 1}: PASS")

    num_chunks = len(chunks)
    print(f"\nVRAM read/write verification PASS: covered {gib(allocated):.2f} GiB, {num_chunks} blocks total.")
    del chunks
    gc.collect()
    torch.cuda.empty_cache()
    return VramResult(allocated, target_b, num_chunks, rounds)


def stress_compute(seconds: int = 600, matrix_size: int = 8192) -> None:
    print_header("4) Tensor Core Sustained Compute Stress Test")
    print(f"Duration: {seconds}s; matrix: {matrix_size} x {matrix_size}; dtype=float16")
    torch.cuda.empty_cache()
    torch.manual_seed(5090)
    a = torch.randn((matrix_size, matrix_size), device="cuda", dtype=torch.float16)
    b = torch.randn((matrix_size, matrix_size), device="cuda", dtype=torch.float16)

    for _ in range(3):
        c = a @ b
    torch.cuda.synchronize()

    start = time.perf_counter()
    last_report = start
    iterations = 0
    checksum = 0.0

    while time.perf_counter() - start < seconds:
        c = a @ b
        if iterations % 5 == 0:
            c = torch.tanh(c * 0.001)
            checksum = float(c[0, 0].float().item())
            if not math.isfinite(checksum):
                raise RuntimeError("Stress test encountered NaN/Inf.")
        iterations += 1
        now = time.perf_counter()
        if now - last_report >= 30:
            elapsed = now - start
            print(f"Elapsed {elapsed:.0f}s, iterations {iterations}, checksum={checksum:.6g}")
            last_report = now

    torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    print(f"Compute stress PASS: {elapsed:.1f}s, iterations {iterations}, final checksum={checksum:.6g}")
    del a, b, c
    gc.collect()
    torch.cuda.empty_cache()


def main() -> int:
    parser = argparse.ArgumentParser(description="Windows NVIDIA CUDA / PyTorch / VRAM acceptance test")
    parser.add_argument("--stress-minutes", type=int, default=10)
    parser.add_argument("--vram-fraction", type=float, default=0.92)
    parser.add_argument("--vram-rounds", type=int, default=2)
    parser.add_argument("--chunk-mib", type=int, default=256)
    parser.add_argument("--reserve-gib", type=float, default=1.75)
    parser.add_argument("--matrix-size", type=int, default=8192)
    args = parser.parse_args()

    print("Starting CUDA / PyTorch / VRAM acceptance test. Do not run other GPU programs during the test.")
    started = time.time()
    try:
        device_summary()
        basic_correctness()
        vram_full_read_write(
            fraction=args.vram_fraction,
            reserve_gib=args.reserve_gib,
            chunk_mib=args.chunk_mib,
            rounds=args.vram_rounds,
        )
        stress_compute(seconds=args.stress_minutes * 60, matrix_size=args.matrix_size)
    except Exception as exc:
        print_header("TEST FAILED")
        print(type(exc).__name__ + ":", exc)
        traceback.print_exc()
        return 1

    elapsed = time.time() - started
    print_header("ALL TESTS PASSED")
    print(f"All tests passed, total time {elapsed / 60:.1f} minutes.")
    print("It is still recommended to run OCCT VRAM 60 minutes and OCCT 3D Adaptive 30 minutes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
