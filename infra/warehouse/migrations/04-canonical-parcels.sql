-- Keep source fragments intact. Publish one indexed geometry per source parcel.
CREATE MATERIALIZED VIEW IF NOT EXISTS parcels.plot AS
WITH grouped AS (
    SELECT min(id) AS id, max(uniq_id) AS uniq_id,
           max(tinh) AS tinh, max(quan) AS quan, max(phuong) AS phuong,
           max(to_ban_do) AS to_ban_do, max(thua) AS thua,
           max(mdsdd) AS mdsdd, max(loai_dat_qh) AS loai_dat_qh,
           max(quyet_dinh) AS quyet_dinh, max(do_an) AS do_an,
           count(*) AS source_fragments,
           count(DISTINCT mdsdd) > 1 AS conflicting_land_use,
           ST_Multi(ST_CollectionExtract(ST_UnaryUnion(ST_Collect(geom)), 3)) AS geom
    FROM parcels.land_plot
    GROUP BY CASE WHEN lower(trim(coalesce(uniq_id,''))) NOT IN ('','null','none','0')
                  THEN jsonb_build_array(uniq_id,tinh,quan,phuong)::text
                  ELSE 'fragment:' || id::text END
), projected AS (
    SELECT *, ST_Transform(geom,3857) AS geom_web,
           ST_Area(geom::geography) AS area_m2 FROM grouped
)
SELECT *, ST_Area(geom_web) AS area_web FROM projected WHERE NOT ST_IsEmpty(geom);

CREATE UNIQUE INDEX IF NOT EXISTS parcel_plot_id_idx ON parcels.plot(id);
CREATE INDEX IF NOT EXISTS parcel_plot_geom_idx ON parcels.plot USING gist(geom);
CREATE INDEX IF NOT EXISTS parcel_plot_web_idx ON parcels.plot USING gist(geom_web);
ANALYZE parcels.plot;
