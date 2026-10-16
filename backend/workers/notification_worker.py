# ============================================================
# Smart Tourist Safety and Emergency Response System
# Worker: Notification Dispatch
# ============================================================

from typing import Any, Dict, Optional
from backend.notifications.socket_service import broadcast_emergency_update
from backend.utils.logger import logger

class NotificationWorker:
    """Handles asynchronous dispatch of emergency notifications to mobile apps and dashboards."""

    @staticmethod
    def dispatch(
        event_type: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        room: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Dispatches real-time broadcast and records delivery.
        """
        data = {
            "event_type": event_type,
            "message": message,
            "payload": payload or {},
        }
        logger.info(f"[NotificationWorker] Dispatching '{event_type}': {message}")
        try:
            broadcast_emergency_update(event_type=event_type, payload=data, room=room)
            data["delivered"] = True
        except Exception as e:
            logger.warning(f"[NotificationWorker] Failed to dispatch via Socket.IO: {e}")
            data["delivered"] = False
            data["delivery_error"] = str(e)
        return data
