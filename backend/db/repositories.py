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

class TouristRepository:
    """Repository handling all parameterized SQL operations for Tourist profiles."""

    @staticmethod
    def create_tourist(
        name: str,
        phone: str,
        email: str,
        nationality: Optional[str] = None,
        blood_group: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new tourist record using parameterized INSERT."""
        query = """
            INSERT INTO tourists (name, phone, email, nationality, blood_group)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING tourist_id, name, phone, email, nationality, blood_group, registered_at;
        """
        try:
            with get_db_cursor(commit=True) as cur:
                cur.execute(query, (name.strip(), phone.strip(), email.strip().lower(), nationality, blood_group))
                tourist = cur.fetchone()
                logger.info(f"Created tourist #{tourist['tourist_id']} ({tourist['name']})")
                return dict(tourist)
        except errors.UniqueViolation as e:
            logger.warning(f"Duplicate tourist registration attempted: {e}")
            msg = "A tourist with this phone number or email address already exists."
            raise DuplicateRecordError(msg) from e

    @staticmethod
    def get_tourist_by_id(tourist_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a tourist profile with associated emergency contacts."""
        query = """
            SELECT tourist_id, name, phone, email, nationality, blood_group, registered_at
            FROM tourists
            WHERE tourist_id = %s;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (tourist_id,))
            row = cur.fetchone()
            if not row:
                return None
            tourist = dict(row)

            # Fetch emergency contacts
            cur.execute(
                "SELECT contact_id, name, phone, relationship FROM emergency_contacts WHERE tourist_id = %s ORDER BY contact_id ASC;",
                (tourist_id,)
            )
            tourist["emergency_contacts"] = [dict(c) for c in cur.fetchall()]
            return tourist

    @staticmethod
    def get_tourists(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Returns paginated list of tourists with emergency contact counts."""
        query = """
            SELECT 
                t.tourist_id, t.name, t.phone, t.email, t.nationality, t.blood_group, t.registered_at,
                COUNT(c.contact_id) AS contact_count
            FROM tourists t
            LEFT JOIN emergency_contacts c ON t.tourist_id = c.tourist_id
            GROUP BY t.tourist_id
            ORDER BY t.tourist_id DESC
            LIMIT %s OFFSET %s;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (limit, offset))
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def update_tourist(tourist_id: int, **fields: Any) -> Optional[Dict[str, Any]]:
        """Updates tourist fields dynamically with safe parameterized SQL."""
        allowed_fields = {"name", "phone", "email", "nationality", "blood_group"}
        updates = {k: v for k, v in fields.items() if k in allowed_fields and v is not None}
        if not updates:
            return TouristRepository.get_tourist_by_id(tourist_id)

        set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
        values = list(updates.values())
        values.append(tourist_id)

        query = f"""
            UPDATE tourists
            SET {set_clause}
            WHERE tourist_id = %s
            RETURNING tourist_id, name, phone, email, nationality, blood_group, registered_at;
        """
        try:
            with get_db_cursor(commit=True) as cur:
                cur.execute(query, tuple(values))
                row = cur.fetchone()
                if not row:
                    return None
                return dict(row)
        except errors.UniqueViolation as e:
            logger.warning(f"Unique violation updating tourist #{tourist_id}: {e}")
            raise DuplicateRecordError("Another tourist is already using this phone or email.") from e

    @staticmethod
    def delete_tourist(tourist_id: int) -> bool:
        """Deletes tourist profile, respecting ON DELETE RESTRICT on active incidents."""
        query = "DELETE FROM tourists WHERE tourist_id = %s RETURNING tourist_id;"
        try:
            with get_db_cursor(commit=True) as cur:
                cur.execute(query, (tourist_id,))
                deleted = cur.fetchone()
                return deleted is not None
        except errors.ForeignKeyViolation as e:
            logger.warning(f"Cannot delete tourist #{tourist_id}: foreign key restriction: {e}")
            raise DependencyConflictError(
                "Cannot delete tourist profile with associated emergency incidents on file."
            ) from e

class ContactRepository:
    """Repository handling all parameterized SQL operations for Emergency Contacts."""

    @staticmethod
    def add_contact(tourist_id: int, name: str, phone: str, relationship: str) -> Dict[str, Any]:
        """Inserts a new emergency contact for a tourist."""
        # Ensure tourist exists first
        if not TouristRepository.get_tourist_by_id(tourist_id):
            raise RecordNotFoundError(f"Tourist with ID {tourist_id} does not exist.")

        query = """
            INSERT INTO emergency_contacts (tourist_id, name, phone, relationship)
            VALUES (%s, %s, %s, %s)
            RETURNING contact_id, tourist_id, name, phone, relationship;
        """
        with get_db_cursor(commit=True) as cur:
            cur.execute(query, (tourist_id, name.strip(), phone.strip(), relationship.strip()))
            row = cur.fetchone()
            logger.info(f"Added emergency contact #{row['contact_id']} for tourist #{tourist_id}")
            return dict(row)

    @staticmethod
    def get_contacts(tourist_id: int) -> List[Dict[str, Any]]:
        """Returns all emergency contacts for a tourist."""
        query = """
            SELECT contact_id, tourist_id, name, phone, relationship
            FROM emergency_contacts
            WHERE tourist_id = %s
            ORDER BY contact_id ASC;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (tourist_id,))
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def delete_contact(tourist_id: int, contact_id: int) -> bool:
        """Deletes an emergency contact."""
        query = """
            DELETE FROM emergency_contacts
            WHERE contact_id = %s AND tourist_id = %s
            RETURNING contact_id;
        """
        with get_db_cursor(commit=True) as cur:
            cur.execute(query, (contact_id, tourist_id))
            return cur.fetchone() is not None
