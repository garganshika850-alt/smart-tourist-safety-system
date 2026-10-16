# ============================================================
# Smart Tourist Safety and Emergency Response System
# Worker: Geofence Intrusion & Hazardous Zone Processing
# ============================================================

from typing import Any, Dict
from backend.scheduler.priority_queue import EmergencyEvent
from backend.db.repositories import EmergencyRepository
from backend.workers.notification_worker import NotificationWorker
from backend.utils.logger import logger

class GeofenceWorker:
    """Worker processing dangerous zone intrusions and perimeter breach events."""

    @staticmethod
    def process_event(event: EmergencyEvent) -> Dict[str, Any]:
        """
        Processes a DANGEROUS_ZONE event, updates incident state, and notifies dispatchers.
        """
        logger.info(
            f"[GeofenceWorker] Handling geofence alert #{event.event_id} "
            f"for Tourist #{event.tourist_id} at ({event.latitude}, {event.longitude})"
        )

        zone_data = event.payload.get("zone", {})
        zone_name = zone_data.get("zone_name", "Hazardous Zone")
        risk_level = zone_data.get("risk_level", "HIGH")

        # Update incident status in DB if associated with an incident
        if event.incident_id:
            try:
                EmergencyRepository.update_incident_status(
                    incident_id=event.incident_id,
                    status="PROCESSING",
                    action="GEOFENCE_WORKER_PROCESSED",
                    details=f"Geofence breach confirmed in {zone_name} (Risk: {risk_level}).",
                    performed_by="GeofenceWorker"
                )
            except Exception as e:
                logger.error(f"[GeofenceWorker] Could not update incident #{event.incident_id}: {e}")

        # Broadcast urgent alert
        NotificationWorker.dispatch(
            event_type="geofence_alert",
            message=f"DANGER: Tourist #{event.tourist_id} in {zone_name} [{risk_level}].",
            payload={
                "incident_id": event.incident_id,
                "tourist_id": event.tourist_id,
                "zone_name": zone_name,
                "risk_level": risk_level,
                "latitude": event.latitude,
                "longitude": event.longitude,
            }
        )

        return {
            "status": "processed",
            "worker": "GeofenceWorker",
            "event_id": event.event_id,
            "incident_id": event.incident_id,
            "zone_name": zone_name,
            "risk_level": risk_level,
        }
