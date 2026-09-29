# Backend

FastAPI service entry point: `app.main:app`. Add API routers under `app/api/`, shared configuration under `app/core/`, and service logic under `app/services/` as the API grows. The backend will read from the warehouse; configure credentials through environment variables rather than source files.
