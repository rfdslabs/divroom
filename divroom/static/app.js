const $ = (id) => document.getElementById(id);
let deviceIp = null;

function row(html) { const li = document.createElement("li"); li.innerHTML = html; return li; }
function cap(list, max) { while (list.children.length > max) list.removeChild(list.lastChild); }

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

function esc(s) { return String(s).replace(/[<>&]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c])); }

function onEvent(ev) {
  if (ev.type === "status") {
    if (ev.error) { const s = $("status"); s.textContent = ev.error; s.classList.remove("hidden"); }
    $("pkts").textContent = (ev.packets || 0) + " pkts";
    setRunning(ev.running);
    return;
  }
  if (ev.type === "packet") {
    const packets = $("packets");
    packets.insertBefore(row(`<span class="proto-${ev.proto}">[${ev.proto}]</span> ${esc(ev.summary)}`), packets.firstChild);
    cap(packets, 200);
    for (const m of (ev.events || [])) {
      const mqtt = $("mqtt");
      mqtt.insertBefore(row(
        `<span class="dir">${esc(m.direction)}</span> ${esc(m.topic)} <span class="cmd">${esc(m.command || "")}</span>`), mqtt.firstChild);
      cap(mqtt, 200);
      if (m.command === "Sys/SetConf" && m.json && "Latitude" in m.json) {
        $("privacy").classList.remove("hidden");
        $("coords").textContent = `lat ${m.json.Latitude}, lon ${m.json.Longitude}`;
      }
    }
  }
}

function connectWs() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (e) => onEvent(JSON.parse(e.data));
  ws.onclose = () => setTimeout(connectWs, 1500);
}

function setRunning(on) {
  $("dot").className = "dot " + (on ? "on" : "off");
  $("start").disabled = on; $("stop").disabled = !on;
}

$("start").onclick = async () => {
  if (!deviceIp) return;
  $("status").classList.add("hidden");
  const r = await (await fetch("/api/capture/start", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ip: deviceIp }) })).json();
  onEvent({ type: "status", ...r });
};
$("stop").onclick = async () => {
  await fetch("/api/capture/stop", { method: "POST" });
  setRunning(false);
};

async function control(act) {
  const out = $("ctlout"); out.className = "ctlout"; out.textContent = "…";
  try {
    let r;
    if (act === "image") {
      const f = $("image").files[0];
      if (!f) { out.textContent = "pick a file first"; return; }
      const fd = new FormData(); fd.append("ip", deviceIp); fd.append("file", f);
      r = await fetch("/api/control/image", { method: "POST", body: fd });
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

loadDevice();
connectWs();
fetch("/api/capture/status").then(r => r.json()).then(s => setRunning(s.running));
