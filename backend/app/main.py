from fastapi import FastAPI

from app.core.health import health_payload
from app.core.logging_setup import setup_logging
from app.middleware.request_id import RequestIdMiddleware

setup_logging()

app = FastAPI(title="糖安食助", version="0.1.0")
app.add_middleware(RequestIdMiddleware)


@app.get("/api/v1/health")
def health() -> dict[str, object]:
    return health_payload()
