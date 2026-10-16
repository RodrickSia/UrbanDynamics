-- Workspace projection of zoning plans. Footprints and masks are 2D; no mesh is stored.
CREATE SCHEMA IF NOT EXISTS plans;

CREATE TABLE IF NOT EXISTS plans.zone_type_catalog (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL CHECK (category IN ('land_use', 'zoning_type', 'zoning_subtype')),
    "group" TEXT NOT NULL DEFAULT '',
    land_use_codes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS plans.plan (
    id TEXT PRIMARY KEY REFERENCES zoning_plans (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    horizon INTEGER,
    status TEXT NOT NULL,
    jurisdiction TEXT,
    revision INTEGER NOT NULL,
    area_m2 DOUBLE PRECISION NOT NULL,
    study_area geometry(Geometry, 4326) NOT NULL,
    baseline JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS plans.zone_type (
    plan_id TEXT NOT NULL REFERENCES plans.plan (id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    uses TEXT NOT NULL DEFAULT '',
    max_height DOUBLE PRECISION,
    max_floors INTEGER,
    coverage DOUBLE PRECISION,
    far DOUBLE PRECISION,
    setback_front DOUBLE PRECISION,
    setback_side DOUBLE PRECISION,
    setback_rear DOUBLE PRECISION,
    source TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    origin_id TEXT,
    catalog_code TEXT REFERENCES plans.zone_type_catalog (code),
    position INTEGER NOT NULL,
    PRIMARY KEY (plan_id, id)
);

CREATE TABLE IF NOT EXISTS plans.scenario (
    plan_id TEXT NOT NULL REFERENCES plans.plan (id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    locked BOOLEAN NOT NULL,
    copied_from TEXT,
    revision INTEGER,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    created_by TEXT,
    position INTEGER NOT NULL,
    PRIMARY KEY (plan_id, id)
);

CREATE TABLE IF NOT EXISTS plans.zone (
    plan_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    id TEXT NOT NULL,
    type_id TEXT,
    origin_id TEXT,
    geom geometry(Geometry, 4326) NOT NULL,
    label_point geometry(Point, 4326),
    area_m2 DOUBLE PRECISION,
    revision INTEGER,
    source TEXT,
    position INTEGER NOT NULL,
    PRIMARY KEY (plan_id, scenario_id, id),
    FOREIGN KEY (plan_id, scenario_id) REFERENCES plans.scenario (plan_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plans.building (
    plan_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    id TEXT NOT NULL,
    parcel_id TEXT,
    origin_id TEXT,
    name TEXT,
    geom geometry(Geometry, 4326) NOT NULL,
    floors INTEGER,
    floor_height DOUBLE PRECISION,
    height_m DOUBLE PRECISION,
    footprint_m2 DOUBLE PRECISION,
    space_use_id TEXT,
    counts_gfa BOOLEAN,
    counts_far BOOLEAN,
    color TEXT,
    status TEXT,
    origin TEXT,
    template_id TEXT,
    template_version INTEGER,
    ground_anchor JSONB,
    floor_stack JSONB,
    floor_overrides JSONB,
    position INTEGER NOT NULL,
    PRIMARY KEY (plan_id, scenario_id, id),
    FOREIGN KEY (plan_id, scenario_id) REFERENCES plans.scenario (plan_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plans.parcel_snapshot (
    plan_id TEXT NOT NULL REFERENCES plans.plan (id) ON DELETE CASCADE,
    parcel_id TEXT NOT NULL,
    geom geometry(Geometry, 4326) NOT NULL,
    area_m2 DOUBLE PRECISION,
    land_use TEXT,
    source TEXT,
    status TEXT,
    captured_at TIMESTAMPTZ,
    PRIMARY KEY (plan_id, parcel_id)
);

CREATE TABLE IF NOT EXISTS plans.demolition_mask (
    plan_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    id TEXT NOT NULL,
    parcel_id TEXT,
    geom geometry(Geometry, 4326) NOT NULL,
    status TEXT,
    PRIMARY KEY (plan_id, scenario_id, id),
    FOREIGN KEY (plan_id, scenario_id) REFERENCES plans.scenario (plan_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS plans_plan_study_area_idx ON plans.plan USING GIST (study_area);
CREATE INDEX IF NOT EXISTS plans_zone_geom_idx ON plans.zone USING GIST (geom);
CREATE INDEX IF NOT EXISTS plans_building_geom_idx ON plans.building USING GIST (geom);
CREATE INDEX IF NOT EXISTS plans_parcel_snapshot_geom_idx ON plans.parcel_snapshot USING GIST (geom);
CREATE INDEX IF NOT EXISTS plans_demolition_mask_geom_idx ON plans.demolition_mask USING GIST (geom);
