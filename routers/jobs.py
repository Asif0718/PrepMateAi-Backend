import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from database import applied_jobs_collection, cache_get, cache_set, job_alerts_collection, users_collection
from deps import get_current_user, get_optional_user, to_object_id
from jobs import fetch_jobs
from matching import match_score
from models import AppliedJobIn, AppliedJobUpdate, JobAlertIn

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

JOB_CACHE_SECONDS = 6 * 3600
MAX_ALERTS = 3


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
        "match_score": job.get("match_score"),
        "source": job.get("source"),
        "description": job.get("description", ""),
        "kit": job.get("kit"),
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
        "description": (job.description or "")[:3000],
        "match_score": job.match_score,
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

    now = datetime.utcnow()
    changes["updated_at"] = now
    if changes.get("status") == "applied":
        # A shortlisted job becomes a real application the moment it moves to Applied.
        await applied_jobs_collection.update_one(
            {"_id": to_object_id(job_id), "user_id": user["user_id"], "status": "shortlisted"},
            {"$set": {"applied_at": now}},
        )

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


def serialize_alert(alert: dict) -> dict:
    last_run = alert.get("last_run_at")
    return {
        "id": str(alert["_id"]),
        "query": alert["query"],
        "location": alert["location"],
        "min_score": alert.get("min_score", 60),
        "last_run_at": last_run.isoformat() if last_run else None,
    }


@router.get("/alerts")
async def list_alerts(user: dict = Depends(get_current_user)):
    cursor = job_alerts_collection.find({"user_id": user["user_id"]}, {"seen_ids": 0}).sort("created_at", 1)
    return {"alerts": [serialize_alert(a) async for a in cursor]}


@router.post("/alerts")
async def create_alert(body: JobAlertIn, user: dict = Depends(get_current_user)):
    query, location = body.query.strip(), body.location.strip()
    existing = await job_alerts_collection.find_one({
        "user_id": user["user_id"],
        "query": {"$regex": f"^{re.escape(query)}$", "$options": "i"},
        "location": {"$regex": f"^{re.escape(location)}$", "$options": "i"},
    })
    if existing:
        return {"alert": serialize_alert(existing)}

    if await job_alerts_collection.count_documents({"user_id": user["user_id"]}) >= MAX_ALERTS:
        raise HTTPException(
            status_code=400,
            detail=f"You can have up to {MAX_ALERTS} job alerts. Delete one to add another.",
        )

    alert = {
        "user_id": user["user_id"],
        "query": query,
        "location": location,
        "min_score": body.min_score,
        "seen_ids": [],
        "created_at": datetime.utcnow(),
    }
    result = await job_alerts_collection.insert_one(alert)
    alert["_id"] = result.inserted_id
    return {"alert": serialize_alert(alert)}


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, user: dict = Depends(get_current_user)):
    result = await job_alerts_collection.delete_one({"_id": to_object_id(alert_id), "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert deleted"}