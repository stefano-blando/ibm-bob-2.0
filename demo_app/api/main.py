# FastAPI application entrypoint for demo_app

from demo_app.api.routes.auth import login_endpoint

def create_app():
    return {"name": "demo_auth_service", "routes": ["/auth/login"]}

if __name__ == "__main__":
    print("Demo App Service running...")
