from io import BytesIO

from pypdf import PdfReader


def extract_text_from_pdf(data: bytes):
    reader = PdfReader(BytesIO(data))
    text = ""

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

    return text
