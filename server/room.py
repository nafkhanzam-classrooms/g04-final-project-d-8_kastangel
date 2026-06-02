"""
room.py - Room and session management for CodeDuel.
"""

import threading
import time
import uuid
from typing import Optional, TYPE_CHECKING

from . import logger, protocol, ranking
from .game_state import GameState, GameStatus
from .questions import get_questions, get_client_question
from .replay import load_replay

if TYPE_CHECKING:
    from .game_server import ClientHandler

MAX_PLAYERS = 2
RECONNECT_TIMEOUT = 30  # seconds a disconnected player has to reconnect
QUESTIONS_PER_MATCH = 10


class Room:
    """
    Manages one 1v1 match session including:
    - Player slots
    - Spectator list
    - Game state
    - Reconnect grace period
    """

    def __init__(self, room_id: Optional[str] = None):
        self.room_id       = room_id or str(uuid.uuid4())[:8].upper()
        self.players: dict[str, "ClientHandler"] = {}   # username → handler
        self.spectators: list["ClientHandler"]   = []
        self.disconnected: dict[str, float]      = {}   # username → disconnect_ts
        self.game: Optional[GameState]           = None
        self.created_at    = time.time()
        self._lock         = threading.Lock()
        self._started      = False
        self._finished     = False

    # ------------------------------------------------------------------
    # Player management
    # ------------------------------------------------------------------

    def add_player(self, username: str, handler: "ClientHandler") -> bool:
        """Add a player. Returns True if added, False if room is full."""
        with self._lock:
            if len(self.players) >= MAX_PLAYERS:
                return False
            self.players[username] = handler
            return True

    def remove_player(self, username: str):
        """Mark a player as disconnected (not immediately removed for reconnect)."""
        with self._lock:
            if username in self.players:
                self.disconnected[username] = time.time()
                # Keep slot but remove live handler reference
                del self.players[username]
                if self.game:
                    self.game.replay.record_disconnect(username)
        logger.log_disconnect(username, "")

    def reconnect_player(self, username: str, handler: "ClientHandler") -> bool:
        """Reconnect a previously disconnected player."""
        with self._lock:
            if username not in self.disconnected:
                return False
            ts = self.disconnected[username]
            if time.time() - ts > RECONNECT_TIMEOUT:
                return False
            self.players[username] = handler
            del self.disconnected[username]
            if self.game:
                self.game.replay.record_reconnect(username)
        logger.log_reconnect(username, self.room_id, True)
        return True

    def is_full(self) -> bool:
        with self._lock:
            return len(self.players) + len(self.disconnected) >= MAX_PLAYERS

    def has_player(self, username: str) -> bool:
        with self._lock:
            return username in self.players or username in self.disconnected

    def is_player_disconnected(self, username: str) -> bool:
        with self._lock:
            return username in self.disconnected

    def get_player_names(self) -> list[str]:
        with self._lock:
            return list(self.players.keys()) + list(self.disconnected.keys())

    # ------------------------------------------------------------------
    # Spectators
    # ------------------------------------------------------------------

    def add_spectator(self, handler: "ClientHandler"):
        with self._lock:
            self.spectators.append(handler)

    def remove_spectator(self, handler: "ClientHandler"):
        with self._lock:
            if handler in self.spectators:
                self.spectators.remove(handler)

    def spectator_count(self) -> int:
        with self._lock:
            return len(self.spectators)

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    def broadcast(self, packet: dict, exclude: Optional[str] = None):
        """Send packet to all connected players and spectators."""
        with self._lock:
            recipients = list(self.players.values()) + list(self.spectators)

        for handler in recipients:
            if exclude and getattr(handler, "username", None) == exclude:
                continue
            handler.send(packet)

    def broadcast_players(self, packet: dict, exclude: Optional[str] = None):
        """Send packet to players only."""
        with self._lock:
            recipients = list(self.players.values())
        for handler in recipients:
            if exclude and getattr(handler, "username", None) == exclude:
                continue
            handler.send(packet)

    # ------------------------------------------------------------------
    # Game lifecycle
    # ------------------------------------------------------------------

    def try_start_game(self):
        """Start the game if both players are present and game not started."""
        with self._lock:
            if self._started:
                return
            total_expected = MAX_PLAYERS
            connected = len(self.players)
            if connected < total_expected:
                return
            self._started = True
            players = list(self.players.keys())

        questions = get_questions(n=QUESTIONS_PER_MATCH)
        self.game = GameState(
            room_id    = self.room_id,
            players    = players,
            questions  = questions,
            on_question      = self._cb_question,
            on_answer_result = self._cb_answer_result,
            on_game_state    = self._cb_game_state,
            on_game_over     = self._cb_game_over,
        )

        # Notify players
        start_pkt = protocol.make_start_game(
            self.room_id, players, len(questions)
        )
        self.broadcast(start_pkt)
        self.game.start()

    # ------------------------------------------------------------------
    # Game callbacks
    # ------------------------------------------------------------------

    def _cb_question(self, state: GameState):
        q = state.questions[state.q_index]
        pkt = protocol.make_question(
            room_id    = self.room_id,
            index      = state.q_index,
            total      = state.total_q,
            question   = get_client_question(q),
            time_limit = 20,
        )
        self.broadcast(pkt)

    def _cb_answer_result(self, state: GameState, username: str,
                          correct: bool, points: int):
        pkt = protocol.make_answer_result(
            room_id  = self.room_id,
            username = username,
            correct  = correct,
            points   = points,
            scores   = state.scores,
        )
        self.broadcast(pkt)

    def _cb_game_state(self, state: GameState):
        snap = state.snapshot()
        pkt  = protocol.make_game_state(
            room_id         = self.room_id,
            scores          = snap["scores"],
            question_index  = snap["question_index"],
            status          = snap["status"],
            players_answered= snap["players_answered"],
        )
        self.broadcast(pkt)

    def _cb_game_over(self, state: GameState):
        winner = getattr(state, "_winner", None)
        loser  = getattr(state, "_loser", None)
        scores = dict(state.scores)

        pkt = protocol.make_game_over(
            room_id = self.room_id,
            winner  = winner,
            scores  = scores,
            reason  = "all_questions_done",
        )
        self.broadcast(pkt)

        # Update ranking
        ranking.record_result(winner, loser, scores)

        with self._lock:
            self._finished = True

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        with self._lock:
            status = "waiting"
            if self._finished:
                status = "finished"
            elif self._started:
                status = "in_progress"
            return {
                "room_id":    self.room_id,
                "players":    self.get_player_names(),
                "spectators": self.spectator_count(),
                "status":     status,
            }


# ---------------------------------------------------------------------------
# Room registry (global)
# ---------------------------------------------------------------------------

_rooms: dict[str, Room] = {}
_rooms_lock = threading.Lock()


def create_room(room_id: Optional[str] = None) -> Room:
    room = Room(room_id)
    with _rooms_lock:
        _rooms[room.room_id] = room
    return room


def get_room(room_id: str) -> Optional[Room]:
    with _rooms_lock:
        return _rooms.get(room_id)


def list_rooms() -> list[dict]:
    with _rooms_lock:
        return [r.to_dict() for r in _rooms.values()]


def cleanup_finished_rooms():
    """Remove finished rooms older than 5 minutes."""
    cutoff = time.time() - 300
    with _rooms_lock:
        to_del = [
            rid for rid, r in _rooms.items()
            if r._finished and r.created_at < cutoff
        ]
        for rid in to_del:
            del _rooms[rid]
