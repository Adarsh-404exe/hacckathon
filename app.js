const BACKEND_URL = "http://127.0.0.1:8000/chat";

// UI Elements
const chatModal = document.getElementById("chat-modal");
const navOpenChat = document.getElementById("nav-open-chat");
const heroChatBtn = document.getElementById("hero-chat-btn");
const closeChat = document.getElementById("close-chat");

const sosModal = document.getElementById("sos-modal");
const openSosBtn = document.getElementById("open-sos-btn");
const heroSosBtn = document.getElementById("hero-sos-btn");
const closeSos = document.getElementById("close-sos");
const sendWaSos = document.getElementById("send-wa-sos");
const sosPhone = document.getElementById("sos-phone");

// Reminder Elements (Webpage Section)
const heroReminderBtn = document.getElementById("hero-reminder-btn");
const webMedName = document.getElementById("web-med-name");
const webMedTime = document.getElementById("web-med-time");
const webSaveReminderBtn = document.getElementById("web-save-reminder-btn");
const remindersContainer = document.getElementById("reminders-container");
const downloadPdfBtn = document.getElementById("download-pdf-btn");

// Camera Elements
const cameraModal = document.getElementById("camera-modal");
const openCameraBtn = document.getElementById("open-camera-btn");
const closeCameraBtn = document.getElementById("close-camera-btn");
const snapPhotoBtn = document.getElementById("snap-photo-btn");
const webcamVideo = document.getElementById("webcam-video");
const webcamCanvas = document.getElementById("webcam-canvas");
let mediaStream = null;

const chatBox = document.getElementById("chat-box");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const voiceBtn = document.getElementById("voice-btn");
const muteBtn = document.getElementById("mute-btn");
const langSelect = document.getElementById("language-select");

const symptomSuggestionsBar = document.getElementById("symptom-suggestions");
const imageUpload = document.getElementById("image-upload");
const imagePreviewContainer = document.getElementById("image-preview-container");
const imagePreview = document.getElementById("image-preview");
const removeImgBtn = document.getElementById("remove-img-btn");

const findHospitalsBtn = document.getElementById("find-hospitals-btn");
const hospitalsContainer = document.getElementById("hospitals-container");
const locStatusText = document.getElementById("loc-status-text");

// State
let isVoiceMuted = false;
let currentBase64Image = null;
let userProfile = { age: 24, gender: "Male", completed: false };
let userLocation = { latitude: null, longitude: null };
let consultationLogs = [];
let savedReminders = [];

// Autocomplete Dictionary
const COMMON_SUGGESTIONS = [
  "High Fever & Chills",
  "Fever with Joint Pain",
  "Severe Headache / Migraine",
  "Chest Pain & Shortness of Breath",
  "Stomach Pain & Cramps",
  "Acid Reflux & Heartburn",
  "Skin Rash & Itching",
  "Blood Test: Platelets & Hemoglobin",
  "Lab Report: High Blood Sugar / HbA1c",
  "CBC Blood Test Interpretation",
  "Recovery Diet Chart for Dengue",
  "Diabetic Diet Chart (Veg)",
  "Diet for High Blood Pressure & Heart Care",
  "Diet for Celiac Disease (Gluten Free)"
];

// Open / Close Modals
function openChat() {
  chatModal.style.display = "flex";
  if (!userProfile.completed) {
    renderIntakeWelcome();
  }
  userInput.focus();
}

function hideChat() {
  chatModal.style.display = "none";
  window.speechSynthesis.cancel();
}

navOpenChat.addEventListener("click", openChat);
heroChatBtn.addEventListener("click", openChat);
closeChat.addEventListener("click", hideChat);

if (heroReminderBtn) {
  heroReminderBtn.addEventListener("click", () => {
    document.getElementById("reminders").scrollIntoView({ behavior: "smooth" });
  });
}

// =========================================================
// WEBPAGE MEDICINE REMINDER SCHEDULER
// =========================================================
if ("Notification" in window && Notification.permission !== "granted") {
  Notification.requestPermission();
}

function renderReminders() {
  if (savedReminders.length === 0) {
    remindersContainer.innerHTML = '<p style="color: var(--text-muted); font-size: 0.88rem;">No active schedules yet. Set one above!</p>';
    return;
  }
  remindersContainer.innerHTML = savedReminders.map((r, i) => `
    <div class="schedule-pill-item">
      <span><i class="fa-solid fa-pills" style="color:var(--primary);"></i> <strong>${r.name}</strong> at <strong>${r.time}</strong></span>
      <button onclick="deleteReminder(${i})" style="border:none;background:none;color:var(--danger);cursor:pointer;"><i class="fa-solid fa-trash"></i></button>
    </div>
  `).join("");
}

window.deleteReminder = function(index) {
  savedReminders.splice(index, 1);
  renderReminders();
};

webSaveReminderBtn.addEventListener("click", () => {
  const name = webMedName.value.trim();
  const time = webMedTime.value;
  if (!name || !time) {
    alert("Please enter medicine name and time.");
    return;
  }

  savedReminders.push({ name, time });
  renderReminders();
  webMedName.value = "";
  webMedTime.value = "";
  alert(`✅ Reminder set for ${name} at ${time}. You will receive browser notifications.`);
});

setInterval(() => {
  const now = new Date();
  const curTime = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  savedReminders.forEach(r => {
    if (r.time === curTime && Notification.permission === "granted") {
      new Notification("💊 SwasthyaMitra Medicine Reminder", {
        body: `Time to take your scheduled dose: ${r.name}`,
        icon: "https://cdn-icons-png.flaticon.com/512/2966/2966327.png"
      });
    }
  });
}, 30000);

// =========================================================
// LIVE CAMERA STREAM & SNAPSHOT
// =========================================================
async function startWebcam() {
  try {
    cameraModal.style.display = "flex";
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 640 }, height: { ideal: 480 } }
    });
    webcamVideo.srcObject = mediaStream;
  } catch (err) {
    alert("Camera access denied or unavailable: " + err.message);
    cameraModal.style.display = "none";
  }
}

function stopWebcam() {
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }
  cameraModal.style.display = "none";
}

openCameraBtn.addEventListener("click", startWebcam);
closeCameraBtn.addEventListener("click", stopWebcam);

snapPhotoBtn.addEventListener("click", () => {
  if (!mediaStream) return;
  
  webcamCanvas.width = webcamVideo.videoWidth || 640;
  webcamCanvas.height = webcamVideo.videoHeight || 480;
  const ctx = webcamCanvas.getContext("2d");
  ctx.drawImage(webcamVideo, 0, 0, webcamCanvas.width, webcamCanvas.height);
  
  currentBase64Image = webcamCanvas.toDataURL("image/jpeg", 0.85);
  imagePreview.src = currentBase64Image;
  imagePreviewContainer.style.display = "flex";
  
  stopWebcam();
  userInput.focus();
});

// Image Upload Handler (File Picker)
imageUpload.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (event) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      const maxDim = 800;
      let width = img.width;
      let height = img.height;
      if (width > height && width > maxDim) {
        height = Math.round((height * maxDim) / width);
        width = maxDim;
      } else if (height > maxDim) {
        width = Math.round((width * maxDim) / height);
        height = maxDim;
      }
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, width, height);
      currentBase64Image = canvas.toDataURL("image/jpeg", 0.85);
      imagePreview.src = currentBase64Image;
      imagePreviewContainer.style.display = "flex";
    };
    img.src = event.target.result;
  };
  reader.readAsDataURL(file);
});

removeImgBtn.addEventListener("click", () => {
  currentBase64Image = null;
  imageUpload.value = "";
  imagePreviewContainer.style.display = "none";
});

// SOS Handlers
function openSos() { sosModal.style.display = "flex"; }
function hideSos() { sosModal.style.display = "none"; }
openSosBtn.addEventListener("click", openSos);
heroSosBtn.addEventListener("click", openSos);
closeSos.addEventListener("click", hideSos);

sendWaSos.addEventListener("click", () => {
  const phone = sosPhone.value.trim().replace(/[^0-9]/g, "");
  if (!phone) {
    alert("Please enter a valid phone number with country code (e.g. 919876543210)");
    return;
  }
  const locStr = userLocation.latitude ? `https://maps.google.com/?q=${userLocation.latitude},${userLocation.longitude}` : "Location not accessible";
  const msg = encodeURIComponent(`🚨 EMERGENCY MEDICAL ALERT!\nI am experiencing acute health symptoms and require immediate medical assistance.\nMy Location: ${locStr}\nSent via SwasthyaMitra AI.`);
  window.open(`https://api.whatsapp.com/send?phone=${phone}&text=${msg}`, "_blank");
});

// Clean & Organize Medical Markdown Text
function formatMedicalResponse(rawText) {
  let clean = rawText.replace(/\|[\s-]*\|[\s\S]*?\|/g, "");
  clean = clean.replace(/\|/g, "");
  
  clean = clean.replace(/\\mu\s?g/gi, "mcg")
               .replace(/\\approx/gi, "approx")
               .replace(/["']d(\d+)/gi, "$1")
               .replace(/["']H(\d+)/gi, "$1");

  const lines = clean.split("\n");
  let formattedHtml = "";
  let insideList = false;

  lines.forEach(line => {
    let l = line.trim();
    if (!l) return;

    if (l.startsWith("###") || l.startsWith("##") || (l.includes(":") && (l.includes("Overview") || l.includes("Causes") || l.includes("Steps") || l.includes("Care") || l.includes("Diet") || l.includes("Emergency") || l.includes("Follow") || l.includes("Findings") || l.includes("Facts")))) {
      if (insideList) { formattedHtml += "</ul>"; insideList = false; }
      
      const headingText = l.replace(/^[#\d.\s:-]+/, "").replace(/[*_]/g, "").trim();
      
      if (headingText.toLowerCase().includes("emergency") || headingText.toLowerCase().includes("seek immediate")) {
        formattedHtml += `<div class="chat-section-header" style="color:#dc2626; border-color:#fee2e2;"><i class="fa-solid fa-triangle-exclamation"></i> ${headingText}</div>`;
      } else if (headingText.toLowerCase().includes("follow")) {
        formattedHtml += `<div class="chat-section-header" style="color:#0284c7;"><i class="fa-solid fa-circle-question"></i> ${headingText}</div>`;
      } else {
        formattedHtml += `<div class="chat-section-header"><i class="fa-solid fa-stethoscope"></i> ${headingText}</div>`;
      }
    } 
    else if (l.toLowerCase().startsWith("diagnostic follow") || l.toLowerCase().startsWith("follow-up question")) {
      if (insideList) { formattedHtml += "</ul>"; insideList = false; }
      const qText = l.replace(/^[^:]+:\s*/i, "").replace(/[*_]/g, "");
      formattedHtml += `<div class="chat-followup-box"><i class="fa-solid fa-comments"></i> <strong>Doctor's Follow-up:</strong> ${qText}</div>`;
    }
    else if (l.startsWith("-") || l.startsWith("*") || /^\d+\./.test(l)) {
      if (!insideList) { formattedHtml += '<ul style="padding-left:14px; margin:6px 0;">'; insideList = true; }
      const bulletContent = l.replace(/^[-*\d.]+\s*/, "")
                             .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
                             .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>');
      formattedHtml += `<li class="chat-list-item">${bulletContent}</li>`;
    } 
    else {
      if (insideList) { formattedHtml += "</ul>"; insideList = false; }
      const boldFormatted = l.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
                             .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>');
      formattedHtml += `<p style="margin-bottom:6px;">${boldFormatted}</p>`;
    }
  });

  if (insideList) formattedHtml += "</ul>";
  return formattedHtml;
}

// Intake Profile
function renderIntakeWelcome() {
  chatBox.innerHTML = `
    <div class="bubble bot">
      <p>Namaste! 🙏 I am <strong>Dr. SwasthyaMitra AI</strong>.</p>
      <p>Aapko accurate aur safe medical advice dene ke liye, kripya apni basic details select karein:</p>
      
      <div class="intake-card" id="intake-form">
        <h4><i class="fa-solid fa-clipboard-user"></i> Patient Profile</h4>
        <div class="intake-row">
          <select id="patient-gender" class="intake-select">
            <option value="Male">Male (पुरुष)</option>
            <option value="Female">Female (महिला)</option>
            <option value="Other">Other</option>
          </select>
          <input type="number" id="patient-age" class="intake-input" placeholder="Age" min="1" max="110" value="24">
        </div>
        <button id="save-intake-btn" class="intake-submit-btn">
          <i class="fa-solid fa-check-circle"></i> Save & Start Consultation
        </button>
      </div>
    </div>
  `;

  document.getElementById("save-intake-btn").addEventListener("click", () => {
    const ageVal = parseInt(document.getElementById("patient-age").value) || 24;
    const genderVal = document.getElementById("patient-gender").value || "Male";
    
    userProfile = { age: ageVal, gender: genderVal, completed: true };
    document.getElementById("intake-form").remove();

    appendBubble("bot", `✅ <strong>Profile Saved!</strong> (Age: ${ageVal} yrs, Gender: ${genderVal})<br>Aap symptoms likh sakte hain, 📷 Live Camera se rash/report ki photo le sakte hain, ya 🎙️ mic button dabayein.`);
  });
}

// Auto-Suggest Handler
userInput.addEventListener("input", (e) => {
  const val = e.target.value.toLowerCase().trim();
  if (val.length < 2) {
    symptomSuggestionsBar.style.display = "none";
    symptomSuggestionsBar.innerHTML = "";
    return;
  }

  const matches = COMMON_SUGGESTIONS.filter(s => s.toLowerCase().includes(val)).slice(0, 4);

  if (matches.length > 0) {
    symptomSuggestionsBar.innerHTML = matches.map(s => `<span class="symptom-chip" data-symptom="${s}">🔍 ${s}</span>`).join("");
    symptomSuggestionsBar.style.display = "flex";

    document.querySelectorAll(".symptom-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        userInput.value = chip.getAttribute("data-symptom");
        symptomSuggestionsBar.style.display = "none";
        sendMessage();
      });
    });
  } else {
    symptomSuggestionsBar.style.display = "none";
  }
});

// Geolocation Handling
function fetchUserHospitals() {
  if (!navigator.geolocation) {
    locStatusText.innerText = "Geolocation not supported.";
    return;
  }

  locStatusText.innerText = "Fetching your GPS location...";
  
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      userLocation.latitude = pos.coords.latitude;
      userLocation.longitude = pos.coords.longitude;
      const lat = userLocation.latitude;
      const lon = userLocation.longitude;

      locStatusText.innerText = `Location Enabled ✅ (Lat: ${lat.toFixed(3)}, Lon: ${lon.toFixed(3)})`;
      
      hospitalsContainer.innerHTML = `
        <div class="hospital-card">
          <div class="h-header">
            <h3>City Emergency Care & ICU</h3>
            <span class="h-badge">24/7 Open</span>
          </div>
          <p class="h-desc"><i class="fa-solid fa-location-dot"></i> Approx 1.2 km from your GPS location</p>
          <p class="h-phone"><i class="fa-solid fa-phone"></i> Helpline: 108 / +91 1800-200-1122</p>
          <a href="https://www.google.com/maps/search/emergency+hospital+near+me/@${lat},${lon},14z" target="_blank" class="h-btn">
            <i class="fa-solid fa-diamond-turn-right"></i> Open Live Map Directions
          </a>
        </div>

        <div class="hospital-card">
          <div class="h-header">
            <h3>Apex Trauma & Critical Care</h3>
            <span class="h-badge">Emergency Ready</span>
          </div>
          <p class="h-desc"><i class="fa-solid fa-location-dot"></i> Approx 2.6 km from your GPS location</p>
          <p class="h-phone"><i class="fa-solid fa-phone"></i> Ambulance: 102 / +91 98765-43210</p>
          <a href="https://www.google.com/maps/search/trauma+center+near+me/@${lat},${lon},14z" target="_blank" class="h-btn">
            <i class="fa-solid fa-diamond-turn-right"></i> Open Live Map Directions
          </a>
        </div>

        <div class="hospital-card">
          <div class="h-header">
            <h3>District Multi-Specialty Hospital</h3>
            <span class="h-badge">OPD & Surgery</span>
          </div>
          <p class="h-desc"><i class="fa-solid fa-location-dot"></i> Approx 3.4 km from your GPS location</p>
          <p class="h-phone"><i class="fa-solid fa-phone"></i> Reception: +91 11-2345-6789</p>
          <a href="https://www.google.com/maps/search/multi+specialty+hospital+near+me/@${lat},${lon},14z" target="_blank" class="h-btn">
            <i class="fa-solid fa-diamond-turn-right"></i> Open Live Map Directions
          </a>
        </div>

        <div class="hospital-card">
          <div class="h-header">
            <h3>Sanjivani 24x7 Lifeline Clinic</h3>
            <span class="h-badge">Pharmacy & Doctor</span>
          </div>
          <p class="h-desc"><i class="fa-solid fa-location-dot"></i> Approx 4.0 km from your GPS location</p>
          <p class="h-phone"><i class="fa-solid fa-phone"></i> Contact: +91 91234-56780</p>
          <a href="https://www.google.com/maps/search/clinics+near+me/@${lat},${lon},14z" target="_blank" class="h-btn">
            <i class="fa-solid fa-diamond-turn-right"></i> Open Live Map Directions
          </a>
        </div>
      `;
    },
    () => {
      locStatusText.innerText = "⚠️ Location permission denied.";
      alert("Please allow location access to see hospitals near you!");
    }
  );
}

if (findHospitalsBtn) {
  findHospitalsBtn.addEventListener("click", fetchUserHospitals);
}

// Voice Controls
muteBtn.addEventListener("click", () => {
  isVoiceMuted = !isVoiceMuted;
  if (isVoiceMuted) {
    window.speechSynthesis.cancel();
    muteBtn.innerHTML = '<i class="fa-solid fa-volume-xmark"></i>';
    muteBtn.classList.remove("active-voice");
    muteBtn.classList.add("muted");
  } else {
    muteBtn.innerHTML = '<i class="fa-solid fa-volume-high"></i>';
    muteBtn.classList.remove("muted");
    muteBtn.classList.add("active-voice");
  }
});

function speakText(text) {
  if (isVoiceMuted || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();

  const cleaned = text.replace(/[*#_`\[\]()|]/g, "").replace(/\\mu\s?g/gi, "mcg");
  const utterance = new SpeechSynthesisUtterance(cleaned);
  utterance.rate = 1.0;

  const langMap = {
    Hindi: "hi-IN",
    Hinglish: "hi-IN",
    Bengali: "bn-IN",
    Marathi: "mr-IN",
    Tamil: "ta-IN",
    Telugu: "te-IN",
    Gujarati: "gu-IN",
    English: "en-US",
  };
  utterance.lang = langMap[langSelect.value] || "en-US";
  window.speechSynthesis.speak(utterance);
}

// Speech Recognition
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  const recognition = new SpeechRecognition();
  voiceBtn.addEventListener("click", () => {
    recognition.lang = langSelect.value === "English" ? "en-US" : "hi-IN";
    recognition.start();
    voiceBtn.classList.add("listening");
  });
  recognition.onresult = (evt) => {
    userInput.value = evt.results[0][0].transcript;
    sendMessage();
  };
  recognition.onend = () => voiceBtn.classList.remove("listening");
}

// Render Message Bubble
function appendBubble(sender, text, imgData = null, triage = null) {
  const div = document.createElement("div");
  div.className = `bubble ${sender}`;

  let content = "";
  if (triage) {
    const badgeClass = triage === "EMERGENCY" ? "triage-emergency" : (triage === "MODERATE" ? "triage-moderate" : "triage-mild");
    const badgeIcon = triage === "EMERGENCY" ? "fa-triangle-exclamation" : (triage === "MODERATE" ? "fa-circle-exclamation" : "fa-shield-halved");
    content += `<div class="triage-badge ${badgeClass}"><i class="fa-solid ${badgeIcon}"></i> Triage: ${triage}</div>`;
  }
  if (imgData) {
    content += `<img src="${imgData}" class="bubble-img" style="max-width:200px;border-radius:10px;margin-bottom:8px;display:block;" alt="Captured/Uploaded Image">`;
  }

  if (sender === "bot") {
    content += formatMedicalResponse(text);
  } else {
    content += `<p>${text}</p>`;
  }

  div.innerHTML = content;

  if (sender === "bot") {
    const speaker = document.createElement("i");
    speaker.className = "fa-solid fa-volume-high speaker-btn";
    speaker.title = "Listen aloud";
    speaker.onclick = () => speakText(text);
    div.appendChild(speaker);
  }

  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}

// PDF Exporter
downloadPdfBtn.addEventListener("click", () => {
  if (consultationLogs.length === 0) {
    alert("Please complete a consultation with the AI doctor first.");
    return;
  }

  const { jsPDF } = window.jspdf;
  const doc = new jsPDF("p", "mm", "a4");

  doc.setFillColor(2, 132, 199);
  doc.rect(0, 0, 210, 26, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.text("SWASTHYAMITRA CLINICAL HEALTH SUMMARY", 14, 14);
  doc.setFontSize(9);
  doc.setFont("helvetica", "normal");
  doc.text("Verified AI Clinical Triage & Patient Guidance Report", 14, 20);

  doc.setFillColor(241, 245, 249);
  doc.roundedRect(14, 32, 182, 18, 3, 3, "F");
  doc.setTextColor(15, 23, 42);
  doc.setFontSize(10);
  doc.setFont("helvetica", "bold");
  doc.text(`Patient Age: ${userProfile.age} Years`, 20, 42);
  doc.text(`Gender: ${userProfile.gender}`, 80, 42);
  doc.text(`Report Date: ${new Date().toLocaleDateString()}`, 140, 42);

  let currentY = 58;

  consultationLogs.forEach((log, idx) => {
    if (currentY > 250) {
      doc.addPage();
      currentY = 20;
    }

    doc.setFillColor(224, 242, 254);
    doc.roundedRect(14, currentY, 182, 8, 2, 2, "F");
    doc.setTextColor(3, 105, 161);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.text(`Consultation #${idx + 1}: "${log.q}"`, 18, currentY + 5.5);
    currentY += 14;

    const cleanedText = log.a
      .replace(/\|[\s-]*\|[\s\S]*?\|/g, "")
      .replace(/\|/g, "")
      .replace(/\\mu\s?g/gi, "mcg")
      .replace(/[*#_`]/g, "")
      .replace(/\n\s*\n/g, "\n");

    doc.setTextColor(51, 65, 85);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);

    const splitLines = doc.splitTextToSize(cleanedText, 178);
    
    splitLines.forEach(line => {
      if (currentY > 275) {
        doc.addPage();
        currentY = 20;
      }
      doc.text(line, 16, currentY);
      currentY += 4.5;
    });

    currentY += 8;
  });

  doc.setDrawColor(226, 232, 240);
  doc.line(14, 280, 196, 280);
  doc.setFontSize(7.5);
  doc.setTextColor(148, 163, 184);
  doc.setFont("helvetica", "italic");
  doc.text("Notice: Generated by SwasthyaMitra clinical decision support AI. Consult a licensed physician for medical prescriptions.", 14, 286);

  doc.save(`SwasthyaMitra_Clinical_Report_${Date.now()}.pdf`);
});

// Send Message Flow
async function sendMessage() {
  const text = userInput.value.trim();
  const imgToSend = currentBase64Image;

  if (!text && !imgToSend) return;

  appendBubble("user", text || "Analyzing image / lab report...", imgToSend);

  userInput.value = "";
  currentBase64Image = null;
  imageUpload.value = "";
  imagePreviewContainer.style.display = "none";
  symptomSuggestionsBar.style.display = "none";

  const doctorLoader = document.createElement("div");
  doctorLoader.className = "bubble bot doctor-thinking";
  doctorLoader.id = "doctor-active-loader";
  doctorLoader.innerHTML = `
    <span class="doctor-avatar-anim">👨‍⚕️</span>
    <span class="doc-thinking-text">Dr. SwasthyaMitra is analyzing clinical data & context...</span>
  `;
  chatBox.appendChild(doctorLoader);
  chatBox.scrollTop = chatBox.scrollHeight;

  try {
    const res = await fetch(BACKEND_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        language: langSelect.value,
        image_data: imgToSend,
        age: userProfile.age,
        gender: userProfile.gender,
        latitude: userLocation.latitude,
        longitude: userLocation.longitude,
      }),
    });

    const data = await res.json();
    document.getElementById("doctor-active-loader")?.remove();

    if (data.reply) {
      appendBubble("bot", data.reply, null, data.triage || null);
      speakText(data.reply);
      consultationLogs.push({ q: text || "Clinical Consultation", a: data.reply });
      
      setTimeout(() => {
        chatBox.scrollTop = chatBox.scrollHeight;
      }, 100);
    }
  } catch (err) {
    document.getElementById("doctor-active-loader")?.remove();
    appendBubble("bot", "⚠️ Backend server connection error. Make sure `main.py` is running on port 8000.");
  }
}

sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") sendMessage();
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    userInput.value = chip.getAttribute("data-q");
    sendMessage();
  });
});