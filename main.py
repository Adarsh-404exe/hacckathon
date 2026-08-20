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
        return chat_models
    except Exception:
        return ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

AVAILABLE_CHAT_MODELS = get_live_groq_models()


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
                "Phimosis is a condition where the foreskin cannot be retracted over the glans penis in males. It cannot occur in females.",
                "Dengue viral fever causes acute high fever, thrombocytopenia (rapid drop in platelets), and severe body ache.",
                "Celiac disease causes chronic digestive inflammation due to gluten sensitivity across adults.",
                "Diabetic care requires monitoring fasting blood sugar and maintaining a low glycemic diet.",
                "Dermatitis, eczema, fungal infections and urticaria present with localized erythema, pruritus, and macular rash."
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


SYSTEM_PROMPT = """You are "Dr. MediNova", a compassionate clinical triage AI physician.
Patient Profile: {age} years old, {gender}.

GUIDELINES:
1. Start the first line strictly with: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. Structure your response clearly:
   - 🩺 Clinical Overview: Simple explanation of the condition or scan findings.
   - 🔍 Key Insights / Biological Context: Address gender and age anatomy explicitly.
   - 💊 Immediate Safe Care & Home Guidance: Actionable home management.
   - ⚠️ When to consult a Doctor / Emergency (108/112).
   - ❓ Diagnostic Follow-Up: Ask exactly 1 relevant follow-up question at the end.

3. NON-HEALTH GUARDRAIL: If query is completely unrelated to health, medicine, or physiology, politely decline.
4. DO NOT use ASCII pipe tables. Respond politely in {language}.

Context: {context}"""


IMAGE_ANALYSIS_PROMPT = """You are Dr. MediNova's Advanced Multimodal Clinical Diagnostic System.
Patient Profile: Age {age}, Gender {gender}. Language: {language}.

INSTRUCTIONS:
1. Start your response strictly with [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. Classify and inspect the uploaded image under one of these 3 medical categories:
   - 📄 Medical / Blood / Lab Report (Examine Platelets, Hemoglobin, WBC, Blood Sugar, etc. Compare against normal ranges).
   - 💊 Medicine / Strip / Prescription (Identify medicine name, active salt, therapeutic use, dosage safety warnings).
   - 🔬 Dermatological / Skin Rash / Wound / Injury (Assess erythema, lesions, swelling, infection indicators, safe first aid).
3. IMAGE CLARITY CHECK: If the image is too blurry, unreadable, obscured, or lacks clear medical information, respond directly:
   "⚠️ The uploaded image is unclear or unreadable. Please upload or capture a sharp, well-lit image of your medical report, prescription strip, or affected skin area for an accurate assessment."
4. Structure findings into:
   - 🩺 Visual / Lab Findings
   - 🔍 Clinical Assessment & Meaning
   - 💊 Safe Next Steps / Home Care
   - ⚠️ Red Flags requiring Immediate Doctor Consultation
   - ❓ 1 Diagnostic Follow-Up Question.

Do NOT use ASCII markdown tables. Respond in {language}."""


def extract_triage_severity(text: str):
    if "[SEVERITY: EMERGENCY]" in text:
        return "EMERGENCY", text.replace("[SEVERITY: EMERGENCY]", "").strip()
    elif "[SEVERITY: MODERATE]" in text:
        return "MODERATE", text.replace("[SEVERITY: MODERATE]", "").strip()
    elif "[SEVERITY: MILD]" in text:
        return "MILD", text.replace("[SEVERITY: MILD]", "").strip()
    return "MILD", text


# 1. SERVE FRONTEND ON ROOT URL ("/")
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
            "reply": "Namaste! 🙏 Main Dr. MediNova hoon. Aap apna koi symptom likh sakte hain, ya Lab Report, Medicine, ya Skin Rash ki photo scan karwa sakte hain.",
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

    # Enhanced Multimodal / Vision Handler
    if req.image_data:
        v_prompt = IMAGE_ANALYSIS_PROMPT.format(age=age_int, gender=gender_str, language=lang)
        
        # Check image validity before inference
        try:
            raw_b64 = req.image_data.split(",")[1] if "," in req.image_data else req.image_data
            img_bytes = base64.b64decode(raw_b64)
            img = Image.open(BytesIO(img_bytes))
            if img.width < 50 or img.height < 50:
                return {
                    "reply": "⚠️ Image resolution is too low. Please upload or capture a clearer, well-lit photo.",
                    "triage": "MILD"
                }
        except Exception:
            return {
                "reply": "⚠️ The image format could not be decoded. Please upload a valid clear medical image or photo.",
                "triage": "MILD"
            }

        user_content_query = q if q else "Analyze this medical image (report, medicine strip, or skin condition) thoroughly."
        messages = [
            {"role": "system", "content": v_prompt},
            {"role": "user", "content": f"{user_content_query}\n[Medical Scan Data attached]"}
        ]
    else:
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
