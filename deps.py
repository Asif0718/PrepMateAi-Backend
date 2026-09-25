import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Header, HTTPException
from pymongo import ReturnDocument

from auth import decode_token
from config import AI_DAILY_LIMIT
from database import usage_collection


def get_current_user(authorization: str | None = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Token missing")

    payload = decode_token(authorization.replace("Bearer ", ""))
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    return payload


def get_optional_user(authorization: str | None = Header(None)) -> dict | None:
    if not authorization:
        return None
    return decode_token(authorization.replace("Bearer ", ""))


def to_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id")


def content_hash(*parts: str) -> str:
    return hashlib.sha256("\n\x00".join(parts).encode("utf-8")).hexdigest()


@asynccontextmanager
async def ai_quota(user_id: str):
    """Count one AI request against the user's daily limit, refunded if the request fails."""
    now = datetime.utcnow()
    key = {"_id": f"{user_id}:{now:%Y-%m-%d}"}
    doc = await usage_collection.find_one_and_update(
        key,
        {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": now + timedelta(days=2)}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if doc["count"] > AI_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Daily AI limit of {AI_DAILY_LIMIT} requests reached. Try again tomorrow.",
        )

    try:
        yield
    except Exception:
        await usage_collection.update_one(key, {"$inc": {"count": -1}})
        raise
