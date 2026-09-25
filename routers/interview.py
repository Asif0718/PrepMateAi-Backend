from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from database import interviews_collection, users_collection
from deps import ai_quota, get_current_user, to_object_id
from llm_service import evaluate_answer, generate_interview_questions
from models import AnswerIn, StartInterview

router = APIRouter(prefix="/api/interview", tags=["interview"])


def readiness(score: int) -> str:
    if score >= 80:
        return "Interview ready"
    if score >= 60:
        return "Almost there"
    return "Needs more practice"


def serialize_session(session: dict) -> dict:
    return {
        "id": str(session["_id"]),
        "role": session["role"],
        "interview_type": session["interview_type"],
        "difficulty": session["difficulty"],
        "status": session["status"],
        "questions": session["questions"],
        "overall_score": session.get("overall_score"),
        "readiness": session.get("readiness"),
        "created_at": session["created_at"].isoformat(),
    }


async def get_owned_session(session_id: str, user_id: str) -> dict:
    session = await interviews_collection.find_one(
        {"_id": to_object_id(session_id), "user_id": user_id}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")
    return session


@router.post("/start")
async def start_interview(body: StartInterview, user: dict = Depends(get_current_user)):
    db_user = await users_collection.find_one(
        {"_id": to_object_id(user["user_id"])}, {"resume_text": 1}
    )

    async with ai_quota(user["user_id"]):
        questions = await generate_interview_questions(
            role=body.role,
            job_description=body.job_description,
            resume_text=(db_user or {}).get("resume_text", ""),
            interview_type=body.interview_type,
            difficulty=body.difficulty,
            count=body.num_questions,
        )

    session = {
        "user_id": user["user_id"],
        "role": body.role,
        "interview_type": body.interview_type,
        "difficulty": body.difficulty,
        "status": "in_progress",
        "questions": [{**q, "answer": None, "evaluation": None} for q in questions],
        "created_at": datetime.utcnow(),
    }

    result = await interviews_collection.insert_one(session)
    session["_id"] = result.inserted_id

    return serialize_session(session)


@router.post("/{session_id}/answer")
async def answer_question(session_id: str, body: AnswerIn, user: dict = Depends(get_current_user)):
    session = await get_owned_session(session_id, user["user_id"])
    questions = session["questions"]

    if body.index >= len(questions):
        raise HTTPException(status_code=400, detail="Invalid question index")
    if questions[body.index].get("evaluation"):
        raise HTTPException(status_code=400, detail="This question is already answered")

    async with ai_quota(user["user_id"]):
        evaluation = await evaluate_answer(session["role"], questions[body.index]["question"], body.answer)

    questions[body.index]["answer"] = body.answer
    questions[body.index]["evaluation"] = evaluation

    updates = {
        f"questions.{body.index}.answer": body.answer,
        f"questions.{body.index}.evaluation": evaluation,
    }

    if all(q.get("evaluation") for q in questions):
        overall = round(10 * sum(q["evaluation"]["score"] for q in questions) / len(questions))
        updates.update({
            "status": "completed",
            "overall_score": overall,
            "readiness": readiness(overall),
            "completed_at": datetime.utcnow(),
        })

    await interviews_collection.update_one({"_id": session["_id"]}, {"$set": updates})

    return {
        "evaluation": evaluation,
        "completed": updates.get("status") == "completed",
        "overall_score": updates.get("overall_score"),
        "readiness": updates.get("readiness"),
    }


@router.get("/history")
async def interview_history(user: dict = Depends(get_current_user)):
    cursor = interviews_collection.find(
        {"user_id": user["user_id"]},
        {"role": 1, "interview_type": 1, "difficulty": 1, "status": 1,
         "overall_score": 1, "readiness": 1, "created_at": 1, "questions.evaluation.score": 1},
    ).sort("created_at", -1).limit(20)

    sessions = []
    async for s in cursor:
        sessions.append({
            "id": str(s["_id"]),
            "role": s["role"],
            "interview_type": s["interview_type"],
            "difficulty": s["difficulty"],
            "status": s["status"],
            "overall_score": s.get("overall_score"),
            "readiness": s.get("readiness"),
            "answered": sum(1 for q in s["questions"] if q.get("evaluation")),
            "total": len(s["questions"]),
            "created_at": s["created_at"].isoformat(),
        })

    return {"sessions": sessions}


@router.get("/{session_id}")
async def get_interview(session_id: str, user: dict = Depends(get_current_user)):
    return serialize_session(await get_owned_session(session_id, user["user_id"]))
