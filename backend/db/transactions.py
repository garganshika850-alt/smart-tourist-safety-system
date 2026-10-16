# ============================================================
# Smart Tourist Safety and Emergency Response System
# ACID Transaction Management Module
# ============================================================

from contextlib import contextmanager
from typing import Generator, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

from backend.db.connection import get_db_connection
from backend.utils.logger import logger

@contextmanager
def transaction_scope(
    existing_conn: Optional[psycopg2.extensions.connection] = None
) -> Generator[RealDictCursor, None, None]:
    """
    ACID Transaction Context Manager.
    
    Guarantees:
    - Atomicity: All SQL operations within the block succeed or all are rolled back.
    - Consistency: Enforced by PostgreSQL constraints during commit.
    - Isolation: Queries operate within PostgreSQL transaction isolation boundaries.
    - Durability: Committed writes are persisted to the WAL.

    Usage:
        with transaction_scope() as cur:
            cur.execute("UPDATE resources SET status = 'ASSIGNED' WHERE resource_id = %s", (r_id,))
            cur.execute("INSERT INTO resource_assignments ...")
            # Automatically committed at exit of block; rolled back on exception.
    """
    if existing_conn is not None:
        # Re-use provided connection
        cursor = existing_conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            existing_conn.commit()
            logger.debug("Transaction committed successfully.")
        except Exception as e:
            existing_conn.rollback()
            logger.error(f"Transaction failed and was rolled back: {e}")
            raise
        finally:
            cursor.close()
    else:
        # Check out connection from ThreadedConnectionPool
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                yield cursor
                conn.commit()
                logger.debug("Pooled transaction committed successfully.")
            except Exception as e:
                conn.rollback()
                logger.error(f"Pooled transaction failed and was rolled back: {e}")
                raise
            finally:
                cursor.close()
