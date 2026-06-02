from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = "mongodb+srv://asif:asif2005@cluster0.sj1tmvh.mongodb.net/?appName=Cluster0"

client = AsyncIOMotorClient(MONGO_URL)

db = client["ai_placement_db"]

users_collection = db["users"]
resumes_collection = db["resumes"]
applied_jobs_collection = db["applied_jobs"]


async def check_mongo_connection():
    try:
        await client.admin.command("ping")
        print("MongoDB connected successfully")
        return True
    except Exception as e:
        print("MongoDB connection failed:", e)
        return False