from dataclasses import dataclass
@dataclass(frozen=True)
class LandPrice:
    id: str
    road: str
    start: str
    end: str
    residential_vnd_m2: int
    commercial_vnd_m2: int
    other_nonagricultural_vnd_m2: int
