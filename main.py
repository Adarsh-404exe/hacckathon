import os, re, base64
from typing import Optional, Union
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import Groq
from pydantic import BaseModel
from pypdf import PdfReader

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Ultra-Lightweight Clinical In-Memory Index
class MedicalRAG:
    def __init__(self, path="Gale Encyclopedia of Medicine Vol. 2 (C-F) (1).pdf"):
        self.chunks = []
        if os.path.exists(path):
            try:
                reader = PdfReader(path)
                for page in reader.pages[:60]:
                    txt = page.extract_text()
                    if txt:
                        words = txt.split()
                        self.chunks.extend([" ".join(words[i:i+80]) for i in range(0, len(words), 80) if len(words[i:i+80]) > 5])
            except Exception: pass
        if not self.chunks:
            self.chunks = ["Digestive pain: Antacids, light diet, hydration.", "Fever: Paracetamol, electrolytes."]

    def retrieve(self, q: str) -> str:
        qw = set(re.findall(r"\w+", q.lower()))
        scored = sorted([(len(qw.intersection(set(re.findall(r"\w+", c.lower())))), c) for c in self.chunks], reverse=True)
        return " ".join([c for s, c in scored[:2] if s > 0]) or self.chunks[0]

rag = MedicalRAG()
app = FastAPI(title="MediNova AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    message: str
    language: Optional[str] = "Hinglish"
    age: Optional[Union[int, str]] = 24
    gender: Optional[str] = "Transgender"
    image_data: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

SYS_PROMPT = """You are Dr. MediNova, clinical AI. Profile: {age}yo, {gender}. Language: {lang}.
RULES:
1. First line strictly: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. Focus ONLY on patient's exact query.
3. Structure:
   - 🩺 Clinical Overview
   - 🔍 Probable Causes (Query specific)
   - 🌿 Home Remedies (Gharelu Nuskhe)
   - 💊 Safe Relief Medicines (Specific safe OTC drugs only)
   - ⚠️ When to see Doctor (Red flags)
   - ❓ Diagnostic Question (1 concise follow-up)
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
    q, lang = req.message.strip(), req.language or "Hinglish"
    if not req.image_data and q.lower() in ["hi", "hello", "hey", "namaste"]:
        return {"reply": "Namaste! 🙏 Main Dr. MediNova hoon. Aap medicine strip, report ya symptoms share karein.", "triage": "MILD"}

    if any(k in q.lower() for k in ["hospital", "clinic", "aspatal"]):
        lat, lon = req.latitude or 26.9124, req.longitude or 75.7873
        return {"reply": f"🏥 **Nearby Emergency Centers:**\n👉 [📍 Open Google Maps Directions](https://www.google.com/maps/search/hospitals+near+me/@{lat},{lon},14z)\n🚨 Emergency: **108**", "triage": "MODERATE"}

    msgs = [{"role": "system", "content": SYS_PROMPT.format(age=req.age, gender=req.gender, lang=lang, context=rag.retrieve(q))}]
    if req.image_data:
        fmt_img = req.image_data if req.image_data.startswith("data:") else f"data:image/jpeg;base64,{req.image_data}"
        msgs.append({"role": "user", "content": [{"type": "text", "text": f"Analyze scan/medicine/report for: {q}"}, {"type": "image_url", "image_url": {"url": fmt_img}}]})
        models = ["llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview", "llama-3.3-70b-versatile"]
    else:
        msgs.append({"role": "user", "content": q})
        models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    for m in models:
        try:
            r = groq_client.chat.completions.create(model=m, messages=msgs, temperature=0.2, max_tokens=400).choices[0].message.content
            triage = "EMERGENCY" if "[SEVERITY: EMERGENCY]" in r else ("MODERATE" if "[SEVERITY: MODERATE]" in r else "MILD")
            clean = re.sub(r"\[SEVERITY:\s*(MILD|MODERATE|EMERGENCY)\]", "", r).strip()
            return {"reply": clean, "triage": triage}
        except Exception: continue
    return {"reply": "⚠️ Service temporarily busy. Please retry.", "triage": "MILD"}
