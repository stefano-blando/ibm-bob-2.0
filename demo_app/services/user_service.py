# User verification and authentication business logic
# PERMITTED: Business logic layer

from typing import Optional, Dict

# Mock in-memory user repository
USERS_DB: Dict[str, Dict[str, str]] = {
    "alice@example.com": {"password": "password123", "role": "admin"},
    "bob@example.com": {"password": "secretbob", "role": "developer"}
}

def verify_user(email: str, password: str) -> Optional[Dict[str, str]]:
    user = USERS_DB.get(email)
    if user and user["password"] == password:
        return {"email": email, "role": user["role"]}
    return None
