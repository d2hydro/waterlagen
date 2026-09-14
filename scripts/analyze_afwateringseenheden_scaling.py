"""Summarize the temporary scaling benchmark without changing production code."""

import json
from pathlib import Path

import numpy as np

ROOT = Path("data/benchmark_afwateringseenheden_scaling")


def main() -> None:
    summaries = []
    for batch_path in sorted(ROOT.glob("*/batch.json")):
        batch = json.loads(batch_path.read_text())
        samples = [
            json.loads(line)
            for line in (batch_path.parent / "samples.jsonl").read_text().splitlines()
        ]
        for result in batch["results"]:
            active = [
                p
                for s in samples
                if result["start"] <= s["time"] <= result["end"]
                for p in s["processes"]
                if p["pid"] == result["pid"]
            ]
            result["sample_peak_rss"] = max(p["rss"] for p in active)
            result["sample_peak_private"] = max(p["private"] for p in active)
            result["max_threads"] = max(p["threads"] for p in active)
            result["mean_active_cores"] = result["cpu_seconds"] / result["total"]
            events = [
                json.loads(line)
                for line in (Path(result["job"]["output"]) / "events.jsonl")
                .read_text()
                .splitlines()
            ]
            ldd_start = next(
                e["time"]
                for e in events
                if e["step"] == "lddcreate" and e["event"] == "start"
            )
            ldd_end = next(
                e for e in events if e["step"] == "lddcreate" and e["event"] == "end"
            )
            result["ldd_active_cores"] = ldd_end["cpu_seconds"] / ldd_end["seconds"]
            ldd_memory = [
                p["rss"]
                for s in samples
                if ldd_start <= s["time"] <= ldd_end["time"]
                for p in s["processes"]
                if p["pid"] == result["pid"]
            ]
            result["ldd_peak_rss"] = max(ldd_memory)
        batch["directory"] = str(batch_path.parent)
        batch["mean_tile_seconds"] = np.mean([r["total"] for r in batch["results"]])
        batch["worker_cpu_seconds"] = sum(r["cpu_seconds"] for r in batch["results"])
        batch["active_cores"] = batch["worker_cpu_seconds"] / batch["wall_seconds"]
        batch["system_cpu_percent_mean"] = np.mean(
            [s["system_cpu_percent"] for s in samples]
        )
        batch["process_read_bytes"] = sum(r["io_read_bytes"] for r in batch["results"])
        batch["process_write_bytes"] = sum(
            r["io_write_bytes"] for r in batch["results"]
        )
        batch["system_disk_read_bytes"] = (
            samples[-1]["disk"]["read_bytes"] - samples[0]["disk"]["read_bytes"]
        )
        batch["system_disk_write_bytes"] = (
            samples[-1]["disk"]["write_bytes"] - samples[0]["disk"]["write_bytes"]
        )
        summaries.append(batch)
    serial = [
        r
        for batch in summaries
        if "serial" in batch["directory"]
        for r in batch["results"]
    ]
    sizes = []
    for size in sorted({r["job"]["size"] for r in serial}):
        runs = [r for r in serial if r["job"]["size"] == size]
        retained_km2 = (size / 1000) ** 2
        processed_km2 = ((size + 4000) / 1000) ** 2
        total = np.mean([r["total"] for r in runs])
        cpu = np.mean([r["cpu_seconds"] for r in runs])
        sizes.append(
            dict(
                size=size,
                repeats=len(runs),
                cells=runs[0]["cells"],
                retained_km2=retained_km2,
                processed_km2=processed_km2,
                overhead=processed_km2 / retained_km2,
                total=total,
                cpu_seconds=cpu,
                lddcreate=np.mean([r["timings"]["lddcreate"] for r in runs]),
                peak_rss=max(r["sample_peak_rss"] for r in runs),
                peak_wset=max(r["peak_wset"] for r in runs),
                seconds_per_retained_km2=total / retained_km2,
                cells_per_retained_km2=runs[0]["cells"] / retained_km2,
                domain_10000km2_tiles=10000 / retained_km2,
                domain_10000km2_cells=10000 / retained_km2 * runs[0]["cells"],
                domain_10000km2_serial_hours=10000 / retained_km2 * total / 3600,
                domain_10000km2_cpu_hours=10000 / retained_km2 * cpu / 3600,
            )
        )
    fit = None
    if len(sizes) >= 3:
        x = np.log([s["cells"] for s in sizes])
        y = np.log([s["lddcreate"] for s in sizes])
        b, log_a = np.polyfit(x, y, 1)
        fit = dict(
            a=np.exp(log_a),
            b=b,
            r_squared_log=1
            - np.sum((y - (log_a + b * x)) ** 2) / np.sum((y - y.mean()) ** 2),
            adjacent_exponents=[
                float((y[i + 1] - y[i]) / (x[i + 1] - x[i])) for i in range(2)
            ],
        )
    parallel = [s for s in summaries if "parallel" in s["directory"]]
    baseline = next((s for s in parallel if s["workers"] == 1), None)
    if baseline:
        for batch in parallel:
            batch["speedup"] = baseline["wall_seconds"] / batch["wall_seconds"]
            batch["efficiency"] = batch["speedup"] / batch["workers"]
    result = dict(sizes=sizes, fit=fit, batches=summaries)
    (ROOT / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            dict(
                sizes=sizes,
                fit=fit,
                parallel=[
                    {k: v for k, v in batch.items() if k != "results"}
                    for batch in parallel
                ],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
