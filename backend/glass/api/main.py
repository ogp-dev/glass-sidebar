# Production ASGI entry point.
# Run with: uvicorn glass.api.main:app
# Tests use create_app() directly from glass.api.app.
from glass.api.app import create_app

app = create_app()
