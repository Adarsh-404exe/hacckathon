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
                "Platelet counts below 100,000 indicate thrombocytopenia needing dengue testing and close monitoring.",
                "Hemoglobin below 12 g/dL indicates mild to moderate anemia requiring dietary iron and consultation.",
                "Emergency first-aid: Paracetamol for acute fever (avoid aspirin in dengue), ORS for severe dehydration."
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


SYSTEM_PROMPT = """You are "Dr. MediNova", an expert concise clinical AI doctor.
Patient Profile: {age} yrs old, {gender}.

RESPONSE RULES (STRICT & SHORT):
1. First line must be: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. Keep explanations SHORT, PRECISE, and bulleted (maximum 120-150 words total).
3. Structure:
   - 🩺 Clinical Summary: 1 concise sentence about the core issue/report numbers.
   - 💊 Safe Emergency First-Aid / Medicines: Mention exact safe OTC medicines with purpose (e.g., Paracetamol 500/650mg for fever/body pain, ORS for dehydration, Calamine lotion / Cetirizine 10mg for rash/allergy, Antacid for reflux). *State caution for pregnancy/kidney*.
   - ⚠️ Hospital Red Flags: Call 108 immediately if danger signs appear.
   - ❓ Quick Question: 1 short diagnostic question.

Respond in {language}. No ASCII markdown tables.

Context: {context}"""


VISION_PROMPT = """You are Dr. MediNova, an expert clinical physician analyzing a medical scan.
Patient Profile: {age} yrs, {gender}. Language: {language}.
Query: "{query}"

Analyze concisely:
1. Start with [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. 🩺 Visual/Lab Findings: Identify the exact condition, abnormal values (e.g. low platelets), or medicine name in 1-2 bullet points.
3. 💊 Suggested First-Aid / Emergency Medicines: Safe relief medicines (e.g. Paracetamol for fever, ORS, Cetirizine, Antacids).
4. ⚠️ When to consult a Doctor / Red Flags.
5. ❓ Diagnostic Question: 1 short follow-up question.

Keep response very short (under 140 words) and empathetic in {language}."""


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
            "reply": "Namaste! 🙏 Main Dr. MediNova hoon. Aap medicine strip, blood report, skin rash scan karwa sakte hain ya apna symptom bata sakte hain.",
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

    # Vision Payload
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
                    max_tokens=350
                )
                raw = resp.choices[0].message.content
                triage_level, clean = extract_triage_severity(raw)
                return {"reply": clean, "triage": triage_level}
            except Exception:
                continue

        ctx = rag.retrieve(user_query)
        dynamic_prompt = f"""Patient uploaded image with query: "{user_query}".
Context: {ctx}
Provide a short 100-word clinical assessment as Dr. MediNova with safe emergency medicines (Paracetamol, ORS, Calamine) in {lang}.
Start with [SEVERITY: MILD]."""

        for chat_model in AVAILABLE_CHAT_MODELS:
            try:
                resp = groq_client.chat.completions.create(
                    model=chat_model,
                    messages=[{"role": "user", "content": dynamic_prompt}],
                    temperature=0.2,
                    max_tokens=300
                )
                raw = resp.choices[0].message.content
                triage_level, clean = extract_triage_severity(raw)
                return {"reply": clean, "triage": triage_level}
            except Exception:
                continue

    # Text RAG
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
                max_tokens=320
            )
            raw_answer = resp.choices[0].message.content
            triage_level, clean_answer = extract_triage_severity(raw_answer)
            return {"reply": clean_answer, "triage": triage_level}
        except Exception as e:
            last_err = str(e)
            continue

    return {"reply": f"⚠️ Service busy. Error: {last_err}", "triage": "MILD"}
