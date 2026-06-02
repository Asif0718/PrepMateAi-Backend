from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import os
import shutil
from bson import ObjectId
from jobs import fetch_jobs



from database import users_collection, resumes_collection
from database import applied_jobs_collection

from models import RegisterUser, LoginUser
from auth import hash_password, verify_password, create_token, decode_token

from pdf_reader import extract_text_from_pdf
from llm_service import generate_preparation_guide

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def home():
    return {"message": "FastAPI backend running"}


@app.post("/api/auth/register")
async def register(user: RegisterUser):
    existing_user = await users_collection.find_one({"email": user.email})

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = {
        "name": user.name,
        "email": user.email,
        "password": hash_password(user.password),
        "created_at": datetime.utcnow()
    }

    result = await users_collection.insert_one(new_user)

    token = create_token({
        "user_id": str(result.inserted_id),
        "email": user.email
    })

    return {
        "message": "User registered successfully",
        "token": token
    }


@app.post("/api/auth/login")
async def login(user: LoginUser):
    db_user = await users_collection.find_one({"email": user.email})

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token({
        "user_id": str(db_user["_id"]),
        "email": db_user["email"]
    })

    return {
        "message": "Login successful",
        "token": token
    }


@app.post("/api/resume/upload")
async def upload_resume(
    resume: UploadFile = File(...),
    jobDescription: str = Form(...),
    authorization: str = Header(None)
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token missing")

    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload["user_id"]

    file_path = os.path.join(UPLOAD_DIR, resume.filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(resume.file, buffer)

        resume_text = extract_text_from_pdf(file_path)

        if not resume_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")

        preparation_guide = generate_preparation_guide(
            resume_text,
            jobDescription
        )

        resume_data = {
            "user_id": user_id,
            "resume_file": resume.filename,
            "job_description": jobDescription,
            "preparation_guide": preparation_guide,
            "uploaded_at": datetime.utcnow()
        }

        await resumes_collection.insert_one(resume_data)

        return {
            "message": "Resume analyzed successfully",
            "resume_file": resume.filename,
            "preparation_guide": preparation_guide
        }

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.get("/api/resume/history")
async def get_resume_history(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token missing")

    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload["user_id"]

    history = []
    cursor = resumes_collection.find({"user_id": user_id}).sort("uploaded_at", -1)

    async for item in cursor:
        uploaded_at = item.get("uploaded_at")

        history.append({
            "id": str(item["_id"]),
            "resume_file": item.get("resume_file"),
            "job_description": item.get("job_description"),
            "preparation_guide": item.get("preparation_guide"),
            "uploaded_at": uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if uploaded_at else ""
        })

    return {"history": history}


@app.delete("/api/resume/history/{history_id}")
async def delete_resume_history(history_id: str, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token missing")

    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload["user_id"]

    result = await resumes_collection.delete_one({
        "_id": ObjectId(history_id),
        "user_id": user_id
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="History not found")

    return {"message": "History deleted successfully"}

@app.get("/api/auth/me")
async def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token missing")

    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await users_collection.find_one({"email": payload["email"]})

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "name": user["name"],
        "email": user["email"]
    }






@app.get("/api/jobs/search")
def search_jobs(query: str = "MERN Stack Developer", location: str = "India"):
    jobs = fetch_jobs(query, location)
    return {
        "query": query,
        "location": location,
        "jobs": jobs
    }


@app.post("/api/jobs/applied")
async def save_applied_job(job: dict, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token missing")

    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    job_data = {
        "user_id": payload["user_id"],
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "apply_link": job.get("apply_link"),
        "applied_at": datetime.utcnow()
    }

    await applied_jobs_collection.insert_one(job_data)

    return {"message": "Job marked as applied"}


@app.get("/api/jobs/applied")
async def get_applied_jobs(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token missing")

    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    jobs = []
    cursor = applied_jobs_collection.find({"user_id": payload["user_id"]}).sort("applied_at", -1)

    async for job in cursor:
        jobs.append({
            "id": str(job["_id"]),
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "apply_link": job.get("apply_link"),
            "applied_at": job.get("applied_at").strftime("%Y-%m-%d %H:%M:%S")
        })

    return {"applied_jobs": jobs}