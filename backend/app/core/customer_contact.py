"""Customer telephone validation without assuming a national dialing plan."""
import re


def phone_key(value: str | None) -> str:
    """Ignore presentation punctuation when comparing legacy/new telephone numbers."""
    return re.sub(r"[^0-9]", "", value or "")


def normalize_phone(value: str) -> str:
    """Keep leading zeroes and optional +; accept 7–15 ASCII digits."""
    if not isinstance(value, str):
        raise ValueError("Telephone number is required")
    normalized = re.sub(r"[\s().-]", "", value)
    if not re.fullmatch(r"\+?[0-9]{7,15}", normalized):
        raise ValueError("Telephone number must contain 7–15 digits, optionally starting with +")
    return normalized
