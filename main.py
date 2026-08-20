import os
import re
import base64
from io import BytesIO
from typing import List, Optional, Union, Dict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
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
                print(f"[!] PDF reading notice: {e}")

        if not raw:
            raw = [
                "Paracetamol (Acetaminophen) is an analgesic and antipyretic used to reduce fever and mild to moderate pain.",
                "Amoxicillin and Azithromycin are broad-spectrum antibiotics used for bacterial infections under medical prescription.",
                "Cetirizine, Levocetirizine, and Calamine lotion provide symptomatic relief from allergic rashes, urticaria, and itching.",
                "Dengue fever presents with acute high fever, thrombocytopenia (low platelets), and severe joint pain.",
                "Antacid medications and Pantoprazole reduce gastric acid secretion and treat GERD / heartburn."
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
            return " ".join(top_chunks)[:400]
        return self.chunks[0][:300]


rag = LightweightMedicalRAG(PDF_FILE_PATH)

# =========================================================
# FASTAPI APP SETUP
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
    gender: Optional[str] = "Male"
    image_data: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    history: Optional[List[MessageItem]] = []


SYSTEM_PROMPT = """You are "Dr. MediNova", a compassionate clinical AI physician.
Patient Profile: {age} years old, {gender}.

GUIDELINES:
1. Start the first line strictly with: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. Structure your response clearly:
   - 🩺 Clinical Overview: Explain the condition, medicine, or symptom clearly.
   - 🔍 Key Facts / Medical Insights: Explain active ingredients, causes, or indications.
   - 💊 Safe Usage / Home Care: Actionable directions and safety cautions.
   - ⚠️ Warnings & Doctor Consultation: Mention side effects, contraindications, or emergency red flags.
   - ❓ Diagnostic Follow-Up: Ask exactly 1 relevant follow-up question.

3. Respond in {language}. Do NOT use ASCII pipe tables."""


VISION_PROMPT = """You are Dr. MediNova, an expert clinical physician and pharmacologist.
Patient Profile: {age} years old, {gender}. Language: {language}.
User's Question: "{query}"

Carefully analyze the attached image and answer specifically based on what is shown:
1. Start first line strictly with [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. If it is a MEDICINE / STRIP / SYRUP:
   - 💊 Medicine Identification: Identify brand name, active salt/composition, and drug class.
   - 🎯 Primary Medical Uses: What conditions or diseases this medicine treats.
   - 📋 How it works & General Guidelines: When it is taken (with/after food), precautions.
   - ⚠️ Common Side Effects & Contraindications: Who should avoid it (e.g. pregnancy, kidney/liver issues).
   - ❓ Diagnostic Question: Ask 1 follow-up question about their prescription or symptoms.
3. If it is a LAB / BLOOD REPORT:
   - 🧪 Key Findings: Highlight abnormal values (High/Low) and explain their clinical meaning.
4. If it is a SKIN RASH / WOUND / PHYSICAL SYMPTOM:
   - 🔬 Visual Observations: Describe rash/bump appearance and likely differentials (e.g. Urticaria, Dermatitis).

Respond accurately and empathetically in {language}."""


def extract_triage_severity(text: str):
    if "[SEVERITY: EMERGENCY]" in text:
        return "EMERGENCY", text.replace("[SEVERITY: EMERGENCY]", "").strip()
    elif "[SEVERITY: MODERATE]" in text:
        return "MODERATE", text.replace("[SEVERITY: MODERATE]", "").strip()
    elif "[SEVERITY: MILD]" in text:
        return "MILD", text.replace("[SEVERITY: MILD]", "").strip()
    return "MILD", text


# 1. SERVE FRONTEND
@app.get("/")
def serve_index():
    return FileResponse("index.html")

@app.get("/style.css")
def serve_css():
    return FileResponse("style.css")

@app.get("/app.js")
def serve_js():
    return FileResponse("app.js")


# 2. CHAT API ENDPOINT
@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    q = req.message.strip()
    lang = req.language or "Hinglish"

    try:
        age_int = int(str(req.age).split()[0]) if req.age else 24
    except Exception:
        age_int = 24

    gender_str = str(req.gender) if req.gender else "Male"

    # Fast Greeting
    if q.lower() in ["hi", "hello", "hey", "namaste", "hii", "hlo"] and not req.image_data:
        return {
            "reply": "Namaste! 🙏 Main Dr. MediNova hoon. Aap medicine strip, blood report, ya skin rash ki photo scan karwa sakte hain, ya apna koi symptom likh sakte hain.",
            "triage": "MILD"
        }

    # Hospital directions
    if any(k in q.lower() for k in ["hospital", "clinic", "aspatal", "doctor nearby"]):
        if req.latitude and req.longitude:
            link = f"https://www.google.com/maps/search/hospitals+near+me/@{req.latitude},{req.longitude},14z"
            return {
                "reply": f"🏥 **Nearby Hospitals:**\n👉 [📍 Open Google Maps Directions]({link})\n🚨 Emergency: Call **108**.",
                "triage": "MODERATE"
            }
        return {"reply": "📍 Please allow location access to see hospitals near you.", "triage": "MILD"}

    # IMAGE ANALYSIS PIPELINE
    if req.image_data:
        user_query = q if q else "Identify and explain this medicine, medical report, or condition in detail."
        v_prompt = VISION_PROMPT.format(age=age_int, gender=gender_str, language=lang, query=user_query)
        formatted_img_url = req.image_data if req.image_data.startswith("data:") else f"data:image/jpeg;base64,{req.image_data}"

        # 1. Attempt Multimodal Vision Models
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
                    max_tokens=450
                )
                raw = resp.choices[0].message.content
                triage_level, clean = extract_triage_severity(raw)
                return {"reply": clean, "triage": triage_level}
            except Exception as e:
                print(f"[!] Vision model {v_model} failed: {e}")
                continue

        # 2. Dynamic Clinical Text Fallback (Query-aware, not hardcoded)
        ctx = rag.retrieve(user_query)
        dynamic_prompt = f"""Patient uploaded an image with question: "{user_query}".
Context reference: {ctx}
As Dr. MediNova:
- If asking about a medicine: Explain its common uses, salt, general indications, and precautions.
- If asking about symptoms: Explain likely clinical causes and safe first steps.
Start with [SEVERITY: MILD]. Respond in {lang}."""

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

    # TEXT ONLY CONVERSATION FLOW
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
                max_tokens=400
            )
            raw_answer = resp.choices[0].message.content
            triage_level, clean_answer = extract_triage_severity(raw_answer)
            return {"reply": clean_answer, "triage": triage_level}
        except Exception as e:
            last_err = str(e)
            continue

    return {"reply": f"⚠️ Service busy. Error: {last_err}", "triage": "MILD"}
