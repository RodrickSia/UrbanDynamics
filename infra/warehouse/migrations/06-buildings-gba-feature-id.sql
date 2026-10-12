ALTER TABLE buildings.gba_lod1
    ADD COLUMN IF NOT EXISTS feature_id TEXT;

UPDATE buildings.gba_lod1
SET feature_id = gba_id
WHERE feature_id IS NULL;

ALTER TABLE buildings.gba_lod1
    ALTER COLUMN feature_id SET NOT NULL;

ALTER TABLE buildings.gba_lod1
    DROP CONSTRAINT IF EXISTS gba_lod1_pkey;

ALTER TABLE buildings.gba_lod1
    ADD CONSTRAINT gba_lod1_pkey PRIMARY KEY (feature_id);
