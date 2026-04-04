"""
LangGraph supervisor: routes files to the correct analysis crew by MIME type.
"""
from __future__ import annotations

from typing import TypedDict

import time

from langgraph.graph import END, START, StateGraph

from app.logger import get_logger

log = get_logger("orchestrator")


# ── Shared state ──────────────────────────────────────────────────────────────

class AnalysisState(TypedDict):
    file_id:   str
    mime_type: str
    raw_bytes: bytes
    result:    dict


# ── Routing ───────────────────────────────────────────────────────────────────

def _route(state: AnalysisState) -> str:
    mime = state["mime_type"]
    if mime.startswith("video/"):  return "video"
    if mime.startswith("audio/"):  return "audio"
    if mime.startswith("image/"):  return "image"
    return "text"


# ── Node factory ──────────────────────────────────────────────────────────────

def _make_node(crew_name: str, run_fn):
    def node(state: AnalysisState) -> dict:
        fid = state["file_id"][:8]
        log.info(f"[{fid}] Running {crew_name}")
        try:
            result = run_fn(state["raw_bytes"], state["mime_type"], state["file_id"])
            log.info(f"[{fid}] {crew_name} complete")
            return {"result": result}
        except Exception as exc:
            log.error(f"[{fid}] {crew_name} failed: {exc}", exc_info=True)
            return {"result": {"error": str(exc)}}
    return node


# ── Graph ─────────────────────────────────────────────────────────────────────

_pipeline = None


def _build():
    from app.agents.audio_crew import run as audio_run
    from app.agents.image_crew import run as image_run
    from app.agents.text_crew  import run as text_run
    from app.agents.video_crew import run as video_run

    g = StateGraph(AnalysisState)
    g.add_node("text",  _make_node("text_crew",  text_run))
    g.add_node("audio", _make_node("audio_crew", audio_run))
    g.add_node("image", _make_node("image_crew", image_run))
    g.add_node("video", _make_node("video_crew", video_run))

    g.add_conditional_edges(START, _route, {
        "text":  "text",
        "audio": "audio",
        "image": "image",
        "video": "video",
    })
    for node in ("text", "audio", "image", "video"):
        g.add_edge(node, END)

    return g.compile()


def run_analysis(file_id: str, raw_bytes: bytes, mime_type: str) -> dict:
    global _pipeline
    if _pipeline is None:
        log.info("Building LangGraph analysis pipeline...")
        _pipeline = _build()
        log.info("Pipeline ready")

    fid  = file_id[:8]
    crew = _route({"file_id": file_id, "mime_type": mime_type, "raw_bytes": b"", "result": {}})
    log.info(f"[{fid}] Supervisor routing {mime_type!r} → {crew}_crew")
    t0   = time.perf_counter()

    final = _pipeline.invoke({
        "file_id":   file_id,
        "mime_type": mime_type,
        "raw_bytes": raw_bytes,
        "result":    {},
    })
    ms = (time.perf_counter() - t0) * 1000
    log.info(f"[{fid}] Pipeline complete in {ms:.0f}ms")
    return final["result"]
