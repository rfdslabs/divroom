"""FastAPI dashboard: discover and control a Divoom Pixoo 64 on the local LAN."""
import os
import tempfile

from urllib.parse import urlparse

from fastapi import (FastAPI, UploadFile, Form, File, Body, HTTPException)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .discovery import discover
from .control import Pixoo, PixooError
from .slideshow import Slideshow
from .camera import CameraStream
from . import animate, art, camera

STATIC = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI()
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_show: Slideshow | None = None
_IDLE_SHOW = {"running": False, "year": None, "current": None, "queued": 0, "error": None}
_cam: CameraStream | None = None
_IDLE_CAM = {"running": False, "index": None, "frames_sent": 0, "fps": 0, "error": None}


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


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/discover")
def api_discover():
    return [d.__dict__ for d in discover()]


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


@app.post("/api/animate/{name}")
async def api_animate(name: str, body: dict = Body(default={})):
    opts = {k: v for k, v in body.items() if k not in ("ip", "speed")}
    try:
        frames = animate.build(name, **opts)
    except KeyError:
        raise HTTPException(404, f"unknown animation {name}")
    try:
        Pixoo(body.get("ip", "")).send_frames(frames, speed_ms=int(body.get("speed", 100)))
    except PixooError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "frames": len(frames)}


@app.get("/api/art/random")
def api_art_random(year: int = 2024):
    try:
        pack, file = art.random_piece(year)
    except Exception as e:
        raise HTTPException(502, f"16colo.rs pick failed: {e}")
    return {"pack": pack, "file": file, "year": year}


@app.post("/api/slideshow/start")
def api_show_start(body: dict = Body(...)):
    global _show
    if _show and _show.status()["running"]:
        _show.stop()
    _show = Slideshow(ip=body["ip"], year=int(body.get("year", 2024)),
                      speed=int(body.get("speed", 60)), hold=int(body.get("hold", 30)),
                      target=int(body.get("buffer", 10)))
    _show.start()
    return _show.status()


@app.post("/api/slideshow/stop")
def api_show_stop():
    if _show:
        _show.stop()
    return {"running": False}


@app.get("/api/slideshow/status")
def api_show_status():
    return _show.status() if _show else dict(_IDLE_SHOW)


@app.get("/api/camera/devices")
def api_cam_devices():
    return camera.list_devices()


@app.post("/api/camera/start")
def api_cam_start(body: dict = Body(...)):
    global _cam
    if _cam and _cam.status()["running"]:
        _cam.stop()
    _cam = CameraStream(ip=body["ip"], index=int(body.get("index", 0)),
                        fps=int(body.get("fps", 12)))
    _cam.start()
    return _cam.status()


@app.post("/api/camera/stop")
def api_cam_stop():
    if _cam:
        _cam.stop()
    return {"running": False}


@app.get("/api/camera/status")
def api_cam_status():
    return _cam.status() if _cam else dict(_IDLE_CAM)


@app.on_event("shutdown")
def _stop_show_on_shutdown():
    if _show:
        _show.stop()
    if _cam:
        _cam.stop()


@app.post("/api/art")
async def api_art(body: dict = Body(default={})):
    try:
        frames = art.build(body["pack"], body["file"],
                           frames=int(body.get("frames", 60)),
                           view=body.get("view", "x1"))
    except Exception as e:  # network / decode / missing piece
        raise HTTPException(502, f"16colo.rs fetch failed: {e}")
    try:
        Pixoo(body.get("ip", "")).send_frames(frames, speed_ms=int(body.get("speed", 100)))
    except PixooError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "frames": len(frames)}


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


app.mount("/static", StaticFiles(directory=STATIC), name="static")
