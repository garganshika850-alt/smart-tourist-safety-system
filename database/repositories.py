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

class ZoneRepository:
    """Repository handling spatial queries and geofence safe/dangerous zones."""

    @staticmethod
    def get_active_zones() -> List[Dict[str, Any]]:
        """Returns all currently active geofence zones."""
        query = """
            SELECT zone_id, zone_name, zone_type, center_lat, center_lng, radius_km, risk_level, is_active
            FROM safe_dangerous_zones
            WHERE is_active = TRUE
            ORDER BY zone_id ASC;
        """
        with get_db_cursor() as cur:
            cur.execute(query)
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_zone_by_id(zone_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a specific zone by ID."""
        query = """
            SELECT zone_id, zone_name, zone_type, center_lat, center_lng, radius_km, risk_level, is_active
            FROM safe_dangerous_zones
            WHERE zone_id = %s;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (zone_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def find_zone_for_coordinates(lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Evaluates coordinates against active geofence zones."""
        from backend.utils.geofence import detect_primary_zone
        active_zones = ZoneRepository.get_active_zones()
        return detect_primary_zone(lat, lon, active_zones)

class LocationRepository:
    """Repository handling tourist GPS telemetry and location history."""

    @staticmethod
    def record_location(
        tourist_id: int, 
        latitude: float, 
        longitude: float, 
        zone_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Persists a GPS coordinate report.
        If zone_id is not explicitly provided, automatically evaluates
        geofences against active safe and dangerous zones.
        """
        if not TouristRepository.get_tourist_by_id(tourist_id):
            raise RecordNotFoundError(f"Tourist with ID {tourist_id} does not exist.")

        matched_zone = None
        if zone_id is None:
            matched_zone = ZoneRepository.find_zone_for_coordinates(latitude, longitude)
            if matched_zone:
                zone_id = matched_zone["zone_id"]
        else:
            matched_zone = ZoneRepository.get_zone_by_id(zone_id)

        query = """
            INSERT INTO locations (tourist_id, latitude, longitude, zone_id)
            VALUES (%s, %s, %s, %s)
            RETURNING location_id, tourist_id, latitude, longitude, recorded_at, zone_id;
        """
        with get_db_cursor(commit=True) as cur:
            cur.execute(query, (tourist_id, latitude, longitude, zone_id))
            row = cur.fetchone()
            location_record = dict(row)
            if matched_zone:
                location_record["zone"] = {
                    "zone_id": matched_zone["zone_id"],
                    "zone_name": matched_zone["zone_name"],
                    "zone_type": matched_zone["zone_type"],
                    "risk_level": matched_zone["risk_level"],
                }
            else:
                location_record["zone"] = None
            logger.info(
                f"Recorded location #{location_record['location_id']} for tourist #{tourist_id} "
                f"({latitude}, {longitude}) - Zone: {zone_id}"
            )
            return location_record

    @staticmethod
    def get_location_history(
        tourist_id: int, 
        limit: int = 50, 
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Returns paginated location history for a tourist, newest first."""
        if not TouristRepository.get_tourist_by_id(tourist_id):
            raise RecordNotFoundError(f"Tourist with ID {tourist_id} does not exist.")

        query = """
            SELECT 
                l.location_id, l.tourist_id, l.latitude, l.longitude, l.recorded_at, l.zone_id,
                z.zone_name, z.zone_type, z.risk_level
            FROM locations l
            LEFT JOIN safe_dangerous_zones z ON l.zone_id = z.zone_id
            WHERE l.tourist_id = %s
            ORDER BY l.recorded_at DESC, l.location_id DESC
            LIMIT %s OFFSET %s;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (tourist_id, limit, offset))
            results = []
            for r in cur.fetchall():
                item = dict(r)
                if item.get("zone_id"):
                    item["zone"] = {
                        "zone_id": item["zone_id"],
                        "zone_name": item.pop("zone_name", None),
                        "zone_type": item.pop("zone_type", None),
                        "risk_level": item.pop("risk_level", None),
                    }
                else:
                    item.pop("zone_name", None)
                    item.pop("zone_type", None)
                    item.pop("risk_level", None)
                    item["zone"] = None
                results.append(item)
            return results

    @staticmethod
    def get_latest_location(tourist_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves the single most recent location report for a tourist."""
        if not TouristRepository.get_tourist_by_id(tourist_id):
            raise RecordNotFoundError(f"Tourist with ID {tourist_id} does not exist.")

        query = """
            SELECT 
                l.location_id, l.tourist_id, l.latitude, l.longitude, l.recorded_at, l.zone_id,
                z.zone_name, z.zone_type, z.risk_level
            FROM locations l
            LEFT JOIN safe_dangerous_zones z ON l.zone_id = z.zone_id
            WHERE l.tourist_id = %s
            ORDER BY l.recorded_at DESC, l.location_id DESC
            LIMIT 1;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (tourist_id,))
            row = cur.fetchone()
            if not row:
                return None
            item = dict(row)
            if item.get("zone_id"):
                item["zone"] = {
                    "zone_id": item["zone_id"],
                    "zone_name": item.pop("zone_name", None),
                    "zone_type": item.pop("zone_type", None),
                    "risk_level": item.pop("risk_level", None),
                }
            else:
                item.pop("zone_name", None)
                item.pop("zone_type", None)
                item.pop("risk_level", None)
                item["zone"] = None
            return item

class EmergencyRepository:
    """Repository handling emergency incident lifecycle and audit logs."""

    @staticmethod
    def create_incident(
        tourist_id: int,
        incident_type: str,
        priority: int,
        latitude: float,
        longitude: float,
        description: Optional[str] = None,
        status: str = "RECEIVED"
    ) -> Dict[str, Any]:
        """
        Creates an emergency incident and inserts an audit log entry atomically.
        """
        if not TouristRepository.get_tourist_by_id(tourist_id):
            raise RecordNotFoundError(f"Tourist with ID {tourist_id} does not exist.")

        insert_incident_sql = """
            INSERT INTO emergency_incidents (tourist_id, incident_type, priority, status, latitude, longitude, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING incident_id, tourist_id, incident_type, priority, status, latitude, longitude, description, created_at, resolved_at;
        """
        insert_log_sql = """
            INSERT INTO emergency_logs (incident_id, action, details, performed_by)
            VALUES (%s, 'INCIDENT_CREATED', %s, 'SYSTEM');
        """

        with get_db_cursor(commit=True) as cur:
            cur.execute(
                insert_incident_sql,
                (tourist_id, incident_type, priority, status, latitude, longitude, description)
            )
            row = cur.fetchone()
            incident = dict(row)
            incident_id = incident["incident_id"]

            log_details = f"Emergency incident '{incident_type}' (Priority {priority}) reported at ({latitude}, {longitude})."
            cur.execute(insert_log_sql, (incident_id, log_details))
            if status == "QUEUED":
                cur.execute(
                    "INSERT INTO emergency_logs (incident_id, action, details, performed_by) "
                    "VALUES (%s, 'PRIORITY_ENQUEUED', %s, 'ProcessManager')",
                    (incident_id, f"Added to priority queue at priority {priority}."),
                )

            logger.info(f"Created emergency incident #{incident_id} [{incident_type}] Priority {priority} for tourist #{tourist_id}")
            return incident

    @staticmethod
    def get_incident_by_id(incident_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves incident details along with tourist info and emergency logs."""
        query = """
            SELECT 
                i.incident_id, i.tourist_id, i.incident_type, i.priority, i.status, 
                i.latitude, i.longitude, i.description, i.created_at, i.resolved_at,
                t.name AS tourist_name, t.phone AS tourist_phone, t.blood_group AS tourist_blood_group
            FROM emergency_incidents i
            JOIN tourists t ON i.tourist_id = t.tourist_id
            WHERE i.incident_id = %s;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (incident_id,))
            row = cur.fetchone()
            if not row:
                return None
            incident = dict(row)

            cur.execute(
                """
                SELECT log_id, incident_id, action, details, performed_by, created_at
                FROM emergency_logs
                WHERE incident_id = %s
                ORDER BY log_id ASC;
                """,
                (incident_id,)
            )
            incident["logs"] = [dict(log) for log in cur.fetchall()]
            return incident

    @staticmethod
    def get_incidents(
        status: Optional[str] = None,
        incident_type: Optional[str] = None,
        priority: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Returns paginated incidents, filtered by status/type/priority, ordered by priority."""
        conditions = []
        params = []

        if status:
            conditions.append("i.status = %s")
            params.append(status)
        if incident_type:
            conditions.append("i.incident_type = %s")
            params.append(incident_type)
        if priority is not None:
            conditions.append("i.priority = %s")
            params.append(priority)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT 
                i.incident_id, i.tourist_id, i.incident_type, i.priority, i.status,
                i.latitude, i.longitude, i.description, i.created_at, i.resolved_at,
                t.name AS tourist_name, t.phone AS tourist_phone
            FROM emergency_incidents i
            JOIN tourists t ON i.tourist_id = t.tourist_id
            {where_clause}
            ORDER BY i.priority ASC, i.created_at ASC
            LIMIT %s OFFSET %s;
        """
        params.extend([limit, offset])

        with get_db_cursor() as cur:
            cur.execute(query, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def update_incident_status(
        incident_id: int,
        status: str,
        action: str = "STATUS_UPDATED",
        details: Optional[str] = None,
        performed_by: str = "OPERATOR"
    ) -> Optional[Dict[str, Any]]:
        """Updates status of an incident and appends an audit log entry."""
        if not details:
            details = f"Incident status transitioned to {status}."

        resolve_clause = ", resolved_at = CURRENT_TIMESTAMP" if status == "RESOLVED" else ""

        update_sql = f"""
            UPDATE emergency_incidents
            SET status = %s{resolve_clause}
            WHERE incident_id = %s
            RETURNING incident_id, tourist_id, incident_type, priority, status, latitude, longitude, description, created_at, resolved_at;
        """
        insert_log_sql = """
            INSERT INTO emergency_logs (incident_id, action, details, performed_by)
            VALUES (%s, %s, %s, %s);
        """

        with get_db_cursor(commit=True) as cur:
            cur.execute(update_sql, (status, incident_id))
            row = cur.fetchone()
            if not row:
                return None
            incident = dict(row)
            cur.execute(insert_log_sql, (incident_id, action, details, performed_by))
            logger.info(f"Updated incident #{incident_id} status to {status} by {performed_by}")
            return incident

class ResourceRepository:
    """Repository handling emergency resources, fleet vehicles, and dispatch assignments."""

    @staticmethod
    def get_all_resources(
        resource_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Returns all resources with optional type and status filters."""
        conditions = []
        params = []
        if resource_type:
            conditions.append("resource_type = %s")
            params.append(resource_type)
        if status:
            conditions.append("status = %s")
            params.append(status)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"""
            SELECT resource_id, resource_name, resource_type, status, current_lat, current_lng
            FROM resources
            {where}
            ORDER BY resource_id ASC;
        """
        with get_db_cursor() as cur:
            cur.execute(query, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_available_resources(resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns physical apparatus currently in AVAILABLE status."""
        return ResourceRepository.get_all_resources(resource_type=resource_type, status="AVAILABLE")

    @staticmethod
    def get_resource_by_id(resource_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves single resource profile by ID."""
        query = """
            SELECT resource_id, resource_name, resource_type, status, current_lat, current_lng
            FROM resources
            WHERE resource_id = %s;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (resource_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_resource_status(resource_id: int, status: str) -> Optional[Dict[str, Any]]:
        """Updates resource status (AVAILABLE, ASSIGNED, MAINTENANCE)."""
        query = """
            UPDATE resources
            SET status = %s
            WHERE resource_id = %s
            RETURNING resource_id, resource_name, resource_type, status, current_lat, current_lng;
        """
        with get_db_cursor(commit=True) as cur:
            cur.execute(query, (status, resource_id))
            row = cur.fetchone()
            return dict(row) if row else None

    @staticmethod
    def create_assignment(
        incident_id: int,
        resource_id: Optional[int] = None,
        team_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Creates a resource assignment record linking apparatus/team to an incident."""
        query = """
            INSERT INTO resource_assignments (incident_id, resource_id, team_id, status)
            VALUES (%s, %s, %s, 'ASSIGNED')
            RETURNING assignment_id, incident_id, resource_id, team_id, status, assigned_at;
        """
        with get_db_cursor(commit=True) as cur:
            cur.execute(query, (incident_id, resource_id, team_id))
            row = cur.fetchone()
            return dict(row)

    @staticmethod
    def get_incident_assignments(incident_id: int) -> List[Dict[str, Any]]:
        """Returns all assignments recorded for a specific incident."""
        query = """
            SELECT 
                a.assignment_id, a.incident_id, a.resource_id, a.team_id, a.status, 
                a.assigned_at, a.released_at,
                r.resource_name, r.resource_type,
                t.team_name, t.specialization
            FROM resource_assignments a
            LEFT JOIN resources r ON a.resource_id = r.resource_id
            LEFT JOIN rescue_teams t ON a.team_id = t.team_id
            WHERE a.incident_id = %s
            ORDER BY a.assignment_id ASC;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (incident_id,))
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def release_incident_assignments(incident_id: int) -> int:
        """Marks all active assignments for an incident as COMPLETED and restores resources to AVAILABLE."""
        select_query = """
            SELECT resource_id, team_id
            FROM resource_assignments
            WHERE incident_id = %s AND status = 'ASSIGNED';
        """
        update_assignments_query = """
            UPDATE resource_assignments
            SET status = 'COMPLETED', released_at = CURRENT_TIMESTAMP
            WHERE incident_id = %s AND status = 'ASSIGNED';
        """
        with get_db_cursor(commit=True) as cur:
            cur.execute(select_query, (incident_id,))
            assignments = cur.fetchall()
            if not assignments:
                return 0

            # Revert resources to AVAILABLE
            for a in assignments:
                if a["resource_id"]:
                    cur.execute(
                        "UPDATE resources SET status = 'AVAILABLE' WHERE resource_id = %s;",
                        (a["resource_id"],)
                    )
                if a["team_id"]:
                    cur.execute(
                        """
                        UPDATE rescue_teams 
                        SET current_capacity = GREATEST(0, current_capacity - 1),
                            status = CASE WHEN current_capacity - 1 <= 0 THEN 'AVAILABLE' ELSE status END
                        WHERE team_id = %s;
                        """,
                        (a["team_id"],)
                    )

            cur.execute(update_assignments_query, (incident_id,))
            return len(assignments)

class RescueTeamRepository:
    """Repository handling specialized human emergency rescue teams."""

    @staticmethod
    def get_all_teams(status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all rescue teams with optional status filter."""
        where = "WHERE status = %s" if status else ""
        query = f"""
            SELECT team_id, team_name, specialization, status, current_capacity, max_capacity, contact_number
            FROM rescue_teams
            {where}
            ORDER BY team_id ASC;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (status,) if status else ())
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_available_teams() -> List[Dict[str, Any]]:
        """Returns rescue teams that have available capacity."""
        query = """
            SELECT team_id, team_name, specialization, status, current_capacity, max_capacity, contact_number
            FROM rescue_teams
            WHERE status = 'AVAILABLE' AND current_capacity < max_capacity
            ORDER BY team_id ASC;
        """
        with get_db_cursor() as cur:
            cur.execute(query)
            return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_team_by_id(team_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves rescue team by ID."""
        query = """
            SELECT team_id, team_name, specialization, status, current_capacity, max_capacity, contact_number
            FROM rescue_teams
            WHERE team_id = %s;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (team_id,))
            row = cur.fetchone()
            return dict(row) if row else None

class LogRepository:
    """Repository handling audit trails and immutable system logs."""

    @staticmethod
    def get_recent_logs(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Returns recent emergency and audit logs across all incidents."""
        query = """
            SELECT 
                l.log_id, l.incident_id, l.action, l.details, l.performed_by, l.created_at,
                i.incident_type, i.priority
            FROM emergency_logs l
            LEFT JOIN emergency_incidents i ON l.incident_id = i.incident_id
            ORDER BY l.log_id DESC
            LIMIT %s OFFSET %s;
        """
        with get_db_cursor() as cur:
            cur.execute(query, (limit, offset))
            return [dict(r) for r in cur.fetchall()]

class DashboardRepository:
    """Repository handling operational metric aggregations for authority dashboards."""

    @staticmethod
    def get_summary_counts() -> Dict[str, int]:
        """Returns high-level metric counts across the entire system."""
        with get_db_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM tourists;")
            tourists_count = cur.fetchone()["c"]

            cur.execute(
                "SELECT COUNT(*) AS c FROM emergency_incidents WHERE status NOT IN ('RESOLVED', 'FAILED');"
            )
            active_incidents = cur.fetchone()["c"]

            cur.execute("SELECT COUNT(*) AS c FROM resources WHERE status = 'AVAILABLE';")
            available_resources = cur.fetchone()["c"]

            cur.execute(
                "SELECT COUNT(*) AS c FROM rescue_teams WHERE status = 'AVAILABLE' AND current_capacity < max_capacity;"
            )
            available_teams = cur.fetchone()["c"]

            return {
                "total_tourists": tourists_count,
                "active_incidents": active_incidents,
                "available_resources": available_resources,
                "available_teams": available_teams,
            }
