import os
import re
import base64
from typing import Optional, Union, List
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import Groq
from pydantic import BaseModel
from pypdf import PdfReader

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing!")

groq_client = Groq(api_key=GROQ_API_KEY)

def get_working_models():
    try:
        available = [m.id for m in groq_client.models.list().data]
        chat = [m for m in available if not any(k in m for k in ["whisper", "guard", "embed", "orpheus", "vision"])]
        vision = [m for m in available if "vision" in m or "scout" in m]
        if not chat:
            chat = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"]
        if not vision:
            vision = ["llama-3.2-11b-vision-preview", "llama-3.2-90b-vision-preview"]
        return chat, vision
    except Exception:
        return ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"], ["llama-3.2-11b-vision-preview"]

ACTIVE_CHAT_MODELS, ACTIVE_VISION_MODELS = get_working_models()

# Clean Medical Knowledge Base
class MedicalRAG:
    def __init__(self, path="Gale Encyclopedia of Medicine Vol. 2 (C-F) (1).pdf"):
        self.chunks: List[str] = []
        if os.path.exists(path):
            try:
                reader = PdfReader(path)
                for page in reader.pages[:40]:
                    txt = page.extract_text()
                    if txt:
                        words = txt.split()
                        for i in range(0, len(words), 80):
                            c = " ".join(words[i:i+80])
                            if len(c) > 30:
                                self.chunks.append(c)
            except Exception: pass
        if not self.chunks:
            self.chunks = [
                "Abdominal pain: Gastritis, indigestion, antacids (Digene, Pudin Hara), ginger water.",
                "Fever: Paracetamol 650mg, ORS electrolyte, cold compress.",
                "Skin allergies: Calamine lotion, Cetirizine 10mg."
            ]

    def retrieve(self, query: str) -> str:
        if not self.chunks:
            return ""
        qw = set(re.findall(r"\w+", query.lower()))
        scored = sorted([(len(qw.intersection(set(re.findall(r"\w+", c.lower())))), c) for c in self.chunks], reverse=True)
        return " ".join([c for s, c in scored[:2] if s > 0]) or self.chunks[0]

rag = MedicalRAG()
app = FastAPI(title="MediNova AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class ChatRequest(BaseModel):
    message: str
    language: Optional[str] = "Hinglish"
    age: Optional[Union[int, str]] = 24
    gender: Optional[str] = "Transgender"
    image_data: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

# STRICT HEALTH-ONLY SYSTEM PROMPT (No Filler Text)
SYS_PROMPT = """You are Dr. MediNova, a clinical AI doctor.
Patient: {age} yrs, {gender}. Language: {lang}.

RULES:
1. First line MUST be: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. Provide ONLY precise clinical & health information matching the patient's exact question.
3. If the query is NOT related to health, human body, symptoms, medicines, or medical reports, strictly reply: "Please ask health or medical related questions only."
4. Structure:
   - 🩺 Clinical Overview: Direct explanation of the condition.
   - 🌿 Home Remedies: 2 practical remedies for immediate comfort.
   - 💊 Safe OTC Relief: Exact safe OTC medicine matching the symptom (e.g., Digene/Pudin Hara for gas, Paracetamol for pain/fever).
   - ⚠️ Red Flags: When to visit a doctor immediately.
   - ❓ Follow-up: 1 direct clinical question.

No markdown tables. Pure concise medical facts in {lang}.
Context: {context}"""

@app.get("/")
def get_index(): return FileResponse("index.html")

@app.get("/{file_name}")
def get_static(file_name: str):
    if file_name in ["style.css", "app.js", "sw.js", "manifest.json"]:
        return FileResponse(file_name)
    return FileResponse("index.html")

@app.post("/chat")
def chat(req: ChatRequest):
    q = req.message.strip()
    lang = req.language or "Hinglish"
    
    if not req.image_data and q.lower() in ["hi", "hello", "hey", "namaste", "hii", "hlo"]:
        return {
            "reply": "Namaste! 🙏 Main Dr. MediNova hoon. Aap medicine, lab report, skin issue ya apne physical symptoms share karein.",
            "triage": "MILD"
        }

    if any(k in q.lower() for k in ["hospital", "clinic", "aspatal"]):
        lat = req.latitude or 26.9124
        lon = req.longitude or 75.7873
        return {
            "reply": f"🏥 **Nearby Emergency Centers:**\n👉 [📍 Open Google Maps Directions](https://www.google.com/maps/search/hospitals+near+me/@{lat},{lon},14z)\n🚨 Ambulance: **108**",
            "triage": "MODERATE"
        }

    ctx = rag.retrieve(q or "clinical guidance")
    prompt = SYS_PROMPT.format(age=req.age, gender=req.gender, lang=lang, context=ctx)
    
    # Vision Query
    if req.image_data:
        fmt_img = req.image_data if req.image_data.startswith("data:") else f"data:image/jpeg;base64,{req.image_data}"
        vision_msgs = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Analyze this medical image / report: {q or 'Identify and evaluate this medical photo.'}"},
                    {"type": "image_url", "image_url": {"url": fmt_img}}
                ]
            }
        ]
        for v_mod in ACTIVE_VISION_MODELS:
            try:
                resp = groq_client.chat.completions.create(
                    model=v_mod,
                    messages=vision_msgs,
                    temperature=0.2,
                    max_tokens=380
                ).choices[0].message.content

                triage = "EMERGENCY" if "[SEVERITY: EMERGENCY]" in resp else ("MODERATE" if "[SEVERITY: MODERATE]" in resp else "MILD")
                clean = re.sub(r"\[SEVERITY:\s*(MILD|MODERATE|EMERGENCY)\]", "", resp).strip()
                return {"reply": clean, "triage": triage}
            except Exception:
                continue

    # Text Query
    text_msgs = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": q}
    ]

    for c_mod in ACTIVE_CHAT_MODELS:
        try:
            resp = groq_client.chat.completions.create(
                model=c_mod,
                messages=text_msgs,
                temperature=0.2,
                max_tokens=380
            ).choices[0].message.content

            triage = "EMERGENCY" if "[SEVERITY: EMERGENCY]" in resp else ("MODERATE" if "[SEVERITY: MODERATE]" in resp else "MILD")
            clean = re.sub(r"\[SEVERITY:\s*(MILD|MODERATE|EMERGENCY)\]", "", resp).strip()
            return {"reply": clean, "triage": triage}
        except Exception:
            continue

    return {
        "reply": "🩺 **Medical Care:**\n- Halka bhojan lein aur hydrated rahein.\n💊 **Safe OTC:** Symptom ke anusar Paracetamol ya Antacid le sakte hain.\n⚠️ **Warning:** Agar lakshan gambhir hon toh turant doctor se consult karein.",
        "triage": "MILD"
    }
