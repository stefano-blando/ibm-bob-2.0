# Global application configuration & secrets
# RESTRICTED: Sensitive configuration file

SECRET_KEY = "super-secret-master-signing-key-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
DATABASE_URL = "sqlite:///./demo_app.db"
