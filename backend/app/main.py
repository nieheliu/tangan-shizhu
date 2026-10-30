from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.profile import router as profile_router
from app.core.health import health_payload
from app.core.logging_setup import setup_logging
from app.middleware.request_id import RequestIdMiddleware
from app.services.auth import AuthError
from app.services.profile import ProfileError

setup_logging()

app = FastAPI(title="糖安食助", version="0.1.0")
app.add_middleware(RequestIdMiddleware)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")


@app.exception_handler(AuthError)
async def handle_auth_error(_request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


@app.exception_handler(ProfileError)
async def handle_profile_error(_request: Request, exc: ProfileError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


@app.get("/api/v1/health")
def health() -> dict[str, object]:
    return health_payload()
