import asyncio
import json
import re
import time

from openai import AsyncOpenAI

from config import GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, LLM_CHAIN

PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", GROQ_API_KEY),
    "openrouter": ("https://openrouter.ai/api/v1", OPENROUTER_API_KEY),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", GEMINI_API_KEY),
}

_clients = {
    name: AsyncOpenAI(api_key=key, base_url=url, timeout=45, max_retries=0)
    for name, (url, key) in PROVIDERS.items()
    if key
}

MODELS = [
    (provider, model)
    for provider, model in (
        item.strip().split(":", 1) for item in LLM_CHAIN.split(",") if item.strip()
    )
    if provider in _clients
]

if not MODELS:
    raise ValueError("No LLM configured. Set GROQ_API_KEY and/or OPENROUTER_API_KEY in .env")

SYSTEM_PROMPT = "You are a helpful career preparation assistant."

_cooldown_until: dict[tuple[str, str], float] = {}


class LLMUnavailable(Exception):
    pass


async def chat(prompt: str, max_tokens: int = 800, temperature: float = 0.4, parse=None):
    """Try each model in LLM_CHAIN until one returns a usable answer.

    Models that fail are skipped for a short cooldown so users don't wait on
    a provider that is rate-limited. If `parse` is given, a response it
    rejects counts as a failure and the next model is tried.
    """
    now = time.monotonic()
    fresh = [m for m in MODELS if _cooldown_until.get(m, 0) <= now]
    # Free-tier overloads usually clear within seconds, so give every model one more try.
    attempts = fresh + [None] + MODELS

    for attempt in attempts:
        if attempt is None:
            await asyncio.sleep(2)
            continue
        provider, model = attempt
        extra_body = {}
        if "gpt-oss" in model:
            extra_body["reasoning_effort"] = "low"
        if provider == "openrouter":
            extra_body["reasoning"] = {"exclude": True}
        try:
            response = await _clients[provider].chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body or None,
            )
            if not response.choices:
                raise ValueError(f"no choices: {(response.model_extra or {}).get('error')}")
            content = response.choices[0].message.content or ""
            content = content.rsplit("</think>", 1)[-1].strip()
            if not content:
                raise ValueError("empty response")
            return parse(content) if parse else content
        except Exception as e:
            rate_limited = getattr(e, "status_code", None) == 429
            _cooldown_until[(provider, model)] = time.monotonic() + (60 if rate_limited else 20)
            print(f"LLM {provider}:{model} failed: {type(e).__name__}: {e}")

    raise LLMUnavailable("All AI models are busy")


def parse_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON object in response")
    return json.loads(match.group(0))


def _parse_guide(text: str) -> str:
    # Some free models leak their planning text before the first section heading.
    heading = re.search(r"^### ", text, re.M)
    if not heading:
        raise ValueError("guide has no section headings")
    return text[heading.start():]


async def generate_preparation_guide(resume_text, job_description):
    resume_text = resume_text[:6000]
    job_description = job_description[:3000]

    prompt = f"""
You are an AI placement preparation assistant.

Analyze the resume and job description.

Resume:
{resume_text}

Job Description:
{job_description}

Give output in this format, and start every section heading with "### " (for example "### 1. Candidate Summary"):

1. Candidate Summary
2. Skills Found in Resume
3. Skills Required in Job Description
4. Skill Gaps
5. Topics to Prepare
6. Technical Interview Questions
7. HR Interview Questions
8. 7-Day Preparation Plan
9. Best Learning Resources

For section 9, follow this EXACT format:

After comparing the most recommended interview resources, provide ONE best learning resource for each day.

Format:

Day 1 – <Topic>
Best Resource: <Video Title>
Link: <Official YouTube URL>

Why?
<One or two lines>

Day 2 – <Topic>
Best Resource: <Video Title>
Link: <Official YouTube URL>

Why?
<One or two lines>

...

Day 7 – <Topic>
Best Resource: <Video Title>
Link: <Official YouTube URL>

Why?
<One or two lines>

Finally provide a section called "Bonus Resources"

Include only the best official resources such as:
- NeetCode
- take U forward (Striver)
- freeCodeCamp
- Programming with Mosh
- Bro Code
- Codevolution
- Web Dev Simplified
- Linda Raynier
- GeeksforGeeks
- React Official Documentation
- FastAPI Documentation
- MongoDB Documentation
- MDN Web Docs

IMPORTANT:
- Give only ONE best resource for each topic.
- Prefer official YouTube links.
- Do NOT generate fake or broken URLs.
- Keep the answer concise and interview-focused.

"""

    return await chat(prompt, max_tokens=2200, parse=_parse_guide)


def _parse_tailoring(text: str) -> dict:
    data = parse_json_object(text)
    return {
        "match_summary": str(data.get("match_summary", "")),
        "missing_keywords": [str(k) for k in data.get("missing_keywords", [])][:12],
        "improved_summary": str(data.get("improved_summary", "")),
        "bullet_rewrites": [
            {"original": str(b.get("original", "")), "improved": str(b.get("improved", ""))}
            for b in data.get("bullet_rewrites", [])
            if isinstance(b, dict) and b.get("improved")
        ][:5],
        "tips": [str(t) for t in data.get("tips", [])][:4],
    }


async def tailor_resume(resume_text: str, job_description: str, title: str = "", company: str = ""):
    prompt = f"""
Tailor this candidate's resume for the job below so it passes ATS keyword screening.

Job: {title} at {company}
Job Description:
{job_description[:3000]}

Resume:
{resume_text[:5000]}

Rules:
- Never invent experience, employers, degrees or skills the candidate does not have.
- Reuse the job's exact keywords only where the resume truthfully supports them.
- Rewrite at most 5 of the weakest resume bullets using action verbs and measurable impact.

Return ONLY valid JSON, no markdown, in this shape:
{{
  "match_summary": "2 sentences on how well the candidate fits",
  "missing_keywords": ["important job keywords missing from the resume"],
  "improved_summary": "a 3-line professional summary tailored to this job",
  "bullet_rewrites": [{{"original": "bullet from resume", "improved": "rewritten bullet"}}],
  "tips": ["short actionable tips"]
}}
"""
    return await chat(prompt, max_tokens=1400, temperature=0.3, parse=_parse_tailoring)


KIT_QUESTIONS = [
    "Why do you want to join {company}?",
    "Why are you a good fit for this role?",
    "Tell us about a project you are proud of.",
    "What are your key strengths?",
]


def _parse_kit(text: str) -> dict:
    data = parse_json_object(text)
    kit = {
        "cover_letter": str(data.get("cover_letter", "")).strip(),
        "recruiter_message": str(data.get("recruiter_message", "")).strip(),
        "answers": [
            {"question": str(a["question"]), "answer": str(a.get("answer", "")).strip()}
            for a in data.get("answers", [])
            if isinstance(a, dict) and a.get("question") and a.get("answer")
        ][:6],
    }
    if not kit["cover_letter"] or not kit["answers"]:
        raise ValueError("incomplete application kit")
    return kit


async def generate_application_kit(resume_text: str, job_description: str, title: str, company: str):
    company = company or "the company"
    questions = "\n".join(f"- {q.format(company=company)}" for q in KIT_QUESTIONS)
    prompt = f"""
Write a job application kit for this candidate, applying to "{title or 'this role'}" at {company}.

Job Description:
{job_description[:3000] or "Not provided"}

Resume:
{resume_text[:5000]}

Rules:
- Use only facts from the resume. Never invent experience, employers, numbers or skills,
  and never state years of experience unless the resume states them.
- Write in first person, plain and confident, no clichés like "I am writing to express my interest".
- Cover letter: 150-220 words, 3 short paragraphs, no address block, no placeholders in brackets.
- Recruiter message: under 80 words, suitable for LinkedIn or email, ends with a clear ask.
- Answer each of these application questions in 60-110 words:
{questions}

Return ONLY valid JSON, no markdown:
{{
  "cover_letter": "...",
  "recruiter_message": "...",
  "answers": [{{"question": "...", "answer": "..."}}]
}}
"""
    return await chat(prompt, max_tokens=1600, temperature=0.5, parse=_parse_kit)


def _questions_parser(count: int):
    def parse(text: str) -> list[dict]:
        questions = [
            {
                "question": str(q["question"]).strip(),
                "type": str(q.get("type", "technical")).lower(),
                "topic": str(q.get("topic", "")),
            }
            for q in parse_json_object(text).get("questions", [])
            if isinstance(q, dict) and q.get("question")
        ]
        if len(questions) < min(3, count):
            raise ValueError("too few questions")
        return questions[:count]

    return parse


async def generate_interview_questions(
    role: str, job_description: str, resume_text: str, interview_type: str, difficulty: str, count: int
):
    type_rule = {
        "technical": "All questions must be technical.",
        "hr": "All questions must be HR/behavioural.",
        "mixed": "Make about 70% technical and 30% HR/behavioural questions.",
    }[interview_type]

    prompt = f"""
Create {count} realistic {difficulty}-level interview questions for a "{role}" candidate.
{type_rule}
Ask one clear question at a time, the way a real interviewer would. Personalise some
questions to the candidate's projects and skills when a resume is provided.

Job Description:
{job_description[:2000] or "Not provided"}

Candidate Resume:
{resume_text[:3000] or "Not provided"}

Return ONLY valid JSON, no markdown:
{{"questions": [{{"question": "...", "type": "technical or hr", "topic": "short topic"}}]}}
"""
    return await chat(prompt, max_tokens=900, temperature=0.6, parse=_questions_parser(count))


def _parse_evaluation(text: str) -> dict:
    data = parse_json_object(text)
    return {
        "score": max(0, min(10, int(round(float(data.get("score", 0)))))),
        "feedback": str(data.get("feedback", "")),
        "strengths": [str(s) for s in data.get("strengths", [])][:4],
        "improvements": [str(s) for s in data.get("improvements", [])][:4],
        "ideal_answer": str(data.get("ideal_answer", "")),
    }


async def evaluate_answer(role: str, question: str, answer: str):
    prompt = f"""
You are a strict but encouraging interviewer for a "{role}" position.

Question: {question}

Candidate's answer: {answer[:4000]}

Score the answer from 0 to 10 for correctness, depth, clarity and structure.
An empty, off-topic or "I don't know" answer scores 0-2.

Return ONLY valid JSON, no markdown:
{{
  "score": 7,
  "feedback": "2-3 sentence overall feedback",
  "strengths": ["what was good"],
  "improvements": ["what was missing or wrong"],
  "ideal_answer": "a concise model answer (max 120 words)"
}}
"""
    return await chat(prompt, max_tokens=900, temperature=0.2, parse=_parse_evaluation)
