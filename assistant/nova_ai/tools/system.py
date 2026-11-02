"""Outils « système » : état de la machine, processus, modes de performance."""
from __future__ import annotations

import os
import time
from pathlib import Path

from ..schema import obj
from . import Tool, ToolContext, ToolResult

MODES = {"eco": "éco", "equilibre": "équilibré", "performance": "performance", "jeu": "jeu"}


def _read(path: str | Path, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _cpu_times() -> tuple[int, int]:
    fields = [int(x) for x in _read("/proc/stat").splitlines()[0].split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    return idle, sum(fields)


def cpu_percent(interval: float = 0.25) -> float:
    try:
        idle1, total1 = _cpu_times()
        time.sleep(interval)
        idle2, total2 = _cpu_times()
        busy = (total2 - total1) - (idle2 - idle1)
        return round(100.0 * busy / max(1, total2 - total1), 1)
    except (IndexError, ValueError):
        return -1.0


def memory_info() -> dict[str, float]:
    info: dict[str, float] = {}
    for line in _read("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        try:
            info[key] = int(rest.split()[0]) / 1024 / 1024  # Gio
        except (IndexError, ValueError):
            continue
    return info


def cpu_temperature() -> float | None:
    """Température du processeur (x86_pkg_temp sur Intel, sinon la zone la plus chaude)."""
    best = None
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        kind = _read(zone / "type")
        raw = _read(zone / "temp")
        if not raw.lstrip("-").isdigit():
            continue
        value = int(raw) / 1000
        if kind == "x86_pkg_temp":
            return value
        best = value if best is None else max(best, value)
    return best


def battery_info() -> dict | None:
    supplies = Path("/sys/class/power_supply")
    battery, on_ac = None, None
    for supply in sorted(supplies.glob("*")):
        kind = _read(supply / "type")
        if kind == "Battery" and battery is None:
            battery = {"capacity": _read(supply / "capacity", "?"), "status": _read(supply / "status", "?")}
        elif kind in ("Mains", "USB"):
            on_ac = on_ac or _read(supply / "online") == "1"
    if battery is None:
        return None
    battery["ac"] = bool(on_ac)
    return battery


def _uptime_text() -> str:
    try:
        seconds = int(float(_read("/proc/uptime").split()[0]))
    except (IndexError, ValueError):
        return "?"
    hours, minutes = divmod(seconds // 60, 60)
    days, hours = divmod(hours, 24)
    parts = ([f"{days} j"] if days else []) + ([f"{hours} h"] if hours else []) + [f"{minutes} min"]
    return " ".join(parts)


def _disk(path: Path) -> str:
    try:
        st = os.statvfs(path)
    except OSError:
        return "?"
    total = st.f_blocks * st.f_frsize / 1024**3
    free = st.f_bavail * st.f_frsize / 1024**3
    return f"{total - free:.0f} / {total:.0f} Go utilisés ({free:.0f} Go libres)"


def current_mode(ctx: ToolContext) -> str:
    result = ctx.runner.run(["nova-mode", "get"], timeout=3)
    return result.stdout.strip() if result.ok and result.stdout.strip() else "inconnu"


def system_status(args: dict, ctx: ToolContext) -> ToolResult:
    mem = memory_info()
    used = mem.get("MemTotal", 0) - mem.get("MemAvailable", 0)
    lines = [
        f"Processeur : {cpu_percent():.0f} % d'utilisation, charge {(_read('/proc/loadavg') or '? ? ?').split()[0]}",
        f"Mémoire : {used:.1f} / {mem.get('MemTotal', 0):.1f} Go",
    ]
    if mem.get("SwapTotal"):
        lines.append(f"Swap (zram) : {mem['SwapTotal'] - mem.get('SwapFree', 0):.1f} / {mem['SwapTotal']:.1f} Go")
    temp = cpu_temperature()
    if temp is not None:
        lines.append(f"Température processeur : {temp:.0f} °C")
    bat = battery_info()
    if bat:
        source = "sur secteur" if bat["ac"] else "sur batterie"
        lines.append(f"Batterie : {bat['capacity']} % ({bat['status']}, {source})")
    lines += [
        f"Disque système : {_disk(Path('/'))}",
        f"Allumé depuis : {_uptime_text()}",
        f"Noyau : {os.uname().release}",
        f"Mode de performance : {current_mode(ctx)}",
    ]
    return ToolResult(True, "\n".join(lines))


def top_processes(args: dict, ctx: ToolContext) -> ToolResult:
    sort = "-%mem" if args.get("sort") == "memory" else "-%cpu"
    limit = max(1, min(int(args.get("limit", 8)), 20))
    result = ctx.runner.run(["ps", "-eo", "pid,comm,%cpu,%mem", f"--sort={sort}", "--no-headers"], timeout=5)
    if not result.ok:
        return ToolResult(False, f"Impossible de lister les processus : {result.stderr.strip()}")
    rows = [line.split() for line in result.stdout.splitlines() if line.strip()][:limit]
    text = "\n".join(f"{r[1]} (pid {r[0]}) : {r[2]} % CPU, {r[3]} % RAM" for r in rows if len(r) >= 4)
    return ToolResult(True, text or "Aucun processus.")


def set_performance_mode(args: dict, ctx: ToolContext) -> ToolResult:
    mode = args["mode"]
    result = ctx.runner.run(["nova-mode", "set", mode], timeout=30)
    if not result.ok:
        return ToolResult(False, f"Échec du changement de mode : {result.stderr.strip() or result.stdout.strip()}")
    return ToolResult(True, f"Mode {MODES[mode]} activé.")


TOOLS = [
    Tool(
        name="system_status",
        description=(
            "Get the current state of the computer: CPU usage, memory, temperature, battery, "
            "disk space, uptime, kernel and performance mode. Call this when the user asks how "
            "the computer is doing, why it is slow or hot, or about battery or storage."
        ),
        parameters=obj({}),
        handler=system_status,
        risk="read",
        label=lambda a: "Analyse de l'état du système",
    ),
    Tool(
        name="top_processes",
        description="List the programs using the most CPU or memory right now. Call this to find what slows the computer down.",
        parameters=obj({
            "sort": {"type": "string", "enum": ["cpu", "memory"], "description": "Sort key"},
            "limit": {"type": "integer", "description": "Number of processes, 1 to 20 (default 8)"},
        }),
        handler=top_processes,
        risk="read",
        label=lambda a: "Recherche des programmes gourmands",
    ),
    Tool(
        name="set_performance_mode",
        description=(
            "Switch the Nova performance mode: 'eco' (battery saving, fewer visual effects), "
            "'equilibre' (balanced default), 'performance' (maximum speed) or 'jeu' (gaming: "
            "maximum performance, effects off, low latency)."
        ),
        parameters=obj({"mode": {"type": "string", "enum": list(MODES)}}, ["mode"]),
        handler=set_performance_mode,
        risk="action",
        label=lambda a: f"Passage en mode {MODES.get(a.get('mode'), a.get('mode'))}",
    ),
]
