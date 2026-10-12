"""FastAPI dashboard: discovery, capture toggle, control, live WebSocket feed."""
import asyncio
import os
import tempfile

from urllib.parse import urlparse

from fastapi import (FastAPI, WebSocket, WebSocketDisconnect, UploadFile,
                     Form, File, Body, HTTPException)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .discovery import discover
from .capture import Capture
from .control import Pixoo, PixooError

GATEWAY = os.environ.get("PIXOO_GW", "192.168.4.1")
IFACE = os.environ.get("PIXOO_IFACE", "en0")
STATIC = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI()
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _origin_ok(origin: str | None) -> bool:
    # No Origin (curl, same-process tools) is allowed; a browser cross-site
    # request carries a foreign Origin and is rejected. Any port on localhost ok.
    if not origin:
        return True
    try:
        return urlparse(origin).hostname in _LOCAL_HOSTS
    except Exception:
        return False


@app.middleware("http")
async def _origin_guard(request, call_next):
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if not _origin_ok(request.headers.get("origin")):
            return JSONResponse(status_code=403, content={"detail": "bad origin"})
    return await call_next(request)


_clients: set[WebSocket] = set()
_capture: Capture | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _broadcast(event: dict):
    # Called from the capture reader thread; hop onto the event loop.
    if _loop is None:
        return
    for ws in list(_clients):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, event), _loop)


async def _safe_send(ws: WebSocket, event: dict):
    try:
        await ws.send_json(event)
    except Exception:
        _clients.discard(ws)


@app.on_event("startup")
async def _startup():
    global _loop
    _loop = asyncio.get_running_loop()


@app.on_event("shutdown")
async def _shutdown():
    if _capture:
        _capture.stop()


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/discover")
def api_discover():
    return [d.__dict__ for d in discover()]


@app.get("/api/capture/status")
def api_status():
    return _capture.status() if _capture else {"running": False, "packets": 0, "error": None}


@app.post("/api/capture/start")
def api_start(body: dict = Body(...)):
    global _capture
    ip = body["ip"]
    if _capture and _capture.status()["running"]:
        return _capture.status()
    _capture = Capture(ip=ip, gateway=GATEWAY, iface=IFACE, on_event=_broadcast)
    _capture.start()
    return _capture.status()


@app.post("/api/capture/stop")
def api_stop():
    if _capture:
        _capture.stop()
    return {"running": False}


# Declared before the generic /api/control/{action} so the literal path wins.
@app.post("/api/control/image")
async def api_control_image(ip: str = Form(...), file: UploadFile = File(...)):
    from PIL import Image, UnidentifiedImageError
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(400, "file too large")
    suffix = os.path.splitext(file.filename or "")[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data); tmp.flush(); tmp.close()
        Image.open(tmp.name).verify()  # raises if not an image
        count = Pixoo(ip).image(tmp.name)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "not a valid image")
    except PixooError as e:
        raise HTTPException(502, str(e))
    finally:
        os.unlink(tmp.name)
    return {"ok": True, "frames": count}


@app.post("/api/control/{action}")
async def api_control(action: str, body: dict = Body(default={})):
    dev = Pixoo(body.get("ip", ""))
    try:
        if action == "color":
            dev.color(body["hex"])
        elif action == "text":
            dev.text(body["msg"], color=body.get("color", "#FFFFFF"), y=body.get("y", 28))
        elif action == "brightness":
            dev.brightness(body["level"])
        elif action == "channel":
            dev.channel(body["name"])
        elif action == "screen":
            dev.screen(bool(body["on"]))
        elif action == "raw":
            return dev.cmd(body["command"], **body.get("params", {}))
        else:
            raise HTTPException(404, f"unknown action {action}")
    except PixooError as e:
        raise HTTPException(502, str(e))
    return {"ok": True}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    if not _origin_ok(websocket.headers.get("origin")):
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()
    _clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive
    except WebSocketDisconnect:
        _clients.discard(websocket)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
