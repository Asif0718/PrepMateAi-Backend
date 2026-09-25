import httpx

from config import RAPIDAPI_KEY

_client = httpx.AsyncClient(timeout=20)


def normalize_location(location):
    location = location.strip()

    corrections = {
        "banglore": "Bangalore",
        "banglaore": "Bangalore",
        "bengalore": "Bangalore",
        "bengaluru": "Bangalore",
    }

    return corrections.get(location.lower(), location)


async def fetch_jobs(query="software developer", location="India"):
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

    try:
        response = await _client.get(url, headers=headers, params=params)
    except httpx.HTTPError as e:
        print("Job search request failed:", e)
        return []

    if response.status_code != 200:
        print("Job search failed:", response.status_code, response.text[:300])
        return []

    jobs = []

    for job in response.json().get("data", []):
        apply_link = job.get("job_apply_link")

        if not apply_link and job.get("apply_options"):
            apply_link = job["apply_options"][0].get("apply_link")

        jobs.append({
            "id": job.get("job_id"),
            "title": job.get("job_title"),
            "company": job.get("employer_name"),
            "location": job.get("job_location"),
            "type": job.get("job_employment_type"),
            "description": job.get("job_description"),
            "apply_link": apply_link,
            "postedAt": job.get("job_posted_at_datetime_utc"),
        })

    return jobs
