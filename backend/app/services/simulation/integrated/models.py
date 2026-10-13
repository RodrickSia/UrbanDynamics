from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from ..models import StrictModel, PolygonInput

Use = Literal["residential", "school", "office", "hospital", "other"]


class Building(StrictModel):
    name: str = Field(default="Building", min_length=1, max_length=80)
    use: Use = "residential"
    footprint: PolygonInput
    floors: int = Field(default=12, ge=1, le=100)
    height_m: float = Field(default=36, gt=0, le=400)
    gross_floor_area_m2: float | None = Field(default=None, gt=0, le=2_000_000)
    units: int = Field(default=0, ge=0, le=10000)
    residents: int = Field(default=0, ge=0, le=20000)
    staff: int = Field(default=0, ge=0, le=20000)
    daily_visitors: int = Field(default=0, ge=0, le=20000)
    daily_users: int = Field(default=0, ge=0, le=20000)
    service_capacity: int = Field(default=0, ge=0, le=50000)
    # Shared hourly schedule: used by visitors/staff, trips and operational loads.
    activity_profile: list[float] | None = Field(default=None, min_length=24, max_length=24)

    @model_validator(mode="after")
    def schedule(self):
        if self.activity_profile is not None and (min(self.activity_profile) < 0 or sum(self.activity_profile) <= 0):
            raise ValueError("Activity profile must be nonnegative with positive total")
        return self


class Tree(StrictModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-85, le=85)
    canopy_radius_m: float = Field(default=3, gt=0, le=30)
    height_m: float = Field(default=6, gt=0, le=50)
    stage: Literal["planted", "mature", "existing"] = "mature"


class Design(StrictModel):
    buildings: list[Building] = Field(default_factory=list, max_length=20)
    paved_m2: float = Field(default=0, ge=0, le=1_000_000)
    permeable_m2: float = Field(default=0, ge=0, le=1_000_000)
    green_m2: float = Field(default=0, ge=0, le=1_000_000)
    trees: list[Tree] = Field(default_factory=list, max_length=300)
    storage_m3: float = Field(default=0, ge=0, le=10000)
    storage_initial_m3: float = Field(default=0, ge=0, le=10000)
    storage_outlet_diameter_m: float = Field(default=.25, ge=.05, le=1)
    gate_lanes: int = Field(default=1, ge=1, le=4)
    gate_service_seconds: float = Field(default=8, ge=1, le=120)
    parking_spaces: int = Field(default=0, ge=0, le=10000)
    stagger_hours: int = Field(default=1, ge=1, le=3)
    efficient_fixtures: bool = False
    efficient_equipment: bool = False
    reuse_m3_day: float = Field(default=0, ge=0, le=10000)
    ev_chargers: int = Field(default=0, ge=0, le=1000)
    ev_charging_hour: int = Field(default=18, ge=0, le=23)
    added_road_m: float = Field(default=0, ge=0, le=2000)
    removed_road_m: float = Field(default=0, ge=0, le=2000)

    @model_validator(mode="after")
    def storage(self):
        if self.storage_initial_m3 > self.storage_m3:
            raise ValueError("Initial storage exceeds tank capacity")
        return self


class Conditions(StrictModel):
    level: Literal["low", "base", "high"] = "base"
    seed: int = Field(default=2026, ge=0, le=2**31-1)
    solar_date: date = date(2026, 4, 15)
    rainfall_mm: float | None = Field(default=None, ge=0, le=300)
    coefficient_profile: Literal["reviewed", "demo"] = "reviewed"


class Baseline(StrictModel):
    design: Design
    source: str = Field(min_length=5, max_length=1000)


class MapMultiPolygon(StrictModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[tuple[float, float]]]] = Field(min_length=1, max_length=20)


class MapBuildingFeature(StrictModel):
    type: Literal["Feature"] = "Feature"
    id: str | int | None = None
    geometry: PolygonInput | MapMultiPolygon
    # Pass raw source properties, not computed extrusion paint values.
    properties: dict[str, str | float | bool | None] = Field(default_factory=dict, max_length=64)
    height_kind: Literal["source_attribute", "visual_fallback", "unknown"] = "source_attribute"

    @model_validator(mode="after")
    def bounded_feature(self):
        from ..engine import polygon_and_area
        if self.id is not None and len(str(self.id)) > 100:
            raise ValueError("Map building ID exceeds 100 characters")
        if any(len(key) > 100 or isinstance(value, str) and len(value) > 500 for key, value in self.properties.items()):
            raise ValueError("Map building properties exceed size limits")
        polygons = [self.geometry.coordinates] if self.geometry.type == "Polygon" else self.geometry.coordinates
        if sum(len(ring) for polygon in polygons for ring in polygon) > 2000:
            raise ValueError("Map building supports at most 2,000 vertices")
        for polygon in polygons:
            polygon_and_area(PolygonInput(type="Polygon", coordinates=polygon))
        from shapely.geometry import shape
        if not shape(self.geometry.model_dump()).is_valid:
            raise ValueError("Map building MultiPolygon must be valid")
        return self


class MapBuildingCollection(StrictModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[MapBuildingFeature] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def bounded_collection(self):
        vertices = 0
        for feature in self.features:
            polygons = [feature.geometry.coordinates] if feature.geometry.type == "Polygon" else feature.geometry.coordinates
            vertices += sum(len(ring) for polygon in polygons for ring in polygon)
        if vertices > 20000:
            raise ValueError("Map context supports at most 20,000 total vertices")
        return self


class MapContext(StrictModel):
    provider: Literal["goong", "team_warehouse", "osm", "other"]
    source_layer: str = Field(default="VN_Building", min_length=1, max_length=80)
    dataset_version: str | None = Field(default=None, max_length=100)
    captured_at: datetime
    bbox: tuple[float, float, float, float]
    coverage: Literal["loaded_tiles", "provided_extract"] = "loaded_tiles"
    buildings: MapBuildingCollection

    @model_validator(mode="after")
    def valid_coverage(self):
        west, south, east, north = self.bbox
        if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
            raise ValueError("Map context bbox must be finite WGS84 bounds")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("Map context captured_at must include a timezone")
        return self


class IntegratedRequest(StrictModel):
    title: str = Field(default="Chung cư tại Thủ Đức", min_length=1, max_length=160)
    site: PolygonInput
    development: Design
    baseline: Baseline | None = None
    conditions: Conditions = Field(default_factory=Conditions)
    # Published local/warehouse data only; clients cannot supply fetch URLs or paths.
    data_mode: Literal["auto", "synthetic", "snapshot_required"] = "auto"
    snapshot_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    map_context: MapContext | None = None

    @model_validator(mode="after")
    def compatible_context(self):
        if self.map_context is not None and self.data_mode == "synthetic":
            raise ValueError("Map context cannot be supplied in synthetic mode")
        return self


class RecommendationRequest(StrictModel):
    budget_vnd: float | None = Field(default=None, ge=0, le=1e13)
    allow_surface_changes: bool = True
    allow_storage: bool = True
    allow_operations: bool = True
    maximum_additional_storage_m3: float = Field(default=200, ge=0, le=1000)
    maximum_surface_conversion_m2: float = Field(default=1500, ge=0, le=10000)
    minimum_paved_m2: float = Field(default=0, ge=0, le=1_000_000)


class SensitivityRequest(StrictModel):
    mode: Literal["demand", "native_traffic"] = "demand"
    parameter_ids: list[str] | None = Field(default=None, min_length=1, max_length=12)
    low_multiplier: float = Field(default=.7, ge=.1, lt=1)
    high_multiplier: float = Field(default=1.3, gt=1, le=3)

    @model_validator(mode="after")
    def bounded_analysis(self):
        if self.parameter_ids is not None and len(set(self.parameter_ids)) != len(self.parameter_ids):
            raise ValueError("Sensitivity parameter IDs must be unique")
        if self.mode == "native_traffic" and (not self.parameter_ids or len(self.parameter_ids) > 3):
            raise ValueError("Native traffic sensitivity requires 1 to 3 explicit traffic parameter IDs")
        return self
