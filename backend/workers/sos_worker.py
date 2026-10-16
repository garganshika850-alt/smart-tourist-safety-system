# ============================================================
# Smart Tourist Safety and Emergency Response System
# Worker: SOS & Critical Accident Dispatch Processing
# ============================================================

from typing import Any, Dict
from backend.scheduler.priority_queue import EmergencyEvent
from backend.db.repositories import EmergencyRepository
from backend.workers.notification_worker import NotificationWorker
from backend.utils.logger import logger

class SOSWorker:
    """Worker processing high-priority SOS distress signals and critical accidents."""

    @staticmethod
    def process_event(event: EmergencyEvent, resource_manager=None) -> Dict[str, Any]:
        """
        Processes critical emergency distress events, marks incident as PROCESSING,
        and requests resource allocation.
        """
        logger.warning(
            f"[SOSWorker] Emergency dispatch started for Event #{event.event_id} "
            f"[{event.event_type}] Priority={event.priority} (Tourist #{event.tourist_id})"
        )

        allocation_result = None

        # Update database incident status
        if event.incident_id:
            try:
                EmergencyRepository.update_incident_status(
                    incident_id=event.incident_id,
                    status="PROCESSING",
                    action="SOS_WORKER_DISPATCHED",
                    details=f"Dispatched by worker thread for event '{event.event_type}' (Priority {event.priority}).",
                    performed_by="SOSWorker"
                )
            except Exception as e:
                logger.error(f"[SOSWorker] Failed to update incident #{event.incident_id}: {e}")

        # Request resource allocation through Resource Manager if available
        if resource_manager and event.incident_id:
            try:
                # Severity-based demand mapping
                if event.priority == 1:  # CRITICAL_ACCIDENT
                    demands = {"AMBULANCE": 1, "RESCUE_TEAM": 1, "HELICOPTER": 0}
                elif event.priority == 2:  # SOS
                    demands = {"AMBULANCE": 1, "RESCUE_TEAM": 0, "HELICOPTER": 0}
                else:
                    demands = {"AMBULANCE": 0, "RESCUE_TEAM": 1, "HELICOPTER": 0}

                allocation_result = resource_manager.request_allocation(
                    incident_id=event.incident_id,
                    demands=demands
                )
            except Exception as e:
                logger.error(f"[SOSWorker] Resource allocation request failed: {e}")

        # Dispatch real-time emergency alert
        NotificationWorker.dispatch(
            event_type="emergency_dispatched",
            message=f"CRITICAL DISPATCH: {event.event_type} (Priority {event.priority}) active for tourist #{event.tourist_id}.",
            payload={
                "event_id": event.event_id,
                "incident_id": event.incident_id,
                "tourist_id": event.tourist_id,
                "priority": event.priority,
                "latitude": event.latitude,
                "longitude": event.longitude,
                "allocation": allocation_result,
            }
        )

        return {
            "status": "processed",
            "worker": "SOSWorker",
            "event_id": event.event_id,
            "incident_id": event.incident_id,
            "priority": event.priority,
            "allocation": allocation_result,
        }
