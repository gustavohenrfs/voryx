from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.accounts.login import PendingLogins
from app.accounts.routes import router as accounts_router
from app.admin.routes import router as admin_router
from app.auth.routes import router as auth_router
from app.auth.security import LoginRateLimiter
from app.channels.routes import router as channels_router
from app.config import get_settings
from app.db import make_engine, make_sessionmaker
from app.deps import CSRF_HEADER, csrf_guard
from app.joins.routes import router as joins_router
from app.joins.service import ApprovalThrottle
from app.logs.routes import router as logs_router
from app.members.routes import router as members_router
from app.posts.routes import router as posts_router
from app.tg.manager import ClientManager


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
        if app.state.gateway is None:
            from app.tg.telethon_gateway import TelethonGateway

            app.state.gateway = TelethonGateway()
        app.state.manager = ClientManager(app.state.gateway, app.state.sessionmaker)
        yield
        await app.state.manager.stop()
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="Voryx API", lifespan=lifespan, dependencies=[Depends(csrf_guard)])
    app.state.sessionmaker = sessionmaker
    app.state.gateway = gateway
    app.state.login_limiter = LoginRateLimiter()
    app.state.logins = PendingLogins()
    app.state.throttle = ApprovalThrottle()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER],
    )
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(accounts_router)
    app.include_router(channels_router)
    app.include_router(joins_router)
    app.include_router(members_router)
    app.include_router(logs_router)
    app.include_router(posts_router)
    return app
