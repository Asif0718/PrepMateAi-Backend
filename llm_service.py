import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found in .env file")

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

def generate_preparation_guide(resume_text, job_description):
    resume_text = resume_text[:6000]
    job_description = job_description[:3000]

    prompt = f"""
You are an AI placement preparation assistant.

Analyze the resume and job description.

Resume:
{resume_text}

Job Description:
{job_description}

Give output in this format:

1. Candidate Summary
2. Skills Found in Resume
3. Skills Required in Job Description
4. Skill Gaps
5. Topics to Prepare
6. Technical Interview Questions
7. HR Interview Questions
8. 7-Day Preparation Plan

Keep the answer clear and concise.
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful career preparation assistant."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.4,
        max_tokens=1500
    )

    return response.choices[0].message.content