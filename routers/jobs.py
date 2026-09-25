from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from database import applied_jobs_collection, cache_get, cache_set, users_collection
from deps import get_current_user, get_optional_user, to_object_id
from jobs import fetch_jobs
from matching import match_score
from models import AppliedJobIn, AppliedJobUpdate

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

JOB_CACHE_SECONDS = 6 * 3600


def serialize_applied_job(job: dict) -> dict:
    applied_at = job.get("applied_at")
    return {
        "id": str(job["_id"]),
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "apply_link": job.get("apply_link"),
        "status": job.get("status", "applied"),
        "notes": job.get("notes", ""),
        "interview_date": job.get("interview_date"),
        "applied_at": applied_at.isoformat() if applied_at else None,
    }


@router.get("/search")
async def search_jobs(
    query: str = "MERN Stack Developer",
    location: str = "India",
    user: dict | None = Depends(get_optional_user),
):
    cache_key = f"jobs:{query.strip().lower()}:{location.strip().lower()}"
    jobs = await cache_get(cache_key)

    if jobs is None:
        jobs = await fetch_jobs(query, location)
        if jobs:
            await cache_set(cache_key, jobs, JOB_CACHE_SECONDS)

    resume_skills = set()
    if user:
        db_user = await users_collection.find_one(
            {"_id": to_object_id(user["user_id"])}, {"resume_skills": 1}
        )
        resume_skills = set((db_user or {}).get("resume_skills", []))

    if resume_skills:
        jobs = [
            {**job, "match": match_score(resume_skills, f"{job.get('title') or ''}\n{job.get('description') or ''}")}
            for job in jobs
        ]
        jobs.sort(key=lambda job: (job["match"] or {}).get("score", -1), reverse=True)

    return {
        "query": query,
        "location": location,
        "has_resume": bool(resume_skills),
        "jobs": jobs,
    }


@router.post("/applied")
async def save_applied_job(job: AppliedJobIn, user: dict = Depends(get_current_user)):
    identity = {
        "user_id": user["user_id"],
        "title": job.title,
        "company": job.company,
        "location": job.location,
    }

    existing = await applied_jobs_collection.find_one(identity)
    if existing:
        return {"message": "Job already tracked", "job": serialize_applied_job(existing)}

    job_data = {
        **identity,
        "apply_link": job.apply_link,
        "status": "applied",
        "notes": "",
        "interview_date": None,
        "applied_at": datetime.utcnow(),
    }

    result = await applied_jobs_collection.insert_one(job_data)
    job_data["_id"] = result.inserted_id

    return {"message": "Job marked as applied", "job": serialize_applied_job(job_data)}


@router.get("/applied")
async def get_applied_jobs(user: dict = Depends(get_current_user)):
    cursor = applied_jobs_collection.find({"user_id": user["user_id"]}).sort("applied_at", -1)
    return {"applied_jobs": [serialize_applied_job(job) async for job in cursor]}


@router.patch("/applied/{job_id}")
async def update_applied_job(job_id: str, body: AppliedJobUpdate, user: dict = Depends(get_current_user)):
    changes = body.model_dump(exclude_unset=True)
    if "interview_date" in changes:
        changes["interview_date"] = changes["interview_date"] or None
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")

    changes["updated_at"] = datetime.utcnow()

    job = await applied_jobs_collection.find_one_and_update(
        {"_id": to_object_id(job_id), "user_id": user["user_id"]},
        {"$set": changes},
        return_document=True,
    )

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"job": serialize_applied_job(job)}


@router.delete("/applied/{job_id}")
async def delete_applied_job(job_id: str, user: dict = Depends(get_current_user)):
    result = await applied_jobs_collection.delete_one(
        {"_id": to_object_id(job_id), "user_id": user["user_id"]}
    )

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"message": "Job removed"}
