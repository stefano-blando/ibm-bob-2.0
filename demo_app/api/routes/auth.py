# Authentication & Login Endpoints
# PERMITTED: API Router layer

from typing import Any

from demo_app.services.user_service import verify_user


def login_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Authenticate a user and return a session token.

    Args:
        payload: A dictionary containing the login credentials.
            Expected keys:
                - ``email`` (str): The user's email address.
                - ``password`` (str): The user's plain-text password.

    Returns:
        On success: ``{"token": str, "status": 200}``
        On failure: ``{"error": str, "status": 401}``
    """
    email: str = payload.get("email", "")
    password: str = payload.get("password", "")
    user = verify_user(email, password)
    if not user:
        return {"error": "Invalid credentials", "status": 401}
    return {"token": f"token-{email}", "status": 200}
