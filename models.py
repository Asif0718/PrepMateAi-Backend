from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterUser(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginUser(BaseModel):
    email: EmailStr
    password: str


class TailorRequest(BaseModel):
    job_description: str = Field(min_length=20, max_length=20000)
    title: str = ""
    company: str = ""


JobStatus = Literal["applied", "online_test", "interview", "offer", "rejected"]


class AppliedJobIn(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    apply_link: Optional[str] = None


class AppliedJobUpdate(BaseModel):
    status: Optional[JobStatus] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    interview_date: Optional[str] = Field(default=None, pattern=r"^(\d{4}-\d{2}-\d{2})?$")


class StartInterview(BaseModel):
    role: str = Field(min_length=2, max_length=100)
    job_description: str = Field(default="", max_length=10000)
    interview_type: Literal["technical", "hr", "mixed"] = "mixed"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    num_questions: int = Field(default=5, ge=3, le=10)


class AnswerIn(BaseModel):
    index: int = Field(ge=0)
    answer: str = Field(min_length=1, max_length=5000)
