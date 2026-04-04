import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import files, reveal, upload
from app.sessions import _sweep_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task that sweeps expired session tokens every 10 s
    task = asyncio.create_task(_sweep_loop())
    yield
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
app.include_router(upload.router, prefix="/api")
app.include_router(files.router,  prefix="/api")
app.include_router(reveal.router, prefix="/api")

# Serve frontend from /static directory at root
app.mount("/", StaticFiles(directory="static", html=True), name="static")
