import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.logger import get_logger, setup_logging
from app.routers import analysis, files, reveal, upload
from app.sessions import _sweep_loop

setup_logging()
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task that sweeps expired session tokens every 10 s
    log.info("Application starting up — session sweep loop starting")
    task = asyncio.create_task(_sweep_loop())
    yield
    log.info("Application shutting down")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Encrypted Multimedia Reveal",
    description="Privacy-obfuscation system: content encrypted at rest, decrypted just-in-time.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes — registered before static mount so they take precedence
app.include_router(upload.router,   prefix="/api")
app.include_router(files.router,    prefix="/api")
app.include_router(reveal.router,   prefix="/api")
app.include_router(analysis.router, prefix="/api")

# Serve frontend from /static directory at root
app.mount("/", StaticFiles(directory="static", html=True), name="static")
