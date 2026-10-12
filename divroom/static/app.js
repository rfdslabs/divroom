const $ = (id) => document.getElementById(id);
let deviceIp = null;

async function loadDevice() {
  try {
    const devs = await (await fetch("/api/discover")).json();
    if (devs.length) {
      deviceIp = devs[0].ip;
      $("device").textContent = `${devs[0].name}  ${devs[0].ip}  (id ${devs[0].device_id})`;
    } else {
      $("device").textContent = "Pixoo not found on this network";
    }
  } catch { $("device").textContent = "discovery failed"; }
}

async function control(act) {
  const out = $("ctlout"); out.className = "ctlout"; out.textContent = "…";
  try {
    let r;
    if (act === "image") {
      const f = $("image").files[0];
      if (!f) { out.textContent = "pick a file first"; return; }
      const fd = new FormData(); fd.append("ip", deviceIp); fd.append("file", f);
      r = await fetch("/api/control/image", { method: "POST", body: fd });
    } else if (act === "animate") {
      const name = $("anim").value;
      const body = { ip: deviceIp, frames: 30, speed: +$("speed").value,
                     a: $("color").value, b: $("color2").value, color: $("color").value };
      r = await fetch(`/api/animate/${name}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } else if (act === "art") {
      const pack = $("artpack").value.trim(), file = $("artfile").value.trim();
      if (!pack || !file) { out.textContent = "enter a pack and a file"; return; }
      const body = { ip: deviceIp, pack, file, frames: 60, speed: +$("speed").value };
      r = await fetch("/api/art", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } else if (act === "gradient") {
      const body = { ip: deviceIp, a: $("color").value, b: $("color2").value, angle: 0 };
      r = await fetch("/api/animate/gradient", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } else {
      const body = { ip: deviceIp };
      if (act === "color") body.hex = $("color").value.slice(1);
      if (act === "text") body.msg = $("text").value;
      if (act === "brightness") body.level = +$("bright").value;
      if (act === "channel") body.name = $("channel").value;
      if (act === "screen") body.on = $("screen").value === "on";
      if (act === "raw") { const j = JSON.parse($("raw").value); body.command = j.Command; body.params = j; delete body.params.Command; }
      r = await fetch(`/api/control/${act}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    }
    const data = await r.json();
    if (!r.ok) { out.className = "ctlout err"; out.textContent = data.detail || ("error " + r.status); }
    else out.textContent = "ok " + JSON.stringify(data);
  } catch (e) { out.className = "ctlout err"; out.textContent = String(e); }
}
document.querySelectorAll("[data-act]").forEach(b => b.onclick = () => control(b.dataset.act));

// --- random slideshow: server-side, with a prefetch buffer (10 ahead)
let showPoll = null;

function setShowRunning(on) {
  $("startshow").disabled = on; $("stopshow").disabled = !on;
}

async function pollShow() {
  try {
    const s = await (await fetch("/api/slideshow/status")).json();
    setShowRunning(s.running);
    if (s.running) {
      const cur = s.current ? `▶ ${s.current.pack} / ${s.current.file}` : "buffering…";
      $("showstat").textContent = `${cur}  ·  ${s.queued} ready` + (s.error ? `  ·  ${s.error}` : "");
    }
  } catch {}
}

$("startshow").onclick = async () => {
  if (!deviceIp) return;
  setShowRunning(true);
  $("showstat").textContent = "starting · buffering 10 pieces…";
  await fetch("/api/slideshow/start", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ip: deviceIp, year: +$("year").value || 2024, speed: +$("speed").value }) });
  if (!showPoll) showPoll = setInterval(pollShow, 2000);
  pollShow();
};
$("stopshow").onclick = async () => {
  await fetch("/api/slideshow/stop", { method: "POST" });
  clearInterval(showPoll); showPoll = null;
  setShowRunning(false);
  $("showstat").textContent = "stopped";
};

loadDevice();
// reflect an already-running slideshow (it lives in the server, not this tab)
fetch("/api/slideshow/status").then(r => r.json()).then(s => {
  if (s.running) { setShowRunning(true); showPoll = setInterval(pollShow, 2000); pollShow(); }
});

// --- live camera → panel (server-side, ffmpeg avfoundation)
let camPoll = null;

function setCamRunning(on) { $("camstart").disabled = on; $("camstop").disabled = !on; }

async function loadCams() {
  try {
    const devs = await (await fetch("/api/camera/devices")).json();
    const sel = $("cam"); sel.innerHTML = "";
    devs.forEach(d => {
      const o = document.createElement("option");
      o.value = d.index; o.textContent = `[${d.index}] ${d.name}`; sel.appendChild(o);
    });
    if (!devs.length) { sel.innerHTML = "<option value='0'>camera 0</option>"; }
  } catch { $("cam").innerHTML = "<option value='0'>camera 0</option>"; }
}

async function pollCam() {
  try {
    const s = await (await fetch("/api/camera/status")).json();
    setCamRunning(s.running);
    if (s.running) {
      $("camstat").textContent = s.error ? ("⚠ " + s.error) : `● live · ${s.frames_sent} frames · ${s.fps} fps`;
    }
  } catch {}
}

$("camstart").onclick = async () => {
  if (!deviceIp) return;
  setCamRunning(true);
  $("camstat").textContent = "starting camera… (approve the macOS prompt if it appears)";
  await fetch("/api/camera/start", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ip: deviceIp, index: +$("cam").value || 0, fps: 12 }) });
  if (!camPoll) camPoll = setInterval(pollCam, 1500);
  pollCam();
};
$("camstop").onclick = async () => {
  await fetch("/api/camera/stop", { method: "POST" });
  clearInterval(camPoll); camPoll = null;
  setCamRunning(false); $("camstat").textContent = "stopped";
};

loadCams();
fetch("/api/camera/status").then(r => r.json()).then(s => {
  if (s.running) { setCamRunning(true); camPoll = setInterval(pollCam, 1500); pollCam(); }
});
