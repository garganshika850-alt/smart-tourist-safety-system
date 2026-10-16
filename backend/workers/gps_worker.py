# ============================================================
# Smart Tourist Safety and Emergency Response System
# Worker: GPS Telemetry & Movement Processing
# ============================================================

from typing import Any, Dict
from backend.scheduler.priority_queue import EmergencyEvent, PRIORITY_DANGEROUS_ZONE
from backend.workers.notification_worker import NotificationWorker
from backend.utils.logger import logger

class GPSWorker:
    """Worker processing background GPS location telemetry and geofence boundary checks."""

    @staticmethod
    def process_event(event: EmergencyEvent, scheduler_instance=None) -> Dict[str, Any]:
        """
        Processes a GPS update event. If a dangerous zone breach is detected,
        escalates by generating a higher-priority geofence breach event.
        """
        logger.info(
            f"[GPSWorker] Processing Event #{event.event_id} for Tourist #{event.tourist_id} "
            f"at ({event.latitude}, {event.longitude})"
        )

        zone_data = event.payload.get("zone")
        is_breach = False
        escalated_event_id = None

        if zone_data and zone_data.get("zone_type") == "DANGEROUS":
            is_breach = True
            zone_name = zone_data.get("zone_name", "Unknown Hazardous Area")
            risk_level = zone_data.get("risk_level", "HIGH")
            logger.warning(
                f"[GPSWorker] Escalation: Tourist #{event.tourist_id} inside dangerous zone '{zone_name}' ({risk_level})!"
            )

            # Escalate: Enqueue higher-priority DANGEROUS_ZONE event if scheduler provided
            if scheduler_instance:
                escalated_event = EmergencyEvent(
                    priority=PRIORITY_DANGEROUS_ZONE,
                    tourist_id=event.tourist_id,
                    event_type="DANGEROUS_ZONE",
                    latitude=event.latitude,
                    longitude=event.longitude,
                    payload={
                        "zone": zone_data,
                        "escalated_from": event.event_id,
                        "description": f"Automated geofence breach in {zone_name}."
                    }
                )
                scheduler_instance.enqueue(escalated_event)
                escalated_event_id = escalated_event.event_id

            NotificationWorker.dispatch(
                event_type="geofence_warning",
                message=f"WARNING: You are in hazardous area {zone_name} ({risk_level}).",
                payload={"tourist_id": event.tourist_id, "zone": zone_data}
            )

        return {
            "status": "processed",
            "worker": "GPSWorker",
            "event_id": event.event_id,
            "tourist_id": event.tourist_id,
            "geofence_breach": is_breach,
            "escalated_event_id": escalated_event_id,
        }
