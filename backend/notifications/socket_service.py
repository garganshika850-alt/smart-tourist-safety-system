# ============================================================
# Smart Tourist Safety and Emergency Response System
# WebSocket Notification Service (Flask-SocketIO)
# ============================================================

from typing import Any, Dict, Optional
from flask_socketio import SocketIO, emit, join_room, leave_room
from backend.utils.logger import logger

# Global SocketIO instance
socketio: SocketIO = SocketIO()

def init_socketio(app, async_mode: str = "threading") -> SocketIO:
    """
    Initializes Flask-SocketIO with the application instance.
    Uses 'threading' mode for seamless multithreading compatibility.
    """
    logger.info(f"Initializing Flask-SocketIO with async_mode='{async_mode}'...")
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode=async_mode,
        logger=False,
        engineio_logger=False,
    )
    register_socket_events(socketio)
    return socketio

def register_socket_events(sio: SocketIO) -> None:
    """Registers standard Socket.IO event listeners."""

    @sio.on("connect")
    def handle_connect():
        logger.info("WebSocket client connected.")
        emit("connection_ack", {"status": "connected", "message": "Connected to tourist safety hub"})

    @sio.on("disconnect")
    def handle_disconnect():
        logger.info("WebSocket client disconnected.")

    @sio.on("join_room")
    def handle_join_room(data: Dict[str, Any]):
        room = data.get("room")
        if room:
            join_room(room)
            logger.info(f"Client joined room: {room}")
            emit("room_joined", {"room": room}, to=room)

    @sio.on("leave_room")
    def handle_leave_room(data: Dict[str, Any]):
        room = data.get("room")
        if room:
            leave_room(room)
            logger.info(f"Client left room: {room}")

def broadcast_emergency_update(event_type: str, payload: Dict[str, Any], room: Optional[str] = None) -> None:
    """
    Broadcasts real-time emergency events to dashboard and mobile subscribers.
    If room is specified (e.g. 'dashboard' or 'tourist_123'), emits only to that room.
    """
    logger.info(f"Broadcasting Socket.IO event '{event_type}' (room={room})...")
    if room:
        socketio.emit(event_type, payload, to=room)
    else:
        socketio.emit(event_type, payload)
