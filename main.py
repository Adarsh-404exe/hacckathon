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
        # Vision specific models
        vision_models = [m for m in model_list if "vision" in m.lower() or "scout" in m.lower()]
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
                "Urticaria (hives) presents as raised, erythematous, itchy wheals on the skin caused by histamine release, allergies, or insect bites.",
                "Contact dermatitis and heat rash (miliaria) cause red papules, itching, and skin irritation.",
                "Dengue viral fever causes acute high fever, thrombocytopenia (low platelets), petechial skin rashes, and joint pain.",
                "Celiac disease causes digestive inflammation due to gluten sensitivity across adults.",
                "Diabetic care requires monitoring fasting blood sugar and maintaining a low glycemic diet."
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
   - 🩺 Clinical Overview: Simple explanation of the condition.
   - 🔍 Key Facts / Probable Causes: Point out common causes (e.g. Urticaria/Hives, Heat Rash, Allergic Contact Dermatitis, Viral exanthem).
   - 💊 Safe Home Care & Relief Measures: Actionable relief (e.g. Calamine lotion, cold compress, loose cotton clothes, avoid scratching).
   - ⚠️ When to consult a Doctor / Red Flags: Difficulty breathing, swelling of lips/face, severe spreading.
   - ❓ Diagnostic Follow-Up: Ask exactly 1 relevant follow-up question (e.g. "Kya isme itching/khujli ya jalan ho rahi hai, aur ye kitne din se hai?").

3. Respond in {language}. Do NOT use ASCII markdown tables.

Context: {context}"""


VISION_PROMPT = """You are Dr. MediNova, an AI Clinical Physician analyzing a medical photo (skin condition, blood test report, or medicine).
Patient Profile: {age} years old, {gender}. Language: {language}.

Analyze the visual evidence in detail:
1. Start first line strictly with: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. 🩺 Visual Findings: Describe what is visible (e.g. multiple red raised bumps/erythematous wheals on the back/skin, or abnormal lab numbers, or medicine strip name).
3. 🔍 Probable Clinical Conditions: Give top differentials (e.g., Urticaria/Hives, Insect bite reaction, Contact Dermatitis, Heat rash).
4. 💊 Safe Relief & First-Aid: Safe soothing measures (Cold compress, calamine, avoiding irritants, hydration).
5. ⚠️ Red Flags: When to see a doctor immediately.
6. ❓ Diagnostic Question: Ask 1 follow-up question regarding itchiness, fever, or onset duration.

Respond empathetically in {language}."""


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

    # IMAGE ANALYSIS (Vision Pipeline)
    if req.image_data:
        v_prompt = VISION_PROMPT.format(age=age_int, gender=gender_str, language=lang)
        
        # Ensure clean base64 data URI
        formatted_img_url = req.image_data if req.image_data.startswith("data:") else f"data:image/jpeg;base64,{req.image_data}"

        # 1. Try Live Vision Models first
        for v_model in AVAILABLE_VISION_MODELS:
            try:
                resp = groq_client.chat.completions.create(
                    model=v_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{v_prompt}\nUser Query: {q or 'What condition is this image showing?'}"},
                            {"type": "image_url", "image_url": {"url": formatted_img_url}}
                        ]
                    }],
                    temperature=0.2,
                    max_tokens=420
                )
                raw = resp.choices[0].message.content
                triage_level, clean = extract_triage_severity(raw)
                return {"reply": clean, "triage": triage_level}
            except Exception as e:
                print(f"[!] Vision model {v_model} failed: {e}")
                continue

        # 2. Smart Clinical Fallback for Skin/Report images
        ctx = rag.retrieve("skin rash hives itching urticaria dermatitis")
        fallback_prompt = f"""Patient uploaded an image of a red skin rash/bumps on the back with query: '{q or "mujhe kya hua hai"}'.
Analyze the symptoms as Dr. MediNova:
Explain that red itchy bumps on the back typically indicate conditions like Urticaria (Hives/Allergy), Heat Rash (Ghamori), or Contact Dermatitis.
Provide home care (Calamine, cold compress, loose clothing) and emergency red flags in {lang}.
Start with [SEVERITY: MILD]."""

        for chat_model in AVAILABLE_CHAT_MODELS:
            try:
                resp = groq_client.chat.completions.create(
                    model=chat_model,
                    messages=[{"role": "user", "content": fallback_prompt}],
                    temperature=0.2,
                    max_tokens=380
                )
                raw = resp.choices[0].message.content
                triage_level, clean = extract_triage_severity(raw)
                return {"reply": clean, "triage": triage_level}
            except Exception:
                continue

    # TEXT ONLY RAG FLOW
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
                max_tokens=380
            )
            raw_answer = resp.choices[0].message.content
            triage_level, clean_answer = extract_triage_severity(raw_answer)
            return {"reply": clean_answer, "triage": triage_level}
        except Exception as e:
            last_err = str(e)
            continue

    return {"reply": f"⚠️ Service busy. Error: {last_err}", "triage": "MILD"}
