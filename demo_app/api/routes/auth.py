# Authentication & Login Endpoints
# PERMITTED: API Router layer

from demo_app.services.user_service import verify_user

def login_endpoint(payload: dict) -> dict:
    email = payload.get("email", "")
    password = payload.get("password", "")
    user = verify_user(email, password)
    if not user:
        return {"error": "Invalid credentials", "status": 401}
    return {"token": f"token-{email}", "status": 200}
