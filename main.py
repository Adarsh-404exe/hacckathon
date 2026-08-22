import os
import re
import base64
from io import BytesIO
from typing import List, Optional, Union, Dict
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import Groq
from PIL import Image
from pydantic import BaseModel
from pypdf import PdfReader

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing in your .env file!")

groq_client = Groq(api_key=GROQ_API_KEY)
PDF_FILE_PATH = "Gale Encyclopedia of Medicine Vol. 2 (C-F) (1).pdf"


def get_live_groq_models():
    try:
        model_list = [m.id for m in groq_client.models.list().data]
        chat_models = [
            m for m in model_list 
            if not any(k in m for k in ["whisper", "guard", "embed", "orpheus"])
        ]
        vision_models = [m for m in model_list if any(k in m.lower() for k in ["vision", "scout", "multimodal"])]
        if not vision_models:
            vision_models = ["llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview"]
        return chat_models, vision_models
    except Exception:
        return ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"], ["llama-3.2-90b-vision-preview"]

AVAILABLE_CHAT_MODELS, AVAILABLE_VISION_MODELS = get_live_groq_models()


# =========================================================
# ULTRA-LIGHTWEIGHT RAG ENGINE (< 40MB RAM)
# =========================================================
class LightweightMedicalRAG:
    def __init__(self, pdf_path: str):
        self.chunks: List[str] = []
        self._load_pdf_data(pdf_path)

    def _load_pdf_data(self, pdf_path: str):
        raw = []
        if os.path.exists(pdf_path):
            try:
                reader = PdfReader(pdf_path)
                for page in reader.pages[:60]:
                    txt = page.extract_text()
                    if txt:
                        words = txt.split()
                        for i in range(0, len(words), 80):
                            c = " ".join(words[i : i + 80])
                            if len(c) > 35:
                                raw.append(c)
            except Exception as e:
                print(f"[!] PDF notice: {e}")

        if not raw:
            raw = [
                "Abdominal pain can stem from indigestion, gastritis, spasms, acid reflux, or infections.",
                "Warm water, ginger/jeera tea, light khichdi, and antacids provide relief for gastric discomfort.",
                "Dengue fever presents with acute high fever, thrombocytopenia (low platelets), and body aches."
            ]

        self.chunks = raw

    def retrieve(self, query: str, top_k: int = 2) -> str:
        if not self.chunks:
            return ""
        
        query_words = set(re.findall(r"\w+", query.lower()))
        if not query_words:
            return self.chunks[0][:300]

        scored_chunks = []
        for chunk in self.chunks:
            chunk_words = set(re.findall(r"\w+", chunk.lower()))
            overlap = len(query_words.intersection(chunk_words))
            scored_chunks.append((overlap, chunk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c for score, c in scored_chunks[:top_k] if score > 0]
        
        if top_chunks:
            return " ".join(top_chunks)[:350]
        return self.chunks[0][:300]


rag = LightweightMedicalRAG(PDF_FILE_PATH)

# =========================================================
# FASTAPI BACKEND
# =========================================================
app = FastAPI(title="MediNova Unified Health AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MessageItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    language: Optional[str] = "Hinglish"
    age: Optional[Union[int, str]] = 24
    gender: Optional[str] = "Transgender"
    image_data: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    history: Optional[List[MessageItem]] = []


SYSTEM_PROMPT = """You are "Dr. MediNova", a clinical AI physician.
Patient Profile: {age} years old, {gender}.

CORE INSTRUCTIONS:
1. First line must strictly be: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. FOCUS STRICTLY ON THE USER'S SPECIFIC PROBLEM (Do NOT mention unrelated illnesses like fever or rash if the user is asking about stomach pain, headache, etc.).
3. STRUCTURE YOUR ANSWER AS FOLLOWS:
   - 🩺 Clinical Overview: 1-2 empathetic lines explaining why this specific problem happens.
   - 🔍 Probable Causes: 2-3 bullet points relevant ONLY to their query.
   - 🌿 Home Remedies (Gharelu Nuskhe): 2-3 practical, effective home relief steps (e.g. warm water, ginger/fennel, diet tips, rest).
   - 💊 Safe Relief Medicines (Specific to this condition only): Mention 1-2 standard safe OTC options strictly matching their symptom (e.g. Antacids/Digene/Pudin Hara for stomach gas, Paracetamol for pain/fever, etc.).
   - ⚠️ When to see a Doctor: 1-2 red flag warnings.
   - ❓ Diagnostic Question: 1 short relevant follow-up question.

Keep the response balanced, helpful, and natural in {language}. No ASCII tables.

Context: {context}"""


VISION_PROMPT = """You are Dr. MediNova analyzing a medical image (report, medicine, skin condition, or physical issue).
Patient Profile: {age} yrs, {gender}. Language: {language}.
Query: "{query}"

Analyze specifically:
1. Start with [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. 🩺 Visual/Lab Findings: What is seen in the image.
3. 🔍 What it indicates: Clear explanation.
4. 🌿 Home Remedies & Safe Self-Care: Practical relief tips.
5. 💊 Recommended Safe OTC Care: Medicines strictly matching the visible issue.
6. ⚠️ Red Flags requiring hospital visit.
7. ❓ 1 Follow-up Question.

Respond empathetically in {language}."""


def extract_triage_severity(text: str):
    if "[SEVERITY: EMERGENCY]" in text:
        return "EMERGENCY", text.replace("[SEVERITY: EMERGENCY]", "").strip()
    elif "[SEVERITY: MODERATE]" in text:
        return "MODERATE", text.replace("[SEVERITY: MODERATE]", "").strip()
    elif "[SEVERITY: MILD]" in text:
        return "MILD", text.replace("[SEVERITY: MILD]", "").strip()
    return "MILD", text


# Serve Static UI
@app.get("/")
def serve_index():
    return FileResponse("index.html")

@app.get("/style.css")
def serve_css():
    return FileResponse("style.css")

@app.get("/app.js")
def serve_js():
    return FileResponse("app.js")


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    q = req.message.strip()
    lang = req.language or "Hinglish"

    try:
        age_int = int(str(req.age).split()[0]) if req.age else 24
    except Exception:
        age_int = 24

    gender_str = str(req.gender) if req.gender else "Transgender"

    if q.lower() in ["hi", "hello", "hey", "namaste", "hii", "hlo"] and not req.image_data:
        return {
            "reply": "Namaste! 🙏 Main Dr. MediNova hoon. Aap medicine strip, blood report, skin rash scan karwa sakte hain ya apna koi symptom bata sakte hain.",
            "triage": "MILD"
        }

    # Hospital directions
    if any(k in q.lower() for k in ["hospital", "clinic", "aspatal", "doctor nearby"]):
        lat = req.latitude or 26.9124
        lon = req.longitude or 75.7873
        link = f"https://www.google.com/maps/search/hospitals+near+me/@{lat},{lon},14z"
        return {
            "reply": f"🏥 **Nearby Hospitals:**\n👉 [📍 Open Google Maps Directions]({link})\n🚨 Emergency: Call **108**.",
            "triage": "MODERATE"
        }

    # Vision Handler
    if req.image_data:
        user_query = q if q else "Analyze this medical report, medicine strip, or skin symptom."
        v_prompt = VISION_PROMPT.format(age=age_int, gender=gender_str, language=lang, query=user_query)
        formatted_img_url = req.image_data if req.image_data.startswith("data:") else f"data:image/jpeg;base64,{req.image_data}"

        for v_model in AVAILABLE_VISION_MODELS:
            try:
                resp = groq_client.chat.completions.create(
                    model=v_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": v_prompt},
                            {"type": "image_url", "image_url": {"url": formatted_img_url}}
                        ]
                    }],
                    temperature=0.2,
                    max_tokens=420
                )
                raw = resp.choices[0].message.content
                triage_level, clean = extract_triage_severity(raw)
                return {"reply": clean, "triage": triage_level}
            except Exception:
                continue

        ctx = rag.retrieve(user_query)
        dynamic_prompt = f"""Patient uploaded image with query: "{user_query}".
Context: {ctx}
Provide a clinical assessment as Dr. MediNova explaining the condition with home remedies and relevant safe medicines in {lang}.
Start with [SEVERITY: MILD]."""

        for chat_model in AVAILABLE_CHAT_MODELS:
            try:
                resp = groq_client.chat.completions.create(
                    model=chat_model,
                    messages=[{"role": "user", "content": dynamic_prompt}],
                    temperature=0.2,
                    max_tokens=400
                )
                raw = resp.choices[0].message.content
                triage_level, clean = extract_triage_severity(raw)
                return {"reply": clean, "triage": triage_level}
            except Exception:
                continue

    # Text RAG Flow
    ctx = rag.retrieve(q)
    prompt = SYSTEM_PROMPT.format(age=age_int, gender=gender_str, language=lang, context=ctx)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": q}
    ]

    last_err = ""
    for model_name in AVAILABLE_CHAT_MODELS:
        try:
            resp = groq_client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=420
            )
            raw_answer = resp.choices[0].message.content
            triage_level, clean_answer = extract_triage_severity(raw_answer)
            return {"reply": clean_answer, "triage": triage_level}
        except Exception as e:
            last_err = str(e)
            continue

    return {"reply": f"⚠️ Service busy. Error: {last_err}", "triage": "MILD"}
