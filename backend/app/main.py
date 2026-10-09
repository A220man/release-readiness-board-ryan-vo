"""FastAPI application factory for Release Readiness Board."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI,Depends
from fastapi.responses import JSONResponse
from app.core.errors import AppError
from app.core.session_config import Settings as SessionSettings,validate_settings,ensure_db_dir
from app.core.session_db import Database
from app.core.session_auth import OIDCClient
from app.core.body_limit import BodyLimit
from app.core.database import _get_db_path
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import get_database_manager, reset_database_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB on startup, cleanup on shutdown."""
    settings = get_settings()
    settings.check_demo_safety()

    if settings.DEMO_MODE:
        logger.info("Starting in DEMO MODE (localhost only)")

    validate_settings(app.state.settings)
    ensure_db_dir(app.state.settings.database_path)
    app.state.db=Database(app.state.settings.database_path)
    manager = await get_database_manager()
    await manager.init_db()
    logger.info("Database initialized")

    yield

    await reset_database_manager()
    app.state.db.close()
    logger.info("Database connection closed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Release Readiness Board",
        description=(
            "Release readiness tracker with deterministic risk scoring, "
            "NLP blocker classification, and auditable state transitions."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    session_settings=SessionSettings(environment=settings.APP_ENV,database_path=_get_db_path(settings),
        auth_mode='demo' if settings.DEMO_MODE else 'oidc',bind_host=settings.DEMO_BIND_HOST,
        cookie_secure=settings.COOKIE_SECURE,frontend_url=settings.FRONTEND_URL,
        oidc_discovery_url=settings.OIDC_ISSUER_URL.rstrip('/')+'/.well-known/openid-configuration' if settings.OIDC_ISSUER_URL else '',
        oidc_client_id=settings.OIDC_CLIENT_ID,oidc_client_secret=settings.OIDC_CLIENT_SECRET,
        oidc_redirect_uri=settings.OIDC_REDIRECT_URI,oidc_role_claim=settings.OIDC_ROLE_CLAIM)
    app.state.settings=session_settings
    app.state.oidc=OIDCClient(session_settings)
    app.add_middleware(BodyLimit,limit=5*1024*1024)
    @app.exception_handler(AppError)
    async def auth_error(request,exc):
        return JSONResponse({'error':{'code':exc.code,'message':exc.message}},status_code=exc.status)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.releases import router as releases_router
    from app.api.criteria import router as criteria_router
    from app.api.blockers import router as blockers_router
    from app.api.approvals import router as approvals_router
    from app.api.audit import router as audit_router
    from app.api.auth_routes import router as auth_router
    from app.api.llm_routes import router as llm_router

    app.include_router(releases_router)
    app.include_router(criteria_router)
    app.include_router(blockers_router)
    app.include_router(approvals_router)
    app.include_router(audit_router)
    app.include_router(auth_router)
    app.include_router(llm_router)

    @app.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": "1.0.0"}

    from app.core.auth import require_role
    @app.get('/api/evaluation')
    async def evaluation(user=Depends(require_role('viewer'))):
        from app.services.evaluation import evaluate
        return evaluate()
    return app


app = create_app()
