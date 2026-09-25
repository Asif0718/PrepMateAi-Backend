"""Daily email reminders for tracked applications.

Run once a day (see .github/workflows/reminders.yml):
    python reminders.py
"""
import asyncio
import html
from datetime import datetime, timedelta

import httpx
from bson import ObjectId

from config import FRONTEND_URL
from database import applied_jobs_collection, users_collection
from mailer import email_enabled, send_email

FOLLOW_UP_AFTER_DAYS = 7


def job_label(job: dict) -> str:
    return html.escape(f"{job.get('title') or 'a role'} at {job.get('company') or 'a company'}")


async def main():
    if not email_enabled():
        print("BREVO_API_KEY / BREVO_SENDER_EMAIL not set, skipping reminders")
        return

    now = datetime.utcnow()
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    reminders: dict[str, list[str]] = {}
    follow_up_ids = []

    async for job in applied_jobs_collection.find({"interview_date": tomorrow}):
        reminders.setdefault(job["user_id"], []).append(f"Interview tomorrow: {job_label(job)}")

    async for job in applied_jobs_collection.find({
        "status": {"$in": ["applied", None]},
        "applied_at": {"$lte": now - timedelta(days=FOLLOW_UP_AFTER_DAYS)},
        "followup_reminded": {"$ne": True},
    }):
        reminders.setdefault(job["user_id"], []).append(
            f"No update yet from {job_label(job)}. Consider sending a follow-up."
        )
        follow_up_ids.append(job["_id"])

    async with httpx.AsyncClient(timeout=20) as client:
        for user_id, lines in reminders.items():
            user = await users_collection.find_one({"_id": ObjectId(user_id)}, {"email": 1, "name": 1})
            if not user:
                continue

            items = "".join(f"<li>{line}</li>" for line in lines)
            status = await send_email(
                client,
                user,
                "Your job application reminders",
                f"<p>Hi {html.escape(user.get('name', ''))},</p><ul>{items}</ul>"
                f'<p><a href="{FRONTEND_URL}/applied-jobs">Open your tracker</a></p>',
            )
            print(user["email"], status)

    if follow_up_ids:
        await applied_jobs_collection.update_many(
            {"_id": {"$in": follow_up_ids}}, {"$set": {"followup_reminded": True}}
        )


if __name__ == "__main__":
    asyncio.run(main())
