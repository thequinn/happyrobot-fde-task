from __future__ import annotations

import logging

from fastapi import FastAPI

from .compat import ensure_httpx_proxy_support
from .routes import call_logs_router, loads_router, metrics_router

# from .routes import negotiation_router


# Configure root logger once so the entire app emits consistent structured logs.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure httpx respects proxy settings when HappyRobot routes traffic through Ngrok.
ensure_httpx_proxy_support()


app = FastAPI(
    title="HappyRobot Agent API",
    description=(
        "FastAPI service that powers happyrobot.ai agents with endpoints for "
        "load discovery and negotiation workflows."
    ),
    version="0.1.0",
)

# Register all feature routers so clients get loads, negotiations, metrics and call logs.
app.include_router(loads_router)
# app.include_router(negotiation_router)

app.include_router(call_logs_router)
app.include_router(metrics_router)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
