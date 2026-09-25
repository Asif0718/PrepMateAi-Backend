import os
from datetime import datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv


load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")

client = AsyncIOMotorClient(MONGO_URL)

db = client["ai_placement_db"]

users_collection = db["users"]
resumes_collection = db["resumes"]
applied_jobs_collection = db["applied_jobs"]
interviews_collection = db["interviews"]
cache_collection = db["cache"]
usage_collection = db["ai_usage"]


async def check_mongo_connection():
    try:
        await client.admin.command("ping")
        print("MongoDB connected successfully")
        return True
    except Exception as e:
        print("MongoDB connection failed:", e)
        return False


async def ensure_indexes():
    await users_collection.create_index("email")
    await resumes_collection.create_index([("user_id", 1), ("uploaded_at", -1)])
    await applied_jobs_collection.create_index([("user_id", 1), ("applied_at", -1)])
    await interviews_collection.create_index([("user_id", 1), ("created_at", -1)])
    await cache_collection.create_index("expires_at", expireAfterSeconds=0)
    await usage_collection.create_index("expires_at", expireAfterSeconds=0)


async def cache_get(key: str):
    doc = await cache_collection.find_one({"_id": key})
    if doc and doc["expires_at"] > datetime.utcnow():
        return doc["value"]
    return None


async def cache_set(key: str, value, ttl_seconds: int):
    await cache_collection.update_one(
        {"_id": key},
        {"$set": {"value": value, "expires_at": datetime.utcnow() + timedelta(seconds=ttl_seconds)}},
        upsert=True,
    )
