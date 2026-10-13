"""Map SUMO lane queues to physical edges without inferring IDs from names."""
from xml.etree import ElementTree as ET


def queue_intervals(directory, intervals):
    lane_edges = {lane.get("id"): edge.get("id")
                  for edge in ET.parse(directory/"network.xml").getroot().findall("edge")
                  for lane in edge.findall("lane")}
    steps = list(ET.parse(directory/"queues.xml").getroot())
    output = []
    for interval in intervals:
        samples = [s for s in steps if interval["begin_seconds"] <= float(s.get("timestep")) < interval["end_seconds"]]
        lanes = {}
        for step in samples:
            for lane in step.iter("lane"):
                identifier = lane.get("id")
                if identifier not in lane_edges:
                    raise ValueError("SUMO queue lane does not belong to the saved network")
                value = float(lane.get("queueing_length"))
                lanes[identifier] = max(lanes.get(identifier, 0), value)
        edges = {}
        for identifier, peak in lanes.items():
            edge = lane_edges[identifier]
            edges[edge] = max(edges.get(edge, 0), peak)
        output.append({"begin_seconds": interval["begin_seconds"], "end_seconds": interval["end_seconds"],
                       "sample_count": len(samples), "sample_interval_seconds": 30,
                       "lanes": [{"lane_id": key, "edge_id": lane_edges[key], "sampled_peak_queue_m": value}
                                 for key, value in sorted(lanes.items())],
                       "edges": [{"edge_id": key, "sampled_peak_queue_m": value} for key, value in sorted(edges.items())],
                       "method": "Maximum reported lane queue length at 30-second samples within [begin,end); lanes are not summed.",
                       "missing_lane_policy": "No reported queue record is not substituted with a measured zero."})
    return output
