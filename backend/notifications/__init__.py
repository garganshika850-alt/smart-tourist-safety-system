# ============================================================
# Smart Tourist Safety and Emergency Response System
# Notifications Subsystem Exports
# ============================================================

from backend.notifications.socket_service import (
    socketio,
    init_socketio,
    broadcast_emergency_update,
)

__all__ = [
    "socketio",
    "init_socketio",
    "broadcast_emergency_update",
]
