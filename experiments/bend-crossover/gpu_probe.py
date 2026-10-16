"""Bend 2.0.36 native CPU/CUDA toolchain smoke test (not graph performance).

No download/install, no private input, no repo writes, no compiler unless requested.
Run on a GPU-capable machine with Bend and CUDA already provisioned.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from time import perf_counter

BEND_VERSION = "bend 2.0.36"  # align with kvnloo/hapsland pinned producer
EXPECTED = "1048576"


def run_checked(cmd, timeout=120):
    start = perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout)
    return proc.stdout.strip(), round((perf_counter() - start) * 1000, 3)


def validate_output(cpu, gpu):
    if cpu != EXPECTED or gpu != EXPECTED or cpu != gpu:
        raise ValueError("Bend native CPU/GPU output mismatch")
    return True


def main():
    if not shutil.which("bend"):
        print("SKIP: Bend compiler unavailable; expected " + BEND_VERSION)
        return 2
    version, _ = run_checked(["bend", "version"], 10)
    if version != BEND_VERSION:
        print("SKIP: exact pinned toolchain required: " + BEND_VERSION + "; got " + version)
        return 2
    if not shutil.which("nvidia-smi"):
        print("SKIP: no NVIDIA GPU evidence; native ! may silently run on CPU")
        return 2
    try:
        run_checked(["nvidia-smi", "-L"], 10)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("SKIP: NVIDIA device not confirmed")
        return 2
    source = Path(__file__).with_name("gpu_smoke.bend")
    with tempfile.TemporaryDirectory(prefix="yohei-bend-probe-") as tmp:
        executable = Path(tmp) / "gpu_smoke"
        _, compile_ms = run_checked(["bend", str(source), "-o", str(executable)], 240)
        cpu, cpu_ms = run_checked([str(executable), "--gpu", "off"])
        gpu, gpu_ms = run_checked([str(executable)])
        validate_output(cpu, gpu)
    print(json.dumps({
        "status": "PASS", "version": version, "kernel": "synthetic_pow2_smoke",
        "output": cpu, "compile_ms": compile_ms,
        "cpu_wall_ms": cpu_ms, "gpu_wall_ms": gpu_ms,
        "graph_kernel_measured": False, "end_to_end_measured": False
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
