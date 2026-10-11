from __future__ import annotations

import asyncio
import io
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.service import ROOT, ScoreboardDataService, active_date
from backend.project_store import (
    MAX_IMPORT_BYTES,
    ProjectConflictError,
    ProjectStore,
    ProjectValidationError,
)
from backend.validation import TargetValidationError, load_target_inputs, validate_target
from backend.builds import BuildError, BuildStore

@asynccontextmanager
async def lifespan(app: FastAPI):
    service = ScoreboardDataService()
    app.state.data_service = service
    app.state.project_store = ProjectStore(service.data_dir)
    app.state.build_store = BuildStore(service.data_dir)
    yield
    await service.close()


app = FastAPI(
    title="Pixelboard Scoreboard Service",
    version="0.4.1",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "PUT", "POST"],
    allow_headers=["Content-Type"],
)


def service_for(app_instance: FastAPI) -> ScoreboardDataService:
    return app_instance.state.data_service


def projects_for(app_instance: FastAPI) -> ProjectStore:
    return app_instance.state.project_store


def builds_for(app_instance: FastAPI) -> BuildStore:
    return app_instance.state.build_store


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "pixelboard", "version": app.version}


@app.get("/api/v1/snapshot")
async def snapshot(
    mode: Literal["live", "demo", "replay"] = "live",
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    force: bool = False,
) -> JSONResponse:
    try:
        value = await service_for(app).get_snapshot(date or active_date(), mode=mode, force=force)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    status_code = 503 if value["source"]["freshness"] == "failed" else 200
    return JSONResponse(value, status_code=status_code)


@app.get("/api/v1/projects")
async def projects() -> list[dict[str, object]]:
    return projects_for(app).list_projects()


@app.get("/api/v1/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, object]:
    try:
        return projects_for(app).get(project_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except ProjectValidationError as error:
        raise HTTPException(status_code=400, detail=error.errors) from error


@app.put("/api/v1/projects/{project_id}")
async def save_project(project_id: str, request: Request) -> dict[str, object]:
    try:
        project = await request.json()
        if not isinstance(project, dict) or project.get("id") != project_id:
            raise ProjectValidationError(["Path id must match project.id"])
        expected_version = (project.get("meta") or {}).get("version")
        expected_version = int(expected_version) if isinstance(expected_version, (int, float)) else None
        return projects_for(app).save(project, expected_version=expected_version)
    except ProjectValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors) from error
    except ProjectConflictError as error:
        raise HTTPException(status_code=409, detail=error.current) from error


@app.get("/api/v1/projects/{project_id}/export")
async def export_project(project_id: str) -> StreamingResponse:
    try:
        filename, payload = projects_for(app).export_zip(project_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except ProjectValidationError as error:
        raise HTTPException(status_code=400, detail=error.errors) from error
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/v1/projects/import")
async def import_project(request: Request) -> dict[str, object]:
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Import exceeds 5 MB")
    payload = await request.body()
    try:
        return projects_for(app).import_zip(payload)
    except ProjectValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors) from error


@app.post("/api/v1/projects/{project_id}/validate")
async def validate_project(project_id: str, request: Request) -> dict[str, object]:
    try:
        project = projects_for(app).get(project_id)
        raw = await request.body()
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="Validation options must be an object")
        acknowledgements = payload.get("acknowledgedWarnings", [])
        if not isinstance(acknowledgements, list) or not all(isinstance(item, str) for item in acknowledgements):
            raise HTTPException(status_code=422, detail="acknowledgedWarnings must be an array of rule names")
        profile, definition, fonts_dir = load_target_inputs(
            project, bundle_dir=projects_for(app).bundle_dir(project_id)
        )
        return validate_target(
            project,
            profile,
            definition,
            fonts_dir=fonts_dir,
            acknowledged_warnings=acknowledgements,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="Validation options must be valid JSON") from error
    except (ProjectValidationError, TargetValidationError) as error:
        detail = error.errors if isinstance(error, ProjectValidationError) else str(error)
        raise HTTPException(status_code=422, detail=detail) from error


@app.post("/api/v1/projects/{project_id}/build")
async def build_project(project_id: str, request: Request) -> dict[str, object]:
    try:
        project = projects_for(app).get(project_id)
        raw = await request.body()
        payload = json.loads(raw) if raw else {}
        acknowledgements = payload.get("acknowledgedWarnings", []) if isinstance(payload, dict) else None
        if not isinstance(acknowledgements, list) or not all(isinstance(item, str) for item in acknowledgements):
            raise HTTPException(status_code=422, detail="acknowledgedWarnings must be an array of rule names")
        return builds_for(app).build(
            project,
            acknowledged_warnings=acknowledgements,
            bundle_dir=projects_for(app).bundle_dir(project_id),
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="Build options must be valid JSON") from error
    except (ProjectValidationError, TargetValidationError) as error:
        detail = error.errors if isinstance(error, ProjectValidationError) else str(error)
        raise HTTPException(status_code=422, detail=detail) from error
    except BuildError as error:
        raise HTTPException(status_code=409, detail={"stage": error.stage, "message": str(error), "logs": error.logs}) from error


@app.get("/api/v1/builds/{build_id}")
async def get_build(build_id: str) -> dict[str, object]:
    try:
        return builds_for(app).result(build_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Build not found") from error


@app.get("/api/v1/builds/{build_id}/artifact")
async def download_build(build_id: str) -> FileResponse:
    try:
        filename, path = builds_for(app).artifact(build_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Build not found") from error
    return FileResponse(path, filename=filename, media_type="application/gzip")


@app.websocket("/api/v1/stream")
async def stream(websocket: WebSocket) -> None:
    await websocket.accept()
    mode = websocket.query_params.get("mode", "live")
    if mode not in {"live", "demo", "replay"}:
        await websocket.close(code=1008, reason="Invalid data mode")
        return
    requested_date = websocket.query_params.get("date") or active_date()
    try:
        while True:
            value = await service_for(app).get_snapshot(requested_date, mode=mode)  # type: ignore[arg-type]
            await websocket.send_json(value)
            refresh = value["source"]["refreshSec"]
            await asyncio.sleep(max(1, int(refresh if refresh else 300)))
    except WebSocketDisconnect:
        return
    except ValueError:
        await websocket.close(code=1008, reason="Invalid date")


DIST = Path(ROOT, "dist")
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="studio")
