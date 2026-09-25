from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from auth import create_token, hash_password, verify_password
from database import users_collection
from deps import get_current_user, to_object_id
from models import LoginUser, RegisterUser

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
async def register(user: RegisterUser):
    existing_user = await users_collection.find_one({"email": user.email}, {"_id": 1})

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = {
        "name": user.name,
        "email": user.email,
        "password": await run_in_threadpool(hash_password, user.password),
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


@router.post("/login")
async def login(user: LoginUser):
    db_user = await users_collection.find_one({"email": user.email}, {"password": 1, "email": 1})

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not await run_in_threadpool(verify_password, user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token({
        "user_id": str(db_user["_id"]),
        "email": db_user["email"]
    })

    return {
        "message": "Login successful",
        "token": token
    }


@router.get("/me")
async def get_current_user_profile(user: dict = Depends(get_current_user)):
    db_user = await users_collection.find_one(
        {"_id": to_object_id(user["user_id"])},
        {"name": 1, "email": 1, "resume_file": 1, "resume_skills": 1},
    )

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "name": db_user["name"],
        "email": db_user["email"],
        "resume_file": db_user.get("resume_file"),
        "resume_skills": db_user.get("resume_skills", []),
    }
