import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import WebSocket

logger = logging.getLogger("websocket.hub")


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._socket_org: dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, user_id: uuid.UUID, org_id: uuid.UUID) -> None:
        org_key = str(org_id)
        self.connections[org_key].add(websocket)
        self._socket_org[websocket] = org_key

        await websocket.send_json(
            {
                "event": "connection.established",
                "data": {"user_id": str(user_id), "org_id": org_key},
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )

    def disconnect(self, websocket: WebSocket) -> None:
        org_key = self._socket_org.pop(websocket, None)
        if org_key is None:
            return
        sockets = self.connections.get(org_key)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            del self.connections[org_key]

    async def broadcast_to_org(self, org_id: str, message: dict) -> None:
        stale: list[WebSocket] = []
        for ws in list(self.connections.get(org_id, ())):
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)

        for ws in stale:
            logger.debug("Dropping stale connection for org %s", org_id)
            self.disconnect(ws)

    def get_connection_count(self, org_id: str) -> int:
        return len(self.connections.get(org_id, ()))


hub = ConnectionManager()
