const BACKEND_URL = "/chat";
const $ = (id) => document.getElementById(id);

let state = {
  img: null,
  profile: { age: 24, gender: "Transgender", done: false },
  loc: { lat: 26.9124, lon: 75.7873 },
  logs: [],
  reminders: JSON.parse(localStorage.getItem("med_rem") || "[]")
};

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

// Modal Toggle
const toggle = (el, show) => el.style.display = show ? "flex" : "none";
$("nav-open-chat").onclick = $("hero-chat-btn").onclick = () => {
  toggle($("chat-modal"), true);
  if (!state.profile.done) renderProfile();
  $("user-input").focus();
};
$("close-chat").onclick = () => { toggle($("chat-modal"), false); window.speechSynthesis.cancel(); };
$("open-sos-btn").onclick = $("hero-sos-btn").onclick = () => { toggle($("sos-modal"), true); getGPS(); };
$("close-sos").onclick = () => toggle($("sos-modal"), false);
$("hero-reminder-btn").onclick = () => $("reminders").scrollIntoView({ behavior: "smooth" });

// Fast GPS
function getGPS(cb) {
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      p => { state.loc = { lat: p.coords.latitude, lon: p.coords.longitude }; if (cb) cb(); },
      () => { if (cb) cb(); },
      { timeout: 3500 }
    );
  } else if (cb) cb();
}

// WhatsApp SOS
$("send-wa-sos").onclick = () => {
  const p = $("sos-phone").value.trim().replace(/\D/g, "");
  if (!p) return alert("Enter valid phone number with country code.");
  $("send-wa-sos").innerText = "Getting GPS...";
  getGPS(() => {
    $("send-wa-sos").innerText = "Send Live GPS";
    window.location.href = `https://api.whatsapp.com/send?phone=${p}&text=${encodeURIComponent(`🚨 EMERGENCY MEDICAL SOS ALERT!\nLive Location: https://maps.google.com/?q=${state.loc.lat},${state.loc.lon}\nSent via MediNova AI.`)}`;
  });
};

// Hospitals Locator
$("find-hospitals-btn").onclick = () => {
  $("loc-status-text").innerText = "Locating via GPS...";
  getGPS(() => {
    $("loc-status-text").innerText = `GPS Active ✅ (${state.loc.lat.toFixed(2)}°, ${state.loc.lon.toFixed(2)}°)`;
    $("hospitals-container").innerHTML = `
      <div class="hospital-card">
        <div class="h-header"><h3>Emergency Trauma & ICU</h3><span class="h-badge">24/7 Open</span></div>
        <p class="h-desc"><i class="fa-solid fa-location-dot"></i> Emergency Care (~1.2 km)</p>
        <a href="https://www.google.com/maps/search/emergency+hospital+near+me/@${state.loc.lat},${state.loc.lon},14z" target="_blank" class="h-btn">Open Google Maps Route</a>
      </div>
      <div class="hospital-card">
        <div class="h-header"><h3>City Multi-Specialty Hospital</h3><span class="h-badge">Ambulance 102</span></div>
        <p class="h-desc"><i class="fa-solid fa-location-dot"></i> OPD & Emergency (~2.5 km)</p>
        <a href="https://www.google.com/maps/search/hospitals+near+me/@${state.loc.lat},${state.loc.lon},14z" target="_blank" class="h-btn">Open Google Maps Route</a>
      </div>`;
  });
};

// Medicine Reminders
function renderReminders() {
  $("reminders-container").innerHTML = state.reminders.length
    ? state.reminders.map((r, i) => `
      <div class="schedule-pill-item">
        <span><i class="fa-solid fa-pills" style="color:var(--primary)"></i> <strong>${r.name}</strong> at <strong>${r.time}</strong></span>
        <button onclick="delRem(${i})" style="border:none;background:none;color:var(--danger);cursor:pointer;"><i class="fa-solid fa-trash"></i></button>
      </div>`).join("")
    : '<p style="color:var(--text-muted);font-size:0.88rem;">No active schedules yet.</p>';
}
window.delRem = (i) => { state.reminders.splice(i, 1); localStorage.setItem("med_rem", JSON.stringify(state.reminders)); renderReminders(); };

$("web-save-reminder-btn").onclick = () => {
  const name = $("web-med-name").value.trim(), time = $("web-med-time").value;
  if (!name || !time) return alert("Enter medicine name and time.");
  if ("Notification" in window) Notification.requestPermission();

  const [h, m] = time.split(":"), now = new Date(), target = new Date();
  target.setHours(h, m, 0, 0);
  if (target < now) target.setDate(target.getDate() + 1);
  const delayMs = target.getTime() - now.getTime();

  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({ type: "SCHEDULE_PILL", name, delayMs });
  }

  state.reminders.push({ name, time });
  localStorage.setItem("med_rem", JSON.stringify(state.reminders));
  renderReminders();
  $("web-med-name").value = $("web-med-time").value = "";
  alert(`✅ Reminder activated for "${name}" at ${time}.`);
};
renderReminders();

setInterval(() => {
  const cur = `${String(new Date().getHours()).padStart(2, "0")}:${String(new Date().getMinutes()).padStart(2, "0")}`;
  state.reminders.forEach(r => {
    if (r.time === cur && !r.alerted) {
      alert(`⏰ MEDINOVA REMINDER!\nTime to take: ${r.name}`);
      r.alerted = true;
      setTimeout(() => r.alerted = false, 65000);
    }
  });
}, 10000);

// Camera
let stream = null;
$("open-camera-btn").onclick = async () => {
  try {
    toggle($("camera-modal"), true);
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    $("webcam-video").srcObject = stream;
  } catch (e) { alert("Camera permission required."); toggle($("camera-modal"), false); }
};
$("close-camera-btn").onclick = () => { if (stream) stream.getTracks().forEach(t => t.stop()); toggle($("camera-modal"), false); };
$("snap-photo-btn").onclick = () => {
  const c = $("webcam-canvas"), v = $("webcam-video");
  c.width = v.videoWidth || 640; c.height = v.videoHeight || 480;
  c.getContext("2d").drawImage(v, 0, 0);
  state.img = c.toDataURL("image/jpeg", 0.85);
  $("image-preview").src = state.img;
  toggle($("image-preview-container"), true);
  $("close-camera-btn").click();
};

$("image-upload").onchange = (e) => {
  const f = e.target.files[0]; if (!f) return;
  const r = new FileReader();
  r.onload = (evt) => { state.img = evt.target.result; $("image-preview").src = state.img; toggle($("image-preview-container"), true); };
  r.readAsDataURL(f);
};
$("remove-img-btn").onclick = () => { state.img = null; $("image-upload").value = ""; toggle($("image-preview-container"), false); };

// Profile Intake
function renderProfile() {
  $("chat-box").innerHTML = `
    <div class="bubble bot"><p>Namaste! 🙏 I am <strong>Dr. MediNova AI</strong>. Please select profile:</p>
      <div class="intake-card"><div class="intake-row">
        <select id="p-gender" class="intake-select">
          <option value="Male">Male (पुरुष)</option>
          <option value="Female">Female (महिला)</option>
          <option value="Transgender" selected>Transgender (ट्रांसजेंडर)</option>
        </select>
        <input type="number" id="p-age" class="intake-input" value="24" min="1" max="110">
      </div><button id="p-save" class="intake-submit-btn">Save Profile</button></div>
    </div>`;
  $("p-save").onclick = () => {
    state.profile = { age: $("p-age").value || 24, gender: $("p-gender").value, done: true };
    $("chat-box").innerHTML = "";
    append("bot", `✅ <strong>Profile Saved!</strong> (${state.profile.gender}, ${state.profile.age} yrs)<br>Aap symptoms likhein ya report/medicine scan karein.`);
  };
}

// Clean Medical Formatter (Zero Junk)
function format(txt) {
  return txt.split("\n").map(l => {
    l = l.trim(); if (!l) return "";
    if (l.includes("Overview") || l.includes("Causes") || l.includes("Remedies") || l.includes("Medicines") || l.includes("Doctor"))
      return `<div class="chat-section-header">${l.replace(/[*#]/g, "")}</div>`;
    if (l.includes("?")) return `<div class="chat-followup-box">${l.replace(/[*#]/g, "")}</div>`;
    return `<p style="margin-bottom:3px">${l.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")}</p>`;
  }).join("");
}

function append(sender, txt, img, triage) {
  const d = document.createElement("div"); d.className = `bubble ${sender}`;
  let html = triage ? `<div class="triage-badge triage-${triage.toLowerCase()}">Triage: ${triage}</div>` : "";
  if (img) html += `<img src="${img}" style="max-width:180px;border-radius:8px;display:block;margin-bottom:5px;">`;
  html += sender === "bot" ? format(txt) : `<p>${txt}</p>`;
  d.innerHTML = html;
  $("chat-box").appendChild(d);
  $("chat-box").scrollTop = $("chat-box").scrollHeight;
}

// Send Query
async function send() {
  const msg = $("user-input").value.trim(), img = state.img;
  if (!msg && !img) return;
  append("user", msg || "Scanning medical image...", img);
  $("user-input").value = ""; state.img = null; toggle($("image-preview-container"), false);

  const loader = document.createElement("div"); loader.className = "bubble bot doctor-thinking";
  loader.innerHTML = `<span class="doctor-avatar-anim">👨‍⚕️</span><span>Dr. MediNova is reviewing...</span>`;
  $("chat-box").appendChild(loader);

  try {
    const res = await fetch(BACKEND_URL, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: msg,
        language: $("language-select").value,
        image_data: img,
        age: state.profile.age,
        gender: state.profile.gender,
        latitude: state.loc.lat,
        longitude: state.loc.lon
      })
    });
    const d = await res.json();
    loader.remove();
    append("bot", d.reply, null, d.triage);
    state.logs.push({ q: msg || "Scan", a: d.reply });
  } catch (e) {
    loader.remove();
    append("bot", "⚠️ Network error. Please try again.");
  }
}

$("send-btn").onclick = send;
$("user-input").onkeypress = (e) => { if (e.key === "Enter") send(); };
document.querySelectorAll(".chip").forEach(c => c.onclick = () => { $("user-input").value = c.getAttribute("data-q"); send(); });

// PDF Summary Download
$("download-pdf-btn").onclick = () => {
  if (!state.logs.length) return alert("Complete a consultation first.");
  const doc = new window.jspdf.jsPDF();
  doc.text("MEDINOVA CLINICAL SUMMARY", 14, 15);
  doc.setFontSize(10);
  doc.text(`Patient: ${state.profile.gender}, ${state.profile.age} Yrs | Date: ${new Date().toLocaleDateString()}`, 14, 22);
  let y = 30;
  state.logs.forEach(l => {
    doc.text(`Q: ${l.q}`, 14, y); y += 6;
    const split = doc.splitTextToSize(l.a.replace(/[*#]/g, ""), 180);
    doc.text(split, 14, y); y += split.length * 5 + 4;
  });
  doc.save("MediNova_Summary.pdf");
};
