"""
matchmaking.py - Matchmaking queue for CodeDuel.

Players enter the queue; when 2 are available they are matched into a new room.
"""

import threading
import time
from typing import Optional, TYPE_CHECKING

from . import logger, protocol
from .room import create_room, Room

if TYPE_CHECKING:
    from .game_server import ClientHandler


class MatchmakingQueue:
    """Thread-safe FIFO matchmaking queue."""

    def __init__(self):
        self._queue: list[tuple[str, "ClientHandler"]] = []
        self._lock  = threading.Lock()
        self._event = threading.Event()

        # Start background matcher thread
        t = threading.Thread(target=self._matcher_loop, daemon=True)
        t.start()

    def enqueue(self, username: str, handler: "ClientHandler"):
        """Add a player to the matchmaking queue."""
        with self._lock:
            # Avoid duplicates
            if any(u == username for u, _ in self._queue):
                return
            self._queue.append((username, handler))
            logger.log_matchmake(username)
        self._event.set()

    def dequeue(self, username: str):
        """Remove a player from the queue (e.g. if they disconnect)."""
        with self._lock:
            self._queue = [(u, h) for u, h in self._queue if u != username]

    def queue_length(self) -> int:
        with self._lock:
            return len(self._queue)

    # ------------------------------------------------------------------
    # Background matcher
    # ------------------------------------------------------------------

    def _matcher_loop(self):
        while True:
            self._event.wait(timeout=1.0)
            self._event.clear()
            self._try_match()

    def _try_match(self):
        with self._lock:
            if len(self._queue) < 2:
                return
            p1_name, p1_handler = self._queue.pop(0)
            p2_name, p2_handler = self._queue.pop(0)

        # Create a new room and add both players
        room = create_room()
        room.add_player(p1_name, p1_handler)
        room.add_player(p2_name, p2_handler)

        # Update handler references
        p1_handler.room = room
        p2_handler.room = room

        logger.log_matched(room.room_id, p1_name, p2_name)

        # Notify both players
        p1_handler.send(protocol.make_matched(room.room_id, p2_name))
        p2_handler.send(protocol.make_matched(room.room_id, p1_name))

        # Notify room joined
        players = room.get_player_names()
        p1_handler.send(protocol.make_room_joined(room.room_id, players))
        p2_handler.send(protocol.make_room_joined(room.room_id, players))

        # Start the game
        room.try_start_game()


# Singleton queue
_queue = MatchmakingQueue()


def get_queue() -> MatchmakingQueue:
    return _queue
