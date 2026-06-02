"""
game_state.py - Game state machine for a single CodeDuel match.
"""

import threading
import time
from enum import Enum, auto
from typing import Optional, Callable

from . import logger
from .questions import get_client_question
from .replay import ReplayRecorder


class GameStatus(Enum):
    WAITING    = auto()  # Waiting for both players
    COUNTDOWN  = auto()  # Short countdown before first question
    QUESTION   = auto()  # Question is active
    REVIEWING  = auto()  # Both answered / timed out, showing result
    GAME_OVER  = auto()  # Match finished


TIME_PER_QUESTION = 20   # seconds
REVIEW_DURATION   = 3    # seconds between questions
POINTS_PER_CORRECT = 100  # base; actual from question data


class GameState:
    """
    Manages the full lifecycle of a 1v1 match.

    Callbacks are called from timer threads — the caller must ensure
    thread-safety when accessing shared state.
    """

    def __init__(
        self,
        room_id: str,
        players: list[str],
        questions: list[dict],
        on_question: Callable,       # (state) → None
        on_answer_result: Callable,  # (state, username, correct, points) → None
        on_game_state: Callable,     # (state) → None
        on_game_over: Callable,      # (state) → None
    ):
        self.room_id      = room_id
        self.players      = players          # [p1, p2]
        self.questions    = questions        # Full list including answers
        self.total_q      = len(questions)

        self.scores       = {p: 0 for p in players}
        self.status       = GameStatus.WAITING
        self.q_index      = -1              # Current question index
        self.answered     = {}              # {username: answer}
        self.q_start_ts   = 0.0

        self.replay       = ReplayRecorder(room_id, players)

        self._lock        = threading.Lock()
        self._timer: Optional[threading.Timer] = None

        # Callbacks
        self._on_question      = on_question
        self._on_answer_result = on_answer_result
        self._on_game_state    = on_game_state
        self._on_game_over     = on_game_over

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Begin the match — sends first question after a brief pause."""
        with self._lock:
            self.status = GameStatus.COUNTDOWN
        logger.log_start_game(self.room_id, self.players)
        self._schedule(2, self._next_question)

    def submit_answer(self, username: str, q_index: int, answer: str) -> bool:
        """
        Process a player's answer.
        Returns False if the answer is rejected (wrong question index, already answered, etc.)
        """
        with self._lock:
            if self.status != GameStatus.QUESTION:
                return False
            if q_index != self.q_index:
                return False
            if username not in self.players:
                return False
            if username in self.answered:
                return False  # Already answered

            q   = self.questions[self.q_index]
            correct = answer.upper() == q["answer"].upper()
            points  = q.get("points", POINTS_PER_CORRECT) if correct else 0
            self.scores[username] += points
            self.answered[username] = answer

            self.replay.record_answer(
                username, q_index, answer, correct, points, dict(self.scores)
            )

        logger.log_answer(username, self.room_id, q_index, correct, points)
        self._on_answer_result(self, username, correct, points)
        self._on_game_state(self)

        # If all players answered, move on
        with self._lock:
            if set(self.answered.keys()) == set(self.players):
                self._cancel_timer()
                self._schedule(REVIEW_DURATION, self._next_question)

        return True

    def handle_timeout(self):
        """Called when the question timer expires."""
        with self._lock:
            if self.status != GameStatus.QUESTION:
                return
            self.replay.record_timeout(self.q_index)

        self._on_game_state(self)
        self._schedule(REVIEW_DURATION, self._next_question)

    def snapshot(self) -> dict:
        """Return a JSON-safe snapshot of the current game state."""
        with self._lock:
            q = self.questions[self.q_index] if self.q_index >= 0 else None
            elapsed = time.time() - self.q_start_ts if self.q_start_ts else 0
            remaining = max(0, TIME_PER_QUESTION - elapsed) if q else 0
            return {
                "room_id":          self.room_id,
                "status":           self.status.name,
                "players":          self.players,
                "scores":           dict(self.scores),
                "question_index":   self.q_index,
                "total_questions":  self.total_q,
                "time_remaining":   round(remaining, 1),
                "players_answered": list(self.answered.keys()),
                "current_question": get_client_question(q) if q else None,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _next_question(self):
        with self._lock:
            self.q_index += 1
            if self.q_index >= self.total_q:
                self._finish()
                return

            self.answered    = {}
            self.q_start_ts  = time.time()
            self.status      = GameStatus.QUESTION
            q = self.questions[self.q_index]

        self.replay.record_question(
            self.q_index, q["id"], q["question"]
        )
        self._on_question(self)
        self._timer = threading.Timer(TIME_PER_QUESTION, self.handle_timeout)
        self._timer.daemon = True
        self._timer.start()

    def _finish(self):
        """Determine winner and trigger game-over callback. Must hold _lock."""
        self.status = GameStatus.GAME_OVER

        scores = dict(self.scores)
        sorted_players = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if sorted_players[0][1] == sorted_players[-1][1]:
            winner = None   # Draw
            loser  = None
        else:
            winner = sorted_players[0][0]
            loser  = sorted_players[-1][0]

        self.replay.record_game_over(winner, scores, "all_questions_done")
        self.replay.save()
        logger.log_game_over(self.room_id, winner, scores)

        # Release lock before callback
        self._winner = winner
        self._loser  = loser
        threading.Thread(
            target=self._on_game_over, args=(self,), daemon=True
        ).start()

    def _schedule(self, delay: float, fn: Callable):
        t = threading.Timer(delay, fn)
        t.daemon = True
        t.start()
        self._timer = t

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
