import re
import unicodedata


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a URL slug: lowercase ASCII words joined by single hyphens."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:max_length].rstrip("-")
