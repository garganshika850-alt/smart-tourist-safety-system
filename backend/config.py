# ============================================================
# Smart Tourist Safety and Emergency Response System
# Configuration Module
# ============================================================

import os
from pathlib import Path
from dotenv import load_dotenv

# Locate base directory and load .env file
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

class Config:
    """Application configuration loaded from environment variables."""

    # Project Root
    BASE_DIR = BASE_DIR

    # Flask Settings
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "yes")

    # PostgreSQL Database Configuration
    DATABASE_HOST = os.getenv("DATABASE_HOST", "localhost")
    DATABASE_PORT = int(os.getenv("DATABASE_PORT", 5432))
    DATABASE_NAME = os.getenv("DATABASE_NAME", "tourist_safety_db")
    DATABASE_USER = os.getenv("DATABASE_USER", "tourist_admin")
    DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "")

    # Connection Pool Settings
    DB_MIN_CONNECTIONS = int(os.getenv("DB_MIN_CONNECTIONS", 2))
    DB_MAX_CONNECTIONS = int(os.getenv("DB_MAX_CONNECTIONS", 10))

    # Multithreading / OS Settings
    WORKER_POOL_SIZE = int(os.getenv("WORKER_POOL_SIZE", 3))

    @classmethod
    def get_db_params(cls) -> dict:
        """Returns dictionary of connection parameters for psycopg2."""
        return {
            "host": cls.DATABASE_HOST,
            "port": cls.DATABASE_PORT,
            "dbname": cls.DATABASE_NAME,
            "user": cls.DATABASE_USER,
            "password": cls.DATABASE_PASSWORD,
        }
