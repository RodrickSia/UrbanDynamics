# Initial architecture

The frontend calls the backend API. The ETL service periodically extracts and transforms source data, then loads it into the warehouse. The backend reads the resulting warehouse data to serve frontend requests.

```text
Frontend  ──HTTP──>  Backend  ──read──>  Warehouse
                                  ETL  ──write──>
```

The warehouse engine, ETL framework, and scheduling mechanism are open decisions. Keep their configuration behind environment variables and service boundaries so they can be selected without moving application code.
