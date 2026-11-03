from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.routes import router as admin_router
from app.auth.routes import router as auth_router
from app.auth.security import LoginRateLimiter
from app.config import get_settings
from app.db import make_engine, make_sessionmaker
from app.deps import CSRF_HEADER, csrf_guard


def create_app(gateway=None, start_background: bool | None = None, sessionmaker=None) -> FastAPI:
    settings = get_settings()
    if start_background is None:
        start_background = settings.start_background

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = None
        if app.state.sessionmaker is None:
            engine = make_engine(settings.database_url, pool_pre_ping=True)
            app.state.sessionmaker = make_sessionmaker(engine)
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="Voryx API", lifespan=lifespan, dependencies=[Depends(csrf_guard)])
    app.state.sessionmaker = sessionmaker
    app.state.gateway = gateway
    app.state.login_limiter = LoginRateLimiter()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER],
    )
    app.include_router(auth_router)
    app.include_router(admin_router)
    return app
