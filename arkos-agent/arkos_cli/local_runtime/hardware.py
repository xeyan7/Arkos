"""Live hardware budget probe.

Budget-source rule: discrete cards may trust the device query (measured honest within rounding);
unified-memory devices must budget from OS free physical memory minus headroom — their device
queries have been observed off by 3x in both directions. Every probe here must work under a
stripped PATH — gateway and service sessions don't inherit the interactive environment.
"""

from __future__ import annotations

from contextlib import suppress
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from arkos_cli.local_runtime.estimator import HardwareBudget

logger = logging.getLogger(__name__)

_GIB = 1 << 30
_MARGIN_FLOOR = 2 << 30
_MARGIN_FRACTION = 0.09
_UMA_HEADROOM_FRACTION = 0.20

_POOL_DISAGREEMENT_FACTOR = 1.5
_POOL_RAM_FRACTION = 0.75

_CU_DEVICE_ATTRIBUTE_INTEGRATED = 18

_POOL_NEGATIVE_TTL_S = 60.0
_pool_probe_cache: tuple[float, "tuple[int, bool | None] | None"] | None = None

_DEVICE_LINE_RE = re.compile(r"CUDA\d+:.*\((\d+)\s*MiB,\s*\d+\s*MiB free\)\s*$")


def _stdout(*argv: str) -> str:
    return subprocess.run(
        list(argv), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5
    ).stdout


def _ram_bytes() -> tuple[int, int]:
    """(total, available) physical memory, cross-platform stdlib."""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = ([("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)]
                        + [(name, ctypes.c_ulonglong) for name in (
                            "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
                            "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")])

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys, stat.ullAvailPhys
    except (AttributeError, OSError):
        pass
    try:
        if sys.platform == "darwin":
            total = int(_stdout("/usr/sbin/sysctl", "-n", "hw.memsize").strip() or 0)
            if total <= 0:
                return 0, 0
            avail = total // 2
            with suppress(OSError, ValueError):
                out = _stdout("/usr/bin/vm_stat")
                page_m = re.search(r"page size of (\d+)", out)
                page = int(page_m.group(1)) if page_m else 16384
                pages = sum(int(m.group(1)) for key in (
                    "Pages free", "Pages inactive", "Pages purgeable", "Pages speculative")
                    if (m := re.search(rf"{key}:\s+(\d+)\.", out)))
                if pages > 0:
                    avail = pages * page
            return total, avail
        page = int(_stdout("getconf", "PAGE_SIZE") or 4096)
        total = int(_stdout("getconf", "_PHYS_PAGES") or 0) * page
        avail = total // 2
        with suppress(OSError, ValueError):
            avail = int(_stdout("getconf", "_AVPHYS_PAGES") or 0) * page or avail
        return total, avail
    except (OSError, ValueError):
        return 0, 0


_smi_path_cache: "tuple[str | None] | None" = None


def _nvidia_smi_path() -> str | None:
    """Absolute path to nvidia-smi, or None. PATH first (respects user overrides), then the
    driver's known install locations on Windows and WSL."""
    global _smi_path_cache
    if _smi_path_cache is not None:
        return _smi_path_cache[0]
    found = shutil.which("nvidia-smi")
    if found is None and os.name == "nt":
        windir = os.environ.get("SystemRoot", r"C:\Windows")
        candidates = (
            Path(windir) / "System32" / "nvidia-smi.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe",
        )
        found = next((str(c) for c in candidates if c.exists()), None)
    elif found is None and sys.platform.startswith("linux"):
        candidate = Path("/usr/lib/wsl/lib/nvidia-smi")
        if candidate.exists():
            found = str(candidate)
    _smi_path_cache = (found,)
    return found


def _nvidia_vram() -> tuple[int, int] | None:
    """(total, free) MiB->bytes from nvidia-smi, or None."""
    exe = _nvidia_smi_path()
    if exe is None:
        return None
    with suppress(OSError, ValueError, subprocess.TimeoutExpired):
        out = subprocess.run(
            [exe, "--query-gpu=memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
        if out.returncode != 0 or not out.stdout.strip():
            return None
        total_mib, free_mib = (int(x) for x in out.stdout.strip().splitlines()[0].split(","))
        return total_mib << 20, free_mib << 20
    return None


def _cuda_driver_pool() -> "tuple[int, bool | None] | None":
    """(allocator_total_bytes, integrated_or_None) from the CUDA driver API via ctypes against the
    driver's own DLL/SO — no toolkit, no subprocess, ~ms. INTEGRATED is the vendor's own
    unified-memory declaration; total is the pool the allocator will actually hand out (on
    carve-out devices, several times what nvidia-smi reports)."""
    import ctypes

    for name in ("nvcuda.dll", "libcuda.so.1", "libcuda.so"):
        try:
            cuda = ctypes.CDLL(name)
            break
        except OSError:
            continue
    else:
        return None
    with suppress(OSError, AttributeError):
        if cuda.cuInit(0) != 0:
            return None
        dev = ctypes.c_int()
        if cuda.cuDeviceGet(ctypes.byref(dev), 0) != 0:
            return None
        total = ctypes.c_size_t()
        getter = getattr(cuda, "cuDeviceTotalMem_v2", None) or cuda.cuDeviceTotalMem
        if getter(ctypes.byref(total), dev) != 0 or total.value <= 0:
            return None
        integrated: bool | None = None
        attr = ctypes.c_int()
        if cuda.cuDeviceGetAttribute(
                ctypes.byref(attr), _CU_DEVICE_ATTRIBUTE_INTEGRATED, dev) == 0:
            integrated = bool(attr.value)
        return total.value, integrated
    return None


def _engine_device_pool() -> "tuple[int, bool | None] | None":
    """(engine_total_bytes, None) from the installed runtime's own --list-devices, or None. The
    fallback when the driver API is unreachable: asks the exact binary that will do the
    allocating. Carries no integrated verdict — callers must gate it."""
    with suppress(Exception):
        from arkos_cli.local_runtime.binaries import installed_tags, runtimes_root, server_binary

        tags = installed_tags()
        if not tags:
            return None
        backend_dirs = [d for d in (runtimes_root() / tags[0]).iterdir() if d.is_dir()]
        if not backend_dirs:
            return None
        exe = server_binary(backend_dirs[0])
        out = subprocess.run([str(exe), "--list-devices"], capture_output=True,
                             text=True, timeout=30, cwd=str(exe.parent))
        if out.returncode != 0:
            return None
        for line in (out.stdout + out.stderr).splitlines():
            m = _DEVICE_LINE_RE.search(line)
            if m:
                return int(m.group(1)) << 20, None
    return None


def _device_pool_view() -> "tuple[int, bool | None] | None":
    """Best available allocator-side view, cached: a hit is permanent for the process, a miss
    retries after a short TTL (the engine binary can appear mid-session via a pane install)."""
    global _pool_probe_cache
    now = time.monotonic()
    if _pool_probe_cache is not None:
        stamp, view = _pool_probe_cache
        if view is not None or now - stamp < _POOL_NEGATIVE_TTL_S:
            return view
    view = _cuda_driver_pool() or _engine_device_pool()
    _pool_probe_cache = (now, view)
    return view


def _unified_pool_bytes(smi_total: int, ram_total: int) -> int | None:
    """The real pool size when this NVIDIA device is unified memory behind a carve-out, else None.

    The driver's INTEGRATED attribute decides in BOTH directions when readable; only the
    attribute-less engine fallback needs the two numeric gates, both of which must hold.
    """
    view = _device_pool_view()
    if view is None:
        return None
    pool, integrated = view
    if integrated is not None:
        return pool if integrated else None
    if (smi_total > 0 and pool >= int(smi_total * _POOL_DISAGREEMENT_FACTOR)
            and ram_total > 0 and pool >= int(ram_total * _POOL_RAM_FRACTION)):
        return pool
    return None


def _uma_budget(base: int, total: int) -> HardwareBudget:
    usable = max(0, int(base * (1 - _UMA_HEADROOM_FRACTION)))
    return HardwareBudget(usable_vram_bytes=usable, total_device_bytes=total,
                          ram_available_bytes=0, uma=True)


def probe_budget(*, planning: bool = False) -> HardwareBudget:
    """Construct the budget per the source rules above.

    ``planning=False``: LIVE budget (free VRAM now) for launch-time fit and growth re-grants.
    ``planning=True``: CAPACITY budget (total minus margin) for catalog pricing and quant
    selection — pricing against live-free while a model was loaded made every row read as too
    large. The managed server unloads/relaunches itself, so capacity is real.
    """
    ram_total, ram_avail = _ram_bytes()
    vram = _nvidia_vram()

    unified = _unified_pool_bytes(vram[0] if vram else 0, ram_total)
    if unified is not None:
        logger.info(
            "unified-memory NVIDIA device: allocator pool %.1f GiB "
            "(nvidia-smi carve-out: %s); budgeting from the pool",
            unified / _GIB,
            f"{vram[0] / _GIB:.1f} GiB" if vram else "unavailable")
        if planning:
            base = unified
        else:
            live = (vram[1] + ram_avail) if vram else ram_avail
            base = min(unified, live)
        return _uma_budget(base, unified)

    if vram is None:
        return _uma_budget(ram_total if planning else ram_avail, ram_total)

    total, free = vram
    margin = max(_MARGIN_FLOOR, int(total * _MARGIN_FRACTION))
    return HardwareBudget(usable_vram_bytes=max(0, (total if planning else free) - margin),
                          total_device_bytes=total,
                          ram_available_bytes=ram_total if planning else ram_avail,
                          uma=False)
