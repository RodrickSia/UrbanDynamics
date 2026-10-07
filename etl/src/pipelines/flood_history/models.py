from dataclasses import dataclass


@dataclass(frozen=True)
class FloodObservation:
    id: str
    observed_at: str | None
    location: str
    depth_min_cm: float | None
    depth_max_cm: float | None
    cause: str | None
