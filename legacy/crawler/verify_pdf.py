import requests

PDF_MAGIC = b"%PDF"


def verify_pdf(url, timeout=15):
    """
    Robust PDF verification.

    Returns:
        (is_pdf, reason)
    """

    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)

        ct = r.headers.get("content-type", "").lower()

        if "pdf" in ct:
            return True, "content-type"

        if "octet-stream" in ct:
            # maybe pdf
            pass

    except Exception:
        pass

    try:
        r = requests.get(url, stream=True, timeout=timeout)

        chunk = r.raw.read(5)

        if chunk.startswith(PDF_MAGIC):
            return True, "magic-bytes"

    except Exception as e:
        return False, f"fetch-error:{e}"

    if url.lower().endswith(".pdf"):
        return True, "url-extension"

    return False, "not-pdf"
