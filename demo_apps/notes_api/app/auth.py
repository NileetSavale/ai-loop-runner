import hashlib
import hmac

SECRET_KEY = "dev-secret-change-me"


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def check_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def make_token(user_id: int) -> str:
    signature = hmac.new(SECRET_KEY.encode(), str(user_id).encode(), "sha256").hexdigest()
    return f"{user_id}.{signature}"


def read_token(token: str) -> int | None:
    user_id, _, signature = token.partition(".")
    if not user_id.isdigit():
        return None
    expected = hmac.new(SECRET_KEY.encode(), user_id.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return int(user_id)
