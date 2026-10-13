"""Isolated SWMM C engine: no global solver state shared across API requests."""
import json
import sys
from pathlib import Path

from swmm.toolkit import output, solver
from swmm.toolkit.shared_enum import ElementType, NodeAttribute, LinkAttribute, SubcatchAttribute, Time


def run(directory, detailed=False):
    code = solver.swmm_run(str(directory/"drainage.inp"), str(directory/"drainage.rpt"), str(directory/"drainage.out"))
    if code:
        raise RuntimeError(f"SWMM returned {code}")
    handle = output.init()
    try:
        output.open(handle, str(directory/"drainage.out"))
        sizes = output.get_proj_size(handle)
        periods = output.get_times(handle, Time.NUM_PERIODS)
        step = output.get_times(handle, Time.REPORT_STEP)
        flooding, nodes, runoff = 0, [], [0.0]*periods
        node_series, link_series = {}, {}
        for i in range(sizes[1]):
            name = output.get_elem_name(handle, ElementType.NODE, i)
            values = output.get_node_series(handle, i, NodeAttribute.FLOODING_LOSSES, 0, periods-1)
            depths = output.get_node_series(handle, i, NodeAttribute.INVERT_DEPTH, 0, periods-1)
            volume = sum(values)*step
            flooding += volume
            nodes.append({"id": name, "flooding_m3": volume, "peak_depth_m": max(depths, default=0),
                          "flooding_duration_minutes": sum(v > 1e-8 for v in values)*step/60})
            if detailed:
                node_series[name] = {"flooding_m3_s": list(values), "depth_m": list(depths)}
        for i in range(sizes[0]):
            series = output.get_subcatch_series(handle, i, SubcatchAttribute.RUNOFF_RATE, 0, periods-1)
            runoff = [a+b for a, b in zip(runoff, series)]
        if detailed:
            for i in range(sizes[2]):
                name = output.get_elem_name(handle, ElementType.LINK, i)
                flows = output.get_link_series(handle, i, LinkAttribute.FLOW_RATE, 0, periods-1)
                depths = output.get_link_series(handle, i, LinkAttribute.FLOW_DEPTH, 0, periods-1)
                link_series[name] = {"flow_m3_s": list(flows), "depth_m": list(depths)}
        report = (directory/"drainage.rpt").read_text(encoding="utf-8", errors="replace")
        errors = []
        for line in report.splitlines():
            if "Continuity Error (%)" in line:
                errors.append(float(line.split()[-1]))
        result = {"version": str(solver.swmm_get_version()), "node_flooding_m3": flooding,
                  "runoff_peak_m3_s": max(runoff, default=0), "runoff_sample_integral_m3": sum(runoff)*step,
                  "nodes": nodes, "hourly_label": "5-minute samples, 3-hour event",
                  "timeseries": {"minute": [(i+1)*step/60 for i in range(periods)], "runoff_m3_s": runoff},
                  "continuity_errors_percent": errors,
                  "balance_passed": bool(errors) and all(abs(e) <= 5 for e in errors),
                  "volume_method": "Flood/runoff rates integrated at report interval; approximate, not solver continuity ledger"}
        if detailed:
            result["timeseries"].update(nodes=node_series, links=link_series)
        (directory/"result.json").write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    finally:
        output.close(handle)


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), detailed="--detailed" in sys.argv[2:])
