import httpx

from config import BREVO_API_KEY, BREVO_SENDER_EMAIL


def email_enabled() -> bool:
    return bool(BREVO_API_KEY and BREVO_SENDER_EMAIL)


async def send_email(client: httpx.AsyncClient, user: dict, subject: str, html_content: str) -> int:
    response = await client.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": BREVO_API_KEY},
        json={
            "sender": {"email": BREVO_SENDER_EMAIL, "name": "PrepMate AI"},
            "to": [{"email": user["email"], "name": user.get("name", "")}],
            "subject": subject,
            "htmlContent": html_content,
        },
    )
    return response.status_code
