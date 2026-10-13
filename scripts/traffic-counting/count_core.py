"""Finite directed line crossings, independent of detector/tracker implementation."""
from dataclasses import dataclass, field
import math


@dataclass
class Line:
    name: str
    start: tuple[float, float]
    end: tuple[float, float]
    negative_to_positive: str = "negative_to_positive"
    positive_to_negative: str = "positive_to_negative"
    margin: float = 3
    states: dict = field(default_factory=dict)
    counted: set = field(default_factory=set)

    def __post_init__(self):
        if self.start == self.end or self.margin < 0:
            raise ValueError("Line must have positive length and nonnegative margin")

    def distance(self, point):
        ax, ay = self.start
        bx, by = self.end
        return ((bx-ax)*(point[1]-ay) - (by-ay)*(point[0]-ax)) / math.hypot(bx-ax, by-ay)

    def update(self, track_id, point, frame, max_gap_frames):
        distance = self.distance(point)
        if abs(distance) <= self.margin:
            return None
        side = 1 if distance > 0 else -1
        previous = self.states.get(track_id)
        self.states[track_id] = (side, point, frame, distance)
        if not previous or frame - previous[2] > max_gap_frames or previous[0] == side:
            return None
        direction = self.negative_to_positive if side == 1 else self.positive_to_negative
        # Count at most once per track/line/direction. A return journey may count
        # in the opposite direction, but jitter must not generate repeat counts.
        key = (track_id, direction)
        if key in self.counted:
            return None
        old_point, old_distance = previous[1], previous[3]
        fraction = abs(old_distance) / (abs(old_distance) + abs(distance))
        crossing = tuple(old_point[i] + fraction*(point[i]-old_point[i]) for i in (0, 1))
        dx, dy = self.end[0]-self.start[0], self.end[1]-self.start[1]
        projection = ((crossing[0]-self.start[0])*dx + (crossing[1]-self.start[1])*dy) / (dx*dx+dy*dy)
        if not 0 <= projection <= 1:
            return None
        self.counted.add(key)
        # Interpolate the event time between the stable observations, including
        # a deadband dwell; assigning every event to its detection frame biases bins.
        crossing_frame = previous[2] + fraction*(frame-previous[2])
        return {"line_id": self.name, "direction": direction, "track_id": track_id,
                "frame": crossing_frame, "crossing_xy": crossing}

    def prune(self, frame, max_gap_frames):
        self.states = {key: value for key, value in self.states.items() if frame-value[2] <= max_gap_frames}


def aggregate(events, start_seconds, end_seconds, bin_seconds):
    """Keep observation duration; an extrapolated hourly rate is explicitly labeled."""
    if end_seconds <= start_seconds or bin_seconds <= 0:
        raise ValueError("Observation and bins must have positive duration")
    groups = sorted({(e["line_id"], e["direction"], e["vehicle_class"]) for e in events})
    rows = []
    count_bins = math.ceil((end_seconds-start_seconds)/bin_seconds)
    for index in range(count_bins):
        low = start_seconds + index*bin_seconds
        high = min(end_seconds, low+bin_seconds)
        for line, direction, vehicle_class in groups:
            count = sum(e["line_id"] == line and e["direction"] == direction and e["vehicle_class"] == vehicle_class
                        and low <= e["video_seconds"] < high for e in events)
            rows.append({"line_id": line, "direction": direction, "vehicle_class": vehicle_class,
                         "start_video_seconds": low, "end_video_seconds": high,
                         "observed_seconds": high-low, "count": count,
                         "extrapolated_vehicles_hour": count*3600/(high-low),
                         "rate_kind": "short_window_extrapolation_not_hour_observation"})
    return rows
