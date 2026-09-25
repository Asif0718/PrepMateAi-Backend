import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from database import cache_get, cache_set, resumes_collection, users_collection
from deps import ai_quota, content_hash, get_current_user, to_object_id
from llm_service import generate_preparation_guide, tailor_resume
from matching import extract_skills
from models import TailorRequest
from pdf_reader import extract_text_from_pdf

router = APIRouter(prefix="/api/resume", tags=["resume"])

MAX_PDF_BYTES = 5 * 1024 * 1024
WEEK = 7 * 24 * 3600


@router.post("/upload")
async def upload_resume(
    resume: UploadFile = File(...),
    jobDescription: str = Form(...),
    user: dict = Depends(get_current_user),
):
    data = await resume.read()

    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="Resume must be smaller than 5 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        resume_text = await run_in_threadpool(extract_text_from_pdf, data)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read this PDF")

    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from PDF")

    cache_key = "guide:" + content_hash(resume_text, jobDescription)
    preparation_guide = await cache_get(cache_key)

    if preparation_guide is None:
        async with ai_quota(user["user_id"]):
            preparation_guide = await generate_preparation_guide(resume_text, jobDescription)
        await cache_set(cache_key, preparation_guide, WEEK)

    now = datetime.utcnow()
    resume_skills = sorted(extract_skills(resume_text))

    await asyncio.gather(
        users_collection.update_one(
            {"_id": to_object_id(user["user_id"])},
            {"$set": {
                "resume_text": resume_text[:20000],
                "resume_skills": resume_skills,
                "resume_file": resume.filename,
                "resume_updated_at": now,
            }},
        ),
        resumes_collection.insert_one({
            "user_id": user["user_id"],
            "resume_file": resume.filename,
            "job_description": jobDescription,
            "preparation_guide": preparation_guide,
            "uploaded_at": now,
        }),
    )

    return {
        "message": "Resume analyzed successfully",
        "resume_file": resume.filename,
        "resume_skills": resume_skills,
        "preparation_guide": preparation_guide,
    }


@router.get("/history")
async def get_resume_history(user: dict = Depends(get_current_user)):
    cursor = resumes_collection.find(
        {"user_id": user["user_id"]},
        {"resume_file": 1, "job_description": 1, "preparation_guide": 1, "uploaded_at": 1},
    ).sort("uploaded_at", -1).limit(50)

    history = []
    async for item in cursor:
        uploaded_at = item.get("uploaded_at")
        history.append({
            "id": str(item["_id"]),
            "resume_file": item.get("resume_file"),
            "job_description": item.get("job_description"),
            "preparation_guide": item.get("preparation_guide"),
            "uploaded_at": uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if uploaded_at else "",
        })

    return {"history": history}


@router.delete("/history/{history_id}")
async def delete_resume_history(history_id: str, user: dict = Depends(get_current_user)):
    result = await resumes_collection.delete_one({
        "_id": to_object_id(history_id),
        "user_id": user["user_id"],
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="History not found")

    return {"message": "History deleted successfully"}


@router.post("/tailor")
async def tailor_resume_for_job(body: TailorRequest, user: dict = Depends(get_current_user)):
    db_user = await users_collection.find_one(
        {"_id": to_object_id(user["user_id"])}, {"resume_text": 1}
    )
    resume_text = (db_user or {}).get("resume_text")

    if not resume_text:
        raise HTTPException(
            status_code=400,
            detail="Upload your resume on the dashboard first",
        )

    cache_key = "tailor:" + content_hash(resume_text, body.job_description)
    result = await cache_get(cache_key)

    if result is None:
        async with ai_quota(user["user_id"]):
            result = await tailor_resume(resume_text, body.job_description, body.title, body.company)
        await cache_set(cache_key, result, WEEK)

    return result
