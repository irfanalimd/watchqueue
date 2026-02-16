"""WebSocket endpoints for real-time updates."""

import asyncio
import json
import logging
from typing import Any
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.database import get_database, Database
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections for rooms."""

    def __init__(self):
        # room_id -> set of WebSocket connections
        self.active_connections: dict[str, set[WebSocket]] = {}
        # WebSocket -> user_id mapping
        self.user_mapping: dict[WebSocket, str] = {}
        # WebSocket -> user display name mapping
        self.user_name_mapping: dict[WebSocket, str] = {}
        # (room_id, user_id) -> delayed leave broadcast task
        self.pending_leave_tasks: dict[tuple[str, str], asyncio.Task] = {}
        # Delay before announcing a user left, to absorb quick refresh reconnects
        self.leave_grace_seconds = 2.0

    def _has_user_connection(self, room_id: str, user_id: str) -> bool:
        """Check if a user currently has any active connection in room."""
        if room_id not in self.active_connections:
            return False
        for connection in self.active_connections[room_id]:
            if self.user_mapping.get(connection) == user_id:
                return True
        return False

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str, user_name: str | None = None):
        """Accept and register a WebSocket connection."""
        await websocket.accept()

        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()

        was_online = self._has_user_connection(room_id, user_id)

        # Cancel pending leave if user reconnected within grace period
        leave_key = (room_id, user_id)
        pending = self.pending_leave_tasks.pop(leave_key, None)
        if pending:
            pending.cancel()

        self.active_connections[room_id].add(websocket)
        self.user_mapping[websocket] = user_id
        if user_name:
            self.user_name_mapping[websocket] = user_name

        # Notify room about new user
        if not was_online:
            await self.broadcast(
                room_id,
                {
                    "type": "user_joined",
                    "user_id": user_id,
                    "user_name": user_name or user_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                exclude=websocket,
            )

        logger.info(f"User {user_id} connected to room {room_id}")

    async def disconnect(self, websocket: WebSocket, room_id: str):
        """Remove a WebSocket connection."""
        user_id = self.user_mapping.pop(websocket, None)
        user_name = self.user_name_mapping.pop(websocket, None)
        if not user_name and user_id:
            user_name = await resolve_member_name(room_id, user_id)

        if room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)

            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

            # Notify room about user leaving with grace period to avoid refresh flicker
            if user_id and not self._has_user_connection(room_id, user_id):
                leave_key = (room_id, user_id)
                self.pending_leave_tasks[leave_key] = asyncio.create_task(
                    self._broadcast_left_after_grace(
                        room_id=room_id,
                        user_id=user_id,
                        user_name=user_name or user_id,
                    )
                )

        logger.info(f"User {user_id} disconnected from room {room_id}")

    async def _broadcast_left_after_grace(self, room_id: str, user_id: str, user_name: str):
        """Broadcast user_left only if user stays disconnected after grace window."""
        leave_key = (room_id, user_id)
        try:
            await asyncio.sleep(self.leave_grace_seconds)
            if self._has_user_connection(room_id, user_id):
                return
            await self.broadcast(
                room_id,
                {
                    "type": "user_left",
                    "user_id": user_id,
                    "user_name": user_name or user_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except asyncio.CancelledError:
            return
        finally:
            self.pending_leave_tasks.pop(leave_key, None)

    async def broadcast(
        self,
        room_id: str,
        message: dict[str, Any],
        exclude: WebSocket | None = None,
    ):
        """Broadcast a message to all connections in a room."""
        if room_id not in self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections[room_id]:
            if connection == exclude:
                continue
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        # Clean up disconnected sockets
        for conn in disconnected:
            self.active_connections[room_id].discard(conn)
            self.user_mapping.pop(conn, None)
            self.user_name_mapping.pop(conn, None)

    async def send_to_user(
        self,
        room_id: str,
        user_id: str,
        message: dict[str, Any],
    ):
        """Send a message to a specific user in a room."""
        if room_id not in self.active_connections:
            return

        for connection in self.active_connections[room_id]:
            if self.user_mapping.get(connection) == user_id:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    def get_room_users(self, room_id: str) -> list[str]:
        """Get list of connected users in a room."""
        if room_id not in self.active_connections:
            return []

        users: list[str] = []
        seen: set[str] = set()
        for connection in self.active_connections[room_id]:
            user_id = self.user_mapping.get(connection)
            if user_id and user_id not in seen:
                users.append(user_id)
                seen.add(user_id)
        return users


# Global connection manager
manager = ConnectionManager()


async def resolve_member_name(room_id: str, user_id: str) -> str | None:
    """Resolve user's display name from room membership."""
    if not ObjectId.is_valid(room_id):
        return None

    db = Database.get_db()
    room = await db.rooms.find_one(
        {"_id": ObjectId(room_id)},
        {"members": 1},
    )
    if not room:
        return None

    for member in room.get("members", []):
        if member.get("user_id") == user_id:
            return member.get("name")
    return None


@router.websocket("/ws/{room_id}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    user_id: str,
):
    """WebSocket endpoint for room real-time updates.

    Handles:
    - Vote updates (broadcast when any user votes)
    - Queue changes (new items, removed items)
    - Selection events (when a movie is selected)
    - Presence (who's online in the room)
    - Heartbeat for connection health
    """
    settings = get_settings()

    query_user_name = websocket.query_params.get("user_name")
    resolved_user_name = query_user_name or await resolve_member_name(room_id, user_id)
    await manager.connect(websocket, room_id, user_id, user_name=resolved_user_name)

    # Send current online users
    await websocket.send_json({
        "type": "presence",
        "users": manager.get_room_users(room_id),
        "timestamp": datetime.utcnow().isoformat(),
    })

    try:
        # Start heartbeat task
        heartbeat_task = asyncio.create_task(
            send_heartbeat(websocket, settings.ws_heartbeat_interval)
        )

        while True:
            try:
                # Wait for messages with timeout
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=float(settings.ws_heartbeat_interval * 2),
                )

                # Handle different message types
                await handle_client_message(websocket, room_id, user_id, data)

            except asyncio.TimeoutError:
                # Check if connection is still alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        heartbeat_task.cancel()
        await manager.disconnect(websocket, room_id)


async def send_heartbeat(websocket: WebSocket, interval: int):
    """Send periodic heartbeat to keep connection alive."""
    while True:
        try:
            await asyncio.sleep(interval)
            await websocket.send_json({
                "type": "heartbeat",
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception:
            break


async def handle_client_message(
    websocket: WebSocket,
    room_id: str,
    user_id: str,
    data: dict[str, Any],
):
    """Handle messages received from client."""
    msg_type = data.get("type")

    if msg_type == "pong":
        # Heartbeat response, connection is alive
        pass

    elif msg_type == "vote":
        # Client is voting - broadcast to others
        await manager.broadcast(
            room_id,
            {
                "type": "vote_update",
                "item_id": data.get("item_id"),
                "user_id": user_id,
                "vote": data.get("vote"),
                "timestamp": datetime.utcnow().isoformat(),
            },
            exclude=websocket,
        )

    elif msg_type == "queue_add":
        # Client added item to queue - broadcast to others
        await manager.broadcast(
            room_id,
            {
                "type": "queue_update",
                "action": "add",
                "item_id": data.get("item_id"),
                "title": data.get("title"),
                "added_by": user_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
            exclude=websocket,
        )

    elif msg_type == "selection":
        # Movie was selected - broadcast to all
        await manager.broadcast(
            room_id,
            {
                "type": "selection",
                "item_id": data.get("item_id"),
                "title": data.get("title"),
                "poster_url": data.get("poster_url"),
                "queue_snapshot": data.get("queue_snapshot", []),
                "selected_by": user_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    elif msg_type == "reaction":
        # Client toggled reaction - broadcast to others
        await manager.broadcast(
            room_id,
            {
                "type": "reaction_update",
                "item_id": data.get("item_id"),
                "user_id": user_id,
                "reaction": data.get("reaction"),
                "active": data.get("active"),
                "timestamp": datetime.utcnow().isoformat(),
            },
            exclude=websocket,
        )

    elif msg_type == "voting_round_start":
        # Voting round started - broadcast to all
        await manager.broadcast(
            room_id,
            {
                "type": "voting_round_start",
                "duration_seconds": data.get("duration_seconds"),
                "started_by": user_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    elif msg_type == "get_presence":
        # Client requesting current presence
        await websocket.send_json({
            "type": "presence",
            "users": manager.get_room_users(room_id),
            "timestamp": datetime.utcnow().isoformat(),
        })


async def broadcast_vote_update(room_id: str, item_id: str, vote_counts: dict):
    """Broadcast vote count update to all users in a room.

    Called by the voting service after a vote is recorded.
    """
    await manager.broadcast(
        room_id,
        {
            "type": "vote_counts",
            "item_id": item_id,
            **vote_counts,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


async def broadcast_queue_update(room_id: str, action: str, item: dict):
    """Broadcast queue update to all users in a room."""
    await manager.broadcast(
        room_id,
        {
            "type": "queue_update",
            "action": action,
            "item": item,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
