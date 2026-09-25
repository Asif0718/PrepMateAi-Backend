from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from database import check_mongo_connection, ensure_indexes
from llm_service import LLMUnavailable
from routers import auth, interview, jobs, resume


@asynccontextmanager
async def lifespan(app: FastAPI):
    if await check_mongo_connection():
        try:
            await ensure_indexes()
        except Exception as e:
            print("Index creation failed:", e)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://prepmateai-frontend.onrender.com",
        "https://prep-mate-ai-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LLMUnavailable)
async def llm_unavailable_handler(request: Request, exc: LLMUnavailable):
    return JSONResponse(
        status_code=503,
        content={"detail": "AI service is busy right now. Please try again in a minute."},
    )


@app.get("/")
def home():
    return {"message": "FastAPI backend running"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(resume.router)
app.include_router(jobs.router)
app.include_router(interview.router)
