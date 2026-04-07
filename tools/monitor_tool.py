"""
MonitorTool — CC-aligned system monitoring.
CC: feature-gated behind MONITOR_TOOL.
Returns system metrics: CPU, memory, disk, top processes.
"""

from tools.base import BaseTool


class MonitorTool(BaseTool):
    name = "Monitor"
    description = (
        "Get system resource metrics: CPU usage, memory, disk space, "
        "and top processes by CPU consumption. Useful for diagnosing "
        "performance issues or checking system health."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "enum": ["all", "cpu", "memory", "disk", "processes"],
                "description": "Which metric to report (default: all)",
            },
        },
        "required": [],
    }
    is_read_only = True
    concurrency_safe = True

    def execute(self, input_data: dict) -> str:
        metric = input_data.get("metric", "all")
        try:
            import psutil
        except ImportError:
            return "Error: psutil not installed. Run: pip install psutil"

        lines = []

        if metric in ("all", "cpu"):
            cpu_pct = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count()
            lines.append(f"## CPU\n  Usage: {cpu_pct}% ({cpu_count} cores)")

        if metric in ("all", "memory"):
            mem = psutil.virtual_memory()
            lines.append(
                f"## Memory\n  Total: {mem.total // (1024**3)}GB | "
                f"Used: {mem.used // (1024**3)}GB ({mem.percent}%) | "
                f"Available: {mem.available // (1024**3)}GB"
            )

        if metric in ("all", "disk"):
            disk = psutil.disk_usage("/")
            lines.append(
                f"## Disk (/)\n  Total: {disk.total // (1024**3)}GB | "
                f"Used: {disk.used // (1024**3)}GB ({disk.percent}%) | "
                f"Free: {disk.free // (1024**3)}GB"
            )

        if metric in ("all", "processes"):
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    info = p.info
                    procs.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            top = sorted(procs, key=lambda x: x.get('cpu_percent', 0) or 0, reverse=True)[:10]
            lines.append("## Top Processes (by CPU)")
            for p in top:
                lines.append(
                    f"  PID {p.get('pid', '?'):>6} | {p.get('name', '?'):<20} | "
                    f"CPU {p.get('cpu_percent', 0):>5.1f}% | "
                    f"Mem {p.get('memory_percent', 0):>5.1f}%"
                )

        return "\n".join(lines) if lines else "No metrics available."
