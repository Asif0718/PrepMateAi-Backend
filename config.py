import os

from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY") or "mysecretkey"
if SECRET_KEY == "mysecretkey":
    print("WARNING: SECRET_KEY is not set, using an insecure default")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

# Comma-separated "provider:model" list, tried in order until one answers.
# Providers without an API key are skipped.
LLM_CHAIN = os.getenv(
    "LLM_CHAIN",
    "groq:openai/gpt-oss-120b,"
    "openrouter:nvidia/nemotron-3-super-120b-a12b:free,"
    "groq:qwen/qwen3.8-27b,"
    "gemini:gemini-3.5-flash-lite,"
    "openrouter:qwen/qwen3.8-27b:free,"
    "openrouter:google/gemma-4-31b-it:free,"
    "groq:openai/gpt-oss-20b",
)

AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "25"))

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://prep-mate-ai-frontend.vercel.app")
