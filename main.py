import os
import re
from typing import List, Optional, Union, Dict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
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
# ULTRA-LIGHTWEIGHT RAG ENGINE (< 40MB RAM - No OOM Crash)
# =========================================================
class LightweightMedicalRAG:
    def __init__(self, pdf_path: str):
        print("[*] Initializing Lightweight Medical Knowledge Base...")
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
                "Pediatric fever and dehydration require oral rehydration solutions and urgent doctor consult if high."
            ]

        self.chunks = raw
        print(f"[✓] Successfully indexed {len(self.chunks)} clinical chunks in memory!")

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
# FASTAPI BACKEND
# =========================================================
app = FastAPI(title="SwasthyaMitra API")
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

GUIDELINES:
1. Start the first line strictly with: [SEVERITY: MILD], [SEVERITY: MODERATE], or [SEVERITY: EMERGENCY].
2. Structure your response clearly:
   - 🩺 Clinical Overview: Simple explanation.
   - 🔍 Key Facts / Biological Context: Address gender and age anatomy explicitly (e.g. if condition like phimosis is male-only, clearly state it cannot happen to females).
   - 💊 Immediate Care & Safe Measures.
   - ⚠️ When to consult a Doctor / Emergency (108/112).
   - ❓ Diagnostic Follow-Up: Ask 1 relevant question at the end.

3. NON-HEALTH GUARDRAIL: If query is completely unrelated to health/medicine, politely refuse.
4. DO NOT use ASCII pipe tables. Respond politely in {language}.

Context: {context}"""


def extract_triage_severity(text: str):
    if "[SEVERITY: EMERGENCY]" in text:
        return "EMERGENCY", text.replace("[SEVERITY: EMERGENCY]", "").strip()
    elif "[SEVERITY: MODERATE]" in text:
        return "MODERATE", text.replace("[SEVERITY: MODERATE]", "").strip()
    elif "[SEVERITY: MILD]" in text:
        return "MILD", text.replace("[SEVERITY: MILD]", "").strip()
    return "MILD", text


@app.get("/")
def health_check():
    return {"status": "online", "service": "SwasthyaMitra AI"}


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    q = req.message.strip()
    lang = req.language or "Hinglish"

    try:
        age_int = int(str(req.age).split()[0]) if req.age else 24
    except Exception:
        age_int = 24

    gender_str = str(req.gender) if req.gender else "Male"

    if q.lower() in ["hi", "hello", "hey", "namaste", "hii", "hlo"]:
        return {
            "reply": "Namaste! 🙏 Main Dr. SwasthyaMitra hoon. Aapko kya health concern ya medical query hai?",
            "triage": "MILD"
        }

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
