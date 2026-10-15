# ============================================================
# Smart Tourist Safety and Emergency Response System
# Data Access Layer / SQL Repositories
# ============================================================

from typing import Any, Dict, List, Optional
import psycopg2
from psycopg2 import errors

from backend.db.connection import get_db_cursor
from backend.utils.logger import logger

class DuplicateRecordError(Exception):
    """Raised when an operation violates a unique constraint."""
    pass

class RecordNotFoundError(Exception):
    """Raised when an entity is not found in the database."""
    pass

class DependencyConflictError(Exception):
    """Raised when an entity cannot be deleted due to active dependencies."""
    pass
