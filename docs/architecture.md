# Initial architecture

The frontend calls the backend API. The ETL service periodically extracts and transforms source data, then loads it into the warehouse. The backend reads the resulting warehouse data to serve frontend requests.

```text
Frontend  ──HTTP──>  Backend  ──read──>  Warehouse
                                  ETL  ──write──>
```

PostGIS is the warehouse. It stores relational data and tiled raster data. Database schema changes live in versioned SQL migrations under `infra/warehouse/migrations/`, while the ETL service loads population rasters into the warehouse. CI validates database, backend, and frontend builds independently; database migration deployment is separate from application deployment because it changes persistent data.
