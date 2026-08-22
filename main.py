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
    raise ValueError("GROQ_API_KEY is missing in your Environment Variables!")

groq_client = Groq(api_key=GROQ_API_KEY)

# Dynamic Fetch of Live Models
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
    except Exception as e:
        print(f"[!] Groq Model List fallback: {e}")
        return ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"], ["llama-3.2-11b-vision-preview"]

ACTIVE_CHAT_MODELS, ACTIVE_VISION_MODELS = get_working_models()

# In-Memory PDF RAG
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
            except Exception as e:
                print(f"[!] RAG PDF Notice: {e}")
        if not self.chunks:
            self.chunks = [
                "Abdominal pain: Indigestion, gas spasms, antacids (Digene, Pudin Hara), light diet, hydration.",
                "Fever and body pain: Paracetamol 650mg, ORS electrolytes, plenty of liquids.",
                "Skin rashes and urticaria: Calamine lotion, Cetirizine, cold compresses."
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

SYS_PROMPT = """You are Dr. MediNova, a compassionate clinical AI physician.
Patient Profile: Age {age}, Gender {gender}. Language: {lang}.

RULES:
1. First line must strictly be: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. Focus strictly on the patient's specific question (do NOT mention unrelated diseases like fever if they ask about stomach pain).
3. Structure:
   - 🩺 Clinical Overview: 1-2 empathetic lines explaining why this happens.
   - 🔍 Probable Causes: 2-3 concise points matching query.
   - 🌿 Home Remedies (Gharelu Nuskhe): Practical home relief (warm water, diet, rest).
   - 💊 Safe Relief Medicines: 1-2 standard safe OTC options strictly matching their symptom (e.g., Antacid/Digene for stomach pain, Paracetamol for body ache/fever).
   - ⚠️ When to see Doctor: 1-2 red flag warnings.
   - ❓ Diagnostic Question: Exactly 1 relevant follow-up question.

Keep it helpful and natural in {lang}. No ASCII markdown tables.
Context: {context}"""

@app.get("/")
def get_index():
    return FileResponse("index.html")

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
            "reply": "Namaste! 🙏 Main Dr. MediNova hoon. Aap medicine strip, report ya apne symptoms share karein.",
            "triage": "MILD"
        }

    if any(k in q.lower() for k in ["hospital", "clinic", "aspatal"]):
        lat = req.latitude or 26.9124
        lon = req.longitude or 75.7873
        return {
            "reply": f"🏥 **Nearby Hospitals:**\n👉 [📍 Open Google Maps Directions](https://www.google.com/maps/search/hospitals+near+me/@{lat},{lon},14z)\n🚨 Emergency: **108**",
            "triage": "MODERATE"
        }

    ctx = rag.retrieve(q or "medicine general")
    prompt = SYS_PROMPT.format(age=req.age, gender=req.gender, lang=lang, context=ctx)
    
    last_error = ""

    # 1. Vision Request
    if req.image_data:
        fmt_img = req.image_data if req.image_data.startswith("data:") else f"data:image/jpeg;base64,{req.image_data}"
        vision_msgs = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Analyze this medical image / report: {q or 'What is shown in this image?'}"},
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
                    max_tokens=400
                ).choices[0].message.content

                triage = "EMERGENCY" if "[SEVERITY: EMERGENCY]" in resp else ("MODERATE" if "[SEVERITY: MODERATE]" in resp else "MILD")
                clean = re.sub(r"\[SEVERITY:\s*(MILD|MODERATE|EMERGENCY)\]", "", resp).strip()
                return {"reply": clean, "triage": triage}
            except Exception as e:
                last_error = str(e)
                continue

    # 2. Text Request (With Robust Multi-Model Fallbacks)
    text_msgs = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": q if q else "Provide health guidance."}
    ]

    for c_mod in ACTIVE_CHAT_MODELS:
        try:
            resp = groq_client.chat.completions.create(
                model=c_mod,
                messages=text_msgs,
                temperature=0.2,
                max_tokens=420
            ).choices[0].message.content

            triage = "EMERGENCY" if "[SEVERITY: EMERGENCY]" in resp else ("MODERATE" if "[SEVERITY: MODERATE]" in resp else "MILD")
            clean = re.sub(r"\[SEVERITY:\s*(MILD|MODERATE|EMERGENCY)\]", "", resp).strip()
            return {"reply": clean, "triage": triage}
        except Exception as e:
            last_error = str(e)
            continue

    # 3. Last-Resort Safe Fallback Response
    if "pet" in q.lower() or "stomach" in q.lower() or "dard" in q.lower():
        return {
            "reply": "🩺 **Pet Dard Care:**\n- Halka gunguna paani ya heeng-jeera paani piyein.\n- Tel, masala aur heavy khana avoid karein, khichdi lein.\n💊 **Safe OTC:** Antacid gel / Digene ya Pudin Hara le sakte hain.\n⚠️ **Warning:** Agar dard unbearable ho ya ulti/fever aaye toh turant doctor ko dikhayein.\n❓ Dard kitni der se ho raha hai?",
            "triage": "MILD"
        }

    return {"reply": f"⚠️ Connection refreshed. Please tap send again. (Ref: {last_error[:50]})", "triage": "MILD"}
