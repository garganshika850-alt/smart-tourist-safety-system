# ============================================================
# Smart Tourist Safety and Emergency Response System
# OS Concept: Resource Manager & Deadlock Gatekeeper (Phase 13)
# ============================================================

import threading
from typing import Any, Dict, List, Optional
from backend.resource_manager.synchronization import sync_manager, SynchronizationManager
from backend.resource_manager.bankers_algorithm import BankersAlgorithm
from backend.db.repositories import (
    ResourceRepository,
    RescueTeamRepository,
    EmergencyRepository,
)
from backend.notifications.socket_service import broadcast_emergency_update
from backend.utils.logger import logger
from backend.db.connection import get_db_connection

class ResourceManager:
    """
    Central gatekeeper orchestrating concurrency control, Banker's Deadlock Avoidance,
    and database-level resource assignment for emergency incidents.
    """

    def __init__(
        self,
        banker: Optional[BankersAlgorithm] = None,
        sync: Optional[SynchronizationManager] = None
    ):
        self.banker = banker or BankersAlgorithm()
        self.sync = sync or sync_manager

    def dispatch_incident_transaction(self, incident_id: int, incident_type: str) -> Dict[str, Any]:
        """Process one queued incident and allocate real DB resources atomically.

        Row locks serialize competing workers across both threads and application
        processes. The incident, team/resource state, assignment, and audit log
        share one PostgreSQL transaction, so any SQL failure rolls the whole
        dispatch back.
        """
        needs_team = incident_type in {"CRITICAL_ACCIDENT", "SOS", "DANGEROUS_ZONE"}
        needs_ambulance = incident_type in {"CRITICAL_ACCIDENT", "SOS"}
        with self.sync.acquire_dispatch_permit(timeout=3.0) as permit_granted:
            if not permit_granted:
                return {"allocated": False, "incident_id": incident_id,
                        "status": "QUEUED", "reason": "Dispatch capacity is busy."}

            with get_db_connection() as conn:
                cur = conn.cursor()
                try:
                    cur.execute(
                        "SELECT status FROM emergency_incidents WHERE incident_id = %s FOR UPDATE",
                        (incident_id,),
                    )
                    incident = cur.fetchone()
                    if incident is None:
                        raise ValueError(f"Emergency {incident_id} does not exist")
                    if incident[0] in ("RESOLVED", "FAILED"):
                        conn.commit()
                        return {"allocated": False, "incident_id": incident_id,
                                "status": incident[0], "reason": "Incident is already closed."}

                    cur.execute(
                        "UPDATE emergency_incidents SET status = 'PROCESSING' WHERE incident_id = %s",
                        (incident_id,),
                    )
                    cur.execute(
                        "INSERT INTO emergency_logs (incident_id, action, details, performed_by) "
                        "VALUES (%s, 'PROCESSING', %s, %s)",
                        (incident_id, f"Priority dispatch processing {incident_type}",
                         threading.current_thread().name),
                    )

                    team = None
                    vehicle = None
                    if needs_team:
                        cur.execute(
                            "SELECT team_id, team_name FROM rescue_teams "
                            "WHERE status = 'AVAILABLE' AND current_capacity < max_capacity "
                            "ORDER BY team_id LIMIT 1 FOR UPDATE SKIP LOCKED"
                        )
                        team = cur.fetchone()
                    if needs_ambulance:
                        cur.execute(
                            "SELECT resource_id, resource_name FROM resources "
                            "WHERE resource_type = 'AMBULANCE' AND status = 'AVAILABLE' "
                            "ORDER BY resource_id LIMIT 1 FOR UPDATE SKIP LOCKED"
                        )
                        vehicle = cur.fetchone()

                    missing = (needs_team and team is None) or (needs_ambulance and vehicle is None)
                    if missing:
                        status = "FAILED"
                        details = "No suitable available rescue resource; no assignment was made."
                        cur.execute(
                            "UPDATE emergency_incidents SET status = %s WHERE incident_id = %s",
                            (status, incident_id),
                        )
                        cur.execute(
                            "INSERT INTO emergency_logs (incident_id, action, details, performed_by) "
                            "VALUES (%s, 'NO_RESOURCE', %s, %s)",
                            (incident_id, details, threading.current_thread().name),
                        )
                        conn.commit()
                        return {"allocated": False, "incident_id": incident_id,
                                "status": status, "reason": details}

                    if team:
                        cur.execute(
                            "UPDATE rescue_teams SET current_capacity = current_capacity + 1, "
                            "status = CASE WHEN current_capacity + 1 >= max_capacity "
                            "THEN 'BUSY' ELSE 'AVAILABLE' END WHERE team_id = %s",
                            (team[0],),
                        )
                    if vehicle:
                        cur.execute("UPDATE resources SET status = 'ASSIGNED' WHERE resource_id = %s",
                                    (vehicle[0],))
                    if team or vehicle:
                        cur.execute(
                            "INSERT INTO resource_assignments (incident_id, resource_id, team_id, status) "
                            "VALUES (%s, %s, %s, 'ASSIGNED') RETURNING assignment_id",
                            (incident_id, vehicle[0] if vehicle else None, team[0] if team else None),
                        )
                        assignment_id = cur.fetchone()[0]
                        status = "RESOURCE_ASSIGNED"
                        details = "Allocated " + ", ".join(
                            [row[1] for row in (vehicle, team) if row]
                        )
                    else:
                        assignment_id = None
                        status = "RESOLVED"
                        details = "Non-dispatch event processed; no physical resource required."

                    cur.execute(
                        "UPDATE emergency_incidents SET status = %s, "
                        "resolved_at = CASE WHEN %s = 'RESOLVED' THEN CURRENT_TIMESTAMP ELSE resolved_at END "
                        "WHERE incident_id = %s",
                        (status, status, incident_id),
                    )
                    cur.execute(
                        "INSERT INTO emergency_logs (incident_id, action, details, performed_by) "
                        "VALUES (%s, %s, %s, %s)",
                        (incident_id, status, details, threading.current_thread().name),
                    )
                    conn.commit()
                    return {
                        "allocated": bool(team or vehicle), "incident_id": incident_id,
                        "status": status, "assignment_id": assignment_id,
                        "team": team[1] if team else None,
                        "resource": vehicle[1] if vehicle else None,
                        "transaction": "COMMITTED",
                    }
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    cur.close()

    def resolve_incident_transaction(self, incident_id: int) -> Dict[str, Any]:
        """Resolve an incident and release its active assignments atomically."""
        with self.sync.critical_section():
            with get_db_connection() as conn:
                cur = conn.cursor()
                try:
                    cur.execute(
                        "SELECT status FROM emergency_incidents WHERE incident_id = %s FOR UPDATE",
                        (incident_id,),
                    )
                    incident = cur.fetchone()
                    if incident is None:
                        raise ValueError(f"Emergency {incident_id} does not exist")
                    cur.execute(
                        "SELECT resource_id, team_id, status FROM resource_assignments "
                        "WHERE incident_id = %s FOR UPDATE",
                        (incident_id,),
                    )
                    assignments = cur.fetchall()
                    cur.execute(
                        "UPDATE resource_assignments SET status = 'COMPLETED', "
                        "released_at = CURRENT_TIMESTAMP WHERE incident_id = %s "
                        "AND status IN ('ASSIGNED', 'EN_ROUTE', 'ON_SITE')",
                        (incident_id,),
                    )
                    resource_ids = {row[0] for row in assignments if row[0] is not None}
                    team_ids = {row[1] for row in assignments if row[1] is not None}
                    for resource_id in resource_ids:
                        cur.execute(
                            "UPDATE resources SET status = CASE WHEN EXISTS ("
                            "SELECT 1 FROM resource_assignments "
                            "WHERE resource_id = %s AND status IN ('ASSIGNED', 'EN_ROUTE', 'ON_SITE')"
                            ") THEN 'ASSIGNED' ELSE 'AVAILABLE' END "
                            "WHERE resource_id = %s AND status IN ('AVAILABLE', 'ASSIGNED')",
                            (resource_id, resource_id),
                        )
                    for team_id in team_ids:
                        cur.execute(
                            "UPDATE rescue_teams t SET "
                            "current_capacity = active.assignment_count, "
                            "status = CASE WHEN t.status = 'OFF_DUTY' THEN 'OFF_DUTY' "
                            "WHEN active.assignment_count >= t.max_capacity THEN 'BUSY' "
                            "ELSE 'AVAILABLE' END "
                            "FROM (SELECT COUNT(*)::int AS assignment_count "
                            "FROM resource_assignments "
                            "WHERE team_id = %s AND status IN ('ASSIGNED', 'EN_ROUTE', 'ON_SITE')"
                            ") active WHERE t.team_id = %s",
                            (team_id, team_id),
                        )
                    cur.execute(
                        "UPDATE emergency_incidents SET status = 'RESOLVED', "
                        "resolved_at = CURRENT_TIMESTAMP WHERE incident_id = %s",
                        (incident_id,),
                    )
                    cur.execute(
                        "INSERT INTO emergency_logs (incident_id, action, details, performed_by) "
                        "VALUES (%s, 'RESOLVED', %s, %s)",
                        (incident_id, f"Released {len(assignments)} assignment(s).",
                         threading.current_thread().name),
                    )
                    conn.commit()
                    return {"incident_id": incident_id, "status": "RESOLVED",
                            "released_assignments": sum(
                                row[2] in ("ASSIGNED", "EN_ROUTE", "ON_SITE")
                                for row in assignments
                            ), "transaction": "COMMITTED"}
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    cur.close()

    def request_allocation(
        self,
        incident_id: int,
        demands: Dict[str, int],
        incident_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes a resource allocation request for an active emergency incident.
        Executes within synchronized critical section guarded by Mutex and Semaphore:
          1. Enforces concurrency limit with counting semaphore permit.
          2. Enforces mutual exclusion on Banker's algorithm matrices with mutex lock.
          3. Evaluates Dijkstra's safety algorithm for deadlock avoidance.
          4. If safe, commits assignments in PostgreSQL and broadcasts real-time update.
        """
        logger.info(f"[ResourceManager] Resource request received for Incident #{incident_id}: {demands}")

        with self.sync.acquire_dispatch_permit(timeout=3.0) as permit_granted:
            if not permit_granted:
                return {
                    "allocated": False,
                    "incident_id": incident_id,
                    "reason": "Dispatch concurrency throttled by Semaphore: maximum simultaneous dispatches reached.",
                    "status_code": 429
                }

            with self.sync.critical_section():
                # Ensure process registered in Banker's algorithm
                if incident_id not in self.banker.max_claim:
                    self.banker.register_process(
                        process_id=incident_id,
                        incident_type=incident_type or "CRITICAL_ACCIDENT"
                    )

                # Run Banker's Algorithm safety check
                allocated_safely, reason, safe_sequence = self.banker.request_resources(
                    process_id=incident_id,
                    request_vector=demands
                )

                if not allocated_safely:
                    logger.warning(f"[ResourceManager] Request for Incident #{incident_id} DENIED: {reason}")
                    return {
                        "allocated": False,
                        "incident_id": incident_id,
                        "reason": reason,
                        "banker_denied": True,
                        "status_code": 409
                    }

                # Safe state verified! Proceed with physical assignment in DB
                assigned_items = []
                assigned_teams = []

                try:
                    # Allocate requested ambulances / vehicles
                    amb_needed = demands.get("AMBULANCE", 0)
                    if amb_needed > 0:
                        avail_ambs = ResourceRepository.get_available_resources(resource_type="AMBULANCE")
                        for amb in avail_ambs[:amb_needed]:
                            ResourceRepository.update_resource_status(amb["resource_id"], "ASSIGNED")
                            asgn = ResourceRepository.create_assignment(
                                incident_id=incident_id,
                                resource_id=amb["resource_id"]
                            )
                            assigned_items.append(amb)

                    # Allocate requested rescue teams
                    teams_needed = demands.get("RESCUE_TEAM", 0)
                    if teams_needed > 0:
                        avail_teams = RescueTeamRepository.get_available_teams()
                        for team in avail_teams[:teams_needed]:
                            asgn = ResourceRepository.create_assignment(
                                incident_id=incident_id,
                                team_id=team["team_id"]
                            )
                            assigned_teams.append(team)

                    # Update incident status to RESOURCE_ASSIGNED
                    EmergencyRepository.update_incident_status(
                        incident_id=incident_id,
                        status="RESOURCE_ASSIGNED",
                        action="RESOURCES_ALLOCATED",
                        details=f"Banker's Algorithm approved allocation. Vehicles: {len(assigned_items)}, Teams: {len(assigned_teams)}.",
                        performed_by="ResourceManager"
                    )

                    result_payload = {
                        "allocated": True,
                        "incident_id": incident_id,
                        "resources_assigned": assigned_items,
                        "teams_assigned": assigned_teams,
                        "safe_sequence": safe_sequence,
                        "banker_state": self.banker.get_state(),
                        "message": "Resource allocated successfully under safe deadlock avoidance state.",
                    }

                    # Broadcast real-time allocation
                    try:
                        broadcast_emergency_update(
                            event_type="resource_allocated",
                            payload={
                                "incident_id": incident_id,
                                "demands": demands,
                                "safe_sequence": safe_sequence
                            }
                        )
                    except Exception as ws_err:
                        logger.warning(f"Failed to broadcast resource allocation Socket.IO: {ws_err}")

                    return result_payload

                except Exception as db_err:
                    logger.error(f"[ResourceManager] DB error assigning physical resources: {db_err}")
                    # Revert Banker's allocation if DB write fails
                    self.banker.release_resources(incident_id, demands)
                    return {
                        "allocated": False,
                        "incident_id": incident_id,
                        "reason": f"Database transaction failed: {db_err}",
                        "status_code": 500
                    }

    def release_allocation(self, incident_id: int) -> Dict[str, Any]:
        """
        Releases all resources and teams held by an incident back to the pool.
        """
        with self.sync.critical_section():
            # Release DB records
            released_count = ResourceRepository.release_incident_assignments(incident_id)

            # Reclaim in Banker's algorithm
            reclaimed_vector = self.banker.unregister_process(incident_id)

            # Update incident status to RESOLVED
            try:
                EmergencyRepository.update_incident_status(
                    incident_id=incident_id,
                    status="RESOLVED",
                    action="RESOURCES_RELEASED",
                    details=f"Released {released_count} active assignments back to available pool.",
                    performed_by="ResourceManager"
                )
            except Exception as e:
                logger.error(f"[ResourceManager] Error marking incident #{incident_id} resolved: {e}")

            logger.info(
                f"[ResourceManager] Released resources for incident #{incident_id}: "
                f"{reclaimed_vector} ({released_count} DB records updated)."
            )

            try:
                broadcast_emergency_update(
                    event_type="resource_released",
                    payload={"incident_id": incident_id, "reclaimed": reclaimed_vector}
                )
            except Exception as ws_err:
                logger.warning(f"Failed to broadcast resource release Socket.IO: {ws_err}")

            return {
                "status": "success",
                "incident_id": incident_id,
                "released_assignments": released_count,
                "reclaimed_vector": reclaimed_vector,
                "banker_state": self.banker.get_state(),
            }

    def get_system_state(self) -> Dict[str, Any]:
        """Returns consolidated snapshot of OS synchronization, Banker's state, and DB fleet."""
        return {
            "banker_algorithm": self.banker.get_state(),
            "synchronization": self.sync.get_sync_metrics(),
        }

# Global shared instance of ResourceManager
resource_manager: ResourceManager = ResourceManager()
