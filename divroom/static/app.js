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

loadDevice();
