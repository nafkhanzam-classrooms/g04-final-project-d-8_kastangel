"""
game_state.py - Game state machine for a single Duels match.
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


TIME_PER_QUESTION  = 20   # seconds
REVIEW_DURATION    = 3    # seconds between questions
POINTS_PER_CORRECT = 100  # base; actual from question data

# HP system
HP_START           = 100
HP_WRONG_PENALTY   = 10
HP_TIMEOUT_PENALTY = 15


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

        self.scores           = {p: 0 for p in players}
        self.hp               = {p: HP_START for p in players}  # HP system
        self.status           = GameStatus.WAITING
        self.q_index          = -1              # Current question index
        self.answered         = {}              # {username: answer} — all submissions this question
        self.wrong_attempts   = set()           # players who answered wrong (may retry)
        self.correct_answerer: Optional[str] = None  # locks the question when set
        self.q_start_ts       = 0.0

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
        Process a player's answer (cerdas cermat style).

        - A player may answer multiple times until they get it right.
        - Once any player answers correctly, the question is locked:
          no further answers are accepted and the next question starts
          after a short review pause.
        - Wrong answers deduct HP.
        - Returns False if the submission is rejected.
        """
        with self._lock:
            if self.status != GameStatus.QUESTION:
                return False
            if q_index != self.q_index:
                return False
            if username not in self.players:
                return False
            # Reject if someone already answered correctly
            if self.correct_answerer is not None:
                return False

            q       = self.questions[self.q_index]
            correct = answer.upper() == q["answer"].upper()
            points  = q.get("points", POINTS_PER_CORRECT) if correct else 0

            if correct:
                self.scores[username] += points
                self.correct_answerer = username
            else:
                self.wrong_attempts.add(username)
                # Deduct HP on wrong answer
                self.hp[username] = max(0, self.hp[username] - HP_WRONG_PENALTY)

            self.answered[username] = answer  # record latest answer

            self.replay.record_answer(
                username, q_index, answer, correct, points, dict(self.scores),
                q["answer"].upper()
            )

            should_advance = correct
            # Also check HP death
            hp_dead = self.hp[username] <= 0 and not correct

        logger.log_answer(username, self.room_id, q_index, correct, points)
        self._on_answer_result(self, username, correct, points)
        self._on_game_state(self)

        if should_advance:
            with self._lock:
                self._cancel_timer()
            self._schedule(REVIEW_DURATION, self._next_question)
        elif hp_dead:
            # Player's HP is 0 — they lose immediately
            with self._lock:
                self._cancel_timer()
            self._schedule(REVIEW_DURATION, self._finish_hp_death)

        return True

    def handle_timeout(self):
        """Called when the question timer expires."""
        with self._lock:
            if self.status != GameStatus.QUESTION:
                return
            # Deduct HP from players who did NOT answer correctly
            for player in self.players:
                if player != self.correct_answerer and player not in [u for u, a in self.answered.items() if self.questions[self.q_index]["answer"].upper() == a.upper()]:
                    self.hp[player] = max(0, self.hp[player] - HP_TIMEOUT_PENALTY)
            self.replay.record_timeout(self.q_index)

        self._on_game_state(self)
        self._schedule(REVIEW_DURATION, self._next_question)

    def snapshot(self) -> dict:
        """Return a JSON-safe snapshot of the current game state."""
        with self._lock:
            q = self.questions[self.q_index] if 0 <= self.q_index < self.total_q else None
            elapsed = time.time() - self.q_start_ts if self.q_start_ts else 0
            remaining = max(0, TIME_PER_QUESTION - elapsed) if q else 0
            return {
                "room_id":          self.room_id,
                "status":           self.status.name,
                "players":          self.players,
                "scores":           dict(self.scores),
                "hp":               dict(self.hp),
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

            # Check if any player has 0 HP
            for player in self.players:
                if self.hp[player] <= 0:
                    self._finish()
                    return

            self.answered         = {}
            self.wrong_attempts   = set()
            self.correct_answerer = None
            self.q_start_ts       = time.time()
            self.status           = GameStatus.QUESTION
            q = self.questions[self.q_index]

        self.replay.record_question(
            self.q_index, q["id"], q["question"]
        )
        self._on_question(self)
        self._timer = threading.Timer(TIME_PER_QUESTION, self.handle_timeout)
        self._timer.daemon = True
        self._timer.start()

    def _finish_hp_death(self):
        """Triggered when a player's HP drops to 0 mid-question."""
        self._finish()

    def _finish(self):
        """Determine winner and trigger game-over callback. Must hold _lock or be called thread-safely."""
        # Check if already finished
        if self.status == GameStatus.GAME_OVER:
            return

        self.status = GameStatus.GAME_OVER

        scores = dict(self.scores)
        hp     = dict(self.hp)

        # Determine winner: first check HP (someone at 0 loses)
        # then fall back to score
        dead_players = [p for p in self.players if hp[p] <= 0]
        alive_players = [p for p in self.players if hp[p] > 0]

        if len(alive_players) == 1:
            winner = alive_players[0]
            loser  = dead_players[0] if dead_players else None
            reason = "hp_depleted"
        elif len(alive_players) == 0:
            # Both dead at same time — score decides
            winner = None
            loser  = None
            reason = "all_questions_done"
        else:
            # Normal finish by score
            sorted_players = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            if sorted_players[0][1] == sorted_players[-1][1]:
                winner = None
                loser  = None
            else:
                winner = sorted_players[0][0]
                loser  = sorted_players[-1][0]
            reason = "all_questions_done"

        self.replay.record_game_over(winner, scores, reason)
        self.replay.save()
        logger.log_game_over(self.room_id, winner, scores)

        self._winner = winner
        self._loser  = loser
        self._reason = reason
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
