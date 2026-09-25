"""Daily job alerts: run each saved search, shortlist strong matches, email the best ones.

Run once a day (see .github/workflows/reminders.yml):
    python job_alerts.py
"""
import asyncio
import html
from datetime import datetime

import httpx
from bson import ObjectId

from config import FRONTEND_URL
from database import applied_jobs_collection, cache_get, cache_set, job_alerts_collection, users_collection
from jobs import fetch_jobs
from matching import match_score
from mailer import email_enabled, send_email

JOB_CACHE_SECONDS = 6 * 3600
EMAIL_TOP = 5
SEEN_LIMIT = 300


async def jobs_for(query: str, location: str) -> list[dict]:
    # Same cache key as /api/jobs/search, so users sharing a search cost one API call.
    key = f"jobs:{query.strip().lower()}:{location.strip().lower()}"
    jobs = await cache_get(key)
    if jobs is None:
        jobs = await fetch_jobs(query, location)
        if jobs:
            await cache_set(key, jobs, JOB_CACHE_SECONDS)
    return jobs


async def run_alert(alert: dict, skills: set[str]) -> list[dict]:
    seen = dict.fromkeys(alert.get("seen_ids", []))
    new_matches = []

    for job in await jobs_for(alert["query"], alert["location"]):
        job_key = job.get("id") or f"{job.get('title')}|{job.get('company')}"
        if job_key in seen:
            continue
        seen[job_key] = None

        match = match_score(skills, f"{job.get('title') or ''}\n{job.get('description') or ''}")
        if not match or match["score"] < alert.get("min_score", 60):
            continue

        identity = {
            "user_id": alert["user_id"],
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
        }
        if await applied_jobs_collection.find_one(identity, {"_id": 1}):
            continue

        await applied_jobs_collection.insert_one({
            **identity,
            "apply_link": job.get("apply_link"),
            "description": (job.get("description") or "")[:3000],
            "match_score": match["score"],
            "status": "shortlisted",
            "source": "alert",
            "notes": "",
            "interview_date": None,
            "applied_at": datetime.utcnow(),
        })
        new_matches.append({**job, "score": match["score"]})

    await job_alerts_collection.update_one(
        {"_id": alert["_id"]},
        {"$set": {"seen_ids": list(seen)[-SEEN_LIMIT:], "last_run_at": datetime.utcnow()}},
    )
    return new_matches


def email_html(name: str, matches: list[dict]) -> str:
    rows = "".join(
        f'<li><a href="{html.escape(m.get("apply_link") or FRONTEND_URL + "/applied-jobs")}">'
        f"{html.escape(m.get('title') or 'Role')}</a> at {html.escape(m.get('company') or 'a company')}"
        f" ({m['score']}% match)</li>"
        for m in matches[:EMAIL_TOP]
    )
    more = len(matches) - EMAIL_TOP
    extra = f"<p>Plus {more} more on your board.</p>" if more > 0 else ""
    found = (
        "1 new job that matches your resume and added it"
        if len(matches) == 1
        else f"{len(matches)} new jobs that match your resume and added them"
    )
    return (
        f"<p>Hi {html.escape(name)},</p>"
        f"<p>We found {found} to the Shortlisted column of your tracker.</p><ul>{rows}</ul>{extra}"
        f'<p><a href="{FRONTEND_URL}/applied-jobs">Open your tracker</a></p>'
    )


async def main():
    per_user: dict[str, list[dict]] = {}
    skills_cache: dict[str, set[str]] = {}

    async for alert in job_alerts_collection.find({}):
        user_id = alert["user_id"]
        if user_id not in skills_cache:
            user = await users_collection.find_one({"_id": ObjectId(user_id)}, {"resume_skills": 1})
            skills_cache[user_id] = set((user or {}).get("resume_skills", []))
        if not skills_cache[user_id]:
            continue

        matches = await run_alert(alert, skills_cache[user_id])
        if matches:
            per_user.setdefault(user_id, []).extend(matches)
        print(f"alert {alert['query']} / {alert['location']}: {len(matches)} new")

    if not per_user or not email_enabled():
        return

    async with httpx.AsyncClient(timeout=20) as client:
        for user_id, matches in per_user.items():
            user = await users_collection.find_one({"_id": ObjectId(user_id)}, {"email": 1, "name": 1})
            if not user:
                continue
            matches.sort(key=lambda m: m["score"], reverse=True)
            status = await send_email(
                client,
                user,
                f"{len(matches)} new job match{'es' if len(matches) > 1 else ''} for you",
                email_html(user.get("name", ""), matches),
            )
            print(user["email"], status)


if __name__ == "__main__":
    asyncio.run(main())
