import re
import unicodedata

from .db import get_db


ACCOUNT_EXISTS_MESSAGE = "An account with this email already exists. Please log in."
INVALID_CREDENTIALS_MESSAGE = "Email or password is incorrect."
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email):
    return unicodedata.normalize("NFKC", str(email or "")).strip().casefold()


def validate_email(email):
    normalized = normalize_email(email)
    if not EMAIL_RE.match(normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def user_by_normalized_email(email, role=None):
    normalized = normalize_email(email)
    query = """
        SELECT * FROM users
        WHERE active=1
          AND (email_normalized=? OR LOWER(TRIM(email))=?)
    """
    params = [normalized, normalized]
    if role:
        query += " AND role=?"
        params.append(role)
    query += " ORDER BY CASE WHEN email_normalized=? THEN 0 ELSE 1 END, id ASC LIMIT 1"
    params.append(normalized)
    return get_db().execute(query, params).fetchone()


def email_exists(email):
    return user_by_normalized_email(email) is not None
