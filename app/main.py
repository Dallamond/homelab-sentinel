"""
Punto de entrada FastAPI. Sirve la API bajo /api y el dashboard estático
bajo /. El comportamiento depende de ROLE:

- standalone: monta DB, API, scheduler de resúmenes Y arranca los
  collectors locales (journald/Docker) directamente en este proceso.
- server: monta DB, API y scheduler, pero espera recibir eventos vía
  POST /api/ingest desde agentes remotos.
- agent: no expone dashboard ni DB; usa `python -m app.agent` en su lugar
  (ver agent.py), este main.py no debería usarse en ese rol.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.config import BASE_DIR, settings
from app.db.session import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Base de datos inicializada (%s)", settings.database_url)

    scheduler = None
    if settings.role in ("server", "standalone") and settings.summarizer_backend != "none":
        from app.scheduler import start_scheduler
        scheduler = start_scheduler()

    if settings.role == "standalone":
        from app.local_ingest import start_local_ingest
        await start_local_ingest()

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="homelab-sentinel", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

frontend_dir = BASE_DIR / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
