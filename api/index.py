from backend.app.main import app

# Vercel expects a handler named "handler" for Python functions.
# FastAPI's ASGI app can be exposed directly.
handler = app
