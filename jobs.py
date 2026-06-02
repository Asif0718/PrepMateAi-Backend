import os
import requests
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")


def normalize_location(location):
    location = location.strip()

    corrections = {
        "banglore": "Bangalore",
        "banglaore": "Bangalore",
        "bengalore": "Bangalore",
        "bengaluru": "Bangalore",
    }

    return corrections.get(location.lower(), location)


def fetch_jobs(query="software developer", location="India"):
    url = "https://jsearch.p.rapidapi.com/search"

    if not RAPIDAPI_KEY:
        print("RAPIDAPI_KEY missing")
        return []

    location = normalize_location(location)

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }

    params = {
        "query": f"{query} {location}",
        "page": "1",
        "num_pages": "1",
        "country": "in",
        "language": "en",
    }

    response = requests.get(url, headers=headers, params=params)

    print("SEARCH QUERY:", params["query"])
    print("STATUS CODE:", response.status_code)
    print("RAW RESPONSE:", response.text)

    if response.status_code != 200:
        return []

    data = response.json()
    jobs = []

    for job in data.get("data", []):
        apply_link = job.get("job_apply_link")

        if not apply_link and job.get("apply_options"):
            apply_options = job.get("apply_options", [])
            if len(apply_options) > 0:
                apply_link = apply_options[0].get("apply_link")

        jobs.append({
            "title": job.get("job_title"),
            "company": job.get("employer_name"),
            "location": job.get("job_location"),
            "description": job.get("job_description"),
            "apply_link": apply_link,
            "postedAt": job.get("job_posted_at_datetime_utc"),
        })

    return jobs