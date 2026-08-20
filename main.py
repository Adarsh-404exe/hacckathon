import os
import base64
from typing import List, Optional, Union, Dict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
import numpy as np
from pydantic import BaseModel
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing in your .env file!")

groq_client = Groq(api_key=GROQ_API_KEY)
PDF_FILE_PATH = "Gale Encyclopedia of Medicine Vol. 2 (C-F) (1).pdf"


# Dynamic Active Model Discovery
def get_live_groq_models():
    try:
        model_list = [m.id for m in groq_client.models.list().data]
        chat_models = [
            m for m in model_list 
            if not any(k in m for k in ["whisper", "guard", "embed", "orpheus"])
        ]
        return chat_models
    except Exception:
        return ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

AVAILABLE_CHAT_MODELS = get_live_groq_models()


# =========================================================
# 1. SMART DEMOGRAPHIC RAG ENGINE
# =========================================================
class PartitionedMedicalRAG:
    def __init__(self, pdf_path: str):
        print("[*] Initializing Semantic Vector Database...")
        self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
        self.chunks = []
        self.embeddings = None
        self._build(pdf_path)

    def _build(self, pdf_path: str):
        raw = []
        if os.path.exists(pdf_path):
            reader = PdfReader(pdf_path)
            for page in reader.pages[:80]:
                txt = page.extract_text()
                if txt:
                    words = txt.split()
                    for i in range(0, len(words), 80):
                        c = " ".join(words[i : i + 80])
                        if len(c) > 30:
                            raw.append(c)
        else:
            raw = [
                "Phimosis is a condition where the foreskin cannot be retracted over the glans penis in males. It is anatomically impossible in females.",
                "Dengue viral infection causes sudden high fever, thrombocytopenia (low platelets), and severe joint pain.",
                "Celiac disease causes digestive inflammation due to gluten sensitivity across all adults.",
                "Fever, dehydration, and pediatric conditions require safe hydration and dosage caution."
            ]
        self.chunks = raw
        if self.chunks:
            embs = self.encoder.encode(self.chunks, convert_to_numpy=True)
            norms = np.linalg.norm(embs, axis=1, keepdims=True)
            norms[norms == 0] = 1e-10
            self.embeddings = embs / norms
            print(f"[✓] Indexed {len(self.chunks)} verified clinical chunks!")

    def retrieve(self, query: str, top_k: int = 1) -> str:
        if not self.chunks or self.embeddings is None:
            return ""
        qv = self.encoder.encode([query], convert_to_numpy=True)[0]
        qn = np.linalg.norm(qv)
        if qn > 0:
            qv = qv / qn
        scores = np.dot(self.embeddings, qv)
        top = np.argsort(scores)[::-1][:top_k]
        return self.chunks[top[0]][:350]


rag = PartitionedMedicalRAG(PDF_FILE_PATH)

# =========================================================
# 2. FASTAPI SETUP
# =========================================================
app = FastAPI(title="SwasthyaMitra Backend")
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
    gender: Optional[str] = "Male"
    image_data: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    history: Optional[List[MessageItem]] = []


SYSTEM_PROMPT = """You are "Dr. SwasthyaMitra", an empathetic clinical AI physician.
Patient Profile: {age} years old, {gender}.

FORMATTING RULES:
1. Start the first line strictly with one triage tag: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. DO NOT use ASCII markdown tables (pipes '|' or table dividers).
3. Use clean bold headings and concise bullet points.
4. Structure your response:
   - 🩺 Clinical Overview: Clear explanation.
   - 🔍 Key Facts / Biological Context: Address gender and age anatomy directly (e.g. if a condition like phimosis is male-only, explicitly state that it cannot occur in females).
   - 💊 Immediate Care & Home Remedies: Safe steps.
   - ⚠️ When to consult a Doctor / Red flags.
   - ❓ Diagnostic Follow-Up: Ask exactly 1 relevant question at the end.

5. NON-HEALTH GUARDRAIL: If query is completely unrelated to healthcare, medicine, anatomy, lab tests, or nutrition, politely decline and instruct to ask medical questions only.

Respond in {language}.

Reference Context:
{context}
"""


def extract_triage_severity(text: str):
    if "[SEVERITY: EMERGENCY]" in text:
        return "EMERGENCY", text.replace("[SEVERITY: EMERGENCY]", "").strip()
    elif "[SEVERITY: MODERATE]" in text:
        return "MODERATE", text.replace("[SEVERITY: MODERATE]", "").strip()
    elif "[SEVERITY: MILD]" in text:
        return "MILD", text.replace("[SEVERITY: MILD]", "").strip()
    return "MILD", text


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    q = req.message.strip()
    lang = req.language or "Hinglish"
    
    try:
        age_int = int(str(req.age).split()[0]) if req.age else 24
    except Exception:
        age_int = 24

    gender_str = str(req.gender) if req.gender else "Male"

    # Fast Greeting Handler
    if q.lower() in ["hi", "hello", "hey", "namaste", "hii", "hlo"]:
        return {
            "reply": "Namaste! 🙏 Main Dr. SwasthyaMitra hoon. Aapko kya health problem, symptom ya medical question hai?",
            "triage": "MILD"
        }

    # Hospital Shortcut
    if any(k in q.lower() for k in ["hospital", "clinic", "aspatal", "doctor nearby"]):
        if req.latitude and req.longitude:
            link = f"https://www.google.com/maps/search/hospitals+near+me/@{req.latitude},{req.longitude},14z"
            return {
                "reply": f"🏥 **Nearby Hospitals:**\n👉 [📍 Open Google Maps Directions]({link})\n🚨 Emergency: Call **108**.",
                "triage": "MODERATE"
            }
        return {"reply": "📍 Please allow location access to see hospitals near you.", "triage": "MILD"}

    ctx = rag.retrieve(q)
    prompt = SYSTEM_PROMPT.format(age=age_int, gender=gender_str, language=lang, context=ctx)

    user_text = q
    if not user_text and req.image_data:
        user_text = "Please analyze this attached medical lab test report / clinical photo."

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_text}
    ]

    last_err = ""
    for model_name in AVAILABLE_CHAT_MODELS:
        try:
            resp = groq_client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=380
            )
            raw_answer = resp.choices[0].message.content
            triage_level, clean_answer = extract_triage_severity(raw_answer)
            return {"reply": clean_answer, "triage": triage_level}
        except Exception as e:
            last_err = str(e)
            continue

    return {"reply": f"⚠️ Service busy. Error: {last_err}", "triage": "MILD"}