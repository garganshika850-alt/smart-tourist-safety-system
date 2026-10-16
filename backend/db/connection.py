# ============================================================
# Smart Tourist Safety and Emergency Response System
# Database Connection Management (ThreadedConnectionPool)
# ============================================================

import threading
from contextlib import contextmanager
from typing import Optional, Generator
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from backend.config import Config
from backend.utils.logger import logger

# Module-level connection pool singleton
_pool: Optional[pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()

def init_db_pool(
    minconn: Optional[int] = None, 
    maxconn: Optional[int] = None
) -> pool.ThreadedConnectionPool:
    """
    Initializes the thread-safe connection pool singleton.
    Guaranteed thread-safe through a re-entrant lock.
    """
    global _pool
    with _pool_lock:
        if _pool is None or _pool.closed:
            min_c = minconn or Config.DB_MIN_CONNECTIONS
            max_c = maxconn or Config.DB_MAX_CONNECTIONS
            logger.info(
                f"Initializing ThreadedConnectionPool (min={min_c}, max={max_c}) "
                f"for database '{Config.DATABASE_NAME}' at {Config.DATABASE_HOST}:{Config.DATABASE_PORT}..."
            )
            try:
                _pool = pool.ThreadedConnectionPool(
                    minconn=min_c,
                    maxconn=max_c,
                    **Config.get_db_params()
                )
                logger.info("ThreadedConnectionPool successfully initialized.")
            except psycopg2.Error as e:
                logger.error(f"Failed to initialize ThreadedConnectionPool: {e}")
                raise
    return _pool

def get_pool() -> pool.ThreadedConnectionPool:
    """Returns the active pool, initializing it if not already created."""
    global _pool
    if _pool is None or _pool.closed:
        return init_db_pool()
    return _pool

def close_db_pool() -> None:
    """Closes all connections in the pool safely upon application shutdown."""
    global _pool
    with _pool_lock:
        if _pool is not None and not _pool.closed:
            logger.info("Closing all pooled database connections...")
            _pool.closeall()
            _pool = None
            logger.info("Database connection pool closed.")

@contextmanager
def get_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Context manager that checks out a connection from the pool
    and reliably returns it to the pool even on failure.
    """
    connection_pool = get_pool()
    conn = connection_pool.getconn()
    try:
        yield conn
    finally:
        connection_pool.putconn(conn)

@contextmanager
def get_db_cursor(commit: bool = False) -> Generator[RealDictCursor, None, None]:
    """
    Context manager yielding a dictionary cursor (RealDictCursor).
    Handles commit on success (if commit=True) and rollback on exception.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error during transaction: {e}. Transaction rolled back.")
            raise
        finally:
            cursor.close()

def check_db_health() -> dict:
    """
    Performs a lightweight health check query ('SELECT 1;') to test pool responsiveness.
    Returns status dictionary with connection parameters.
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT 1 AS alive, current_database() AS db, current_user AS user;")
            result = cur.fetchone()
            return {
                "status": "healthy",
                "database": result["db"],
                "user": result["user"],
                "pool_closed": _pool.closed if _pool else True,
            }
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "pool_closed": _pool.closed if _pool else True,
        }
