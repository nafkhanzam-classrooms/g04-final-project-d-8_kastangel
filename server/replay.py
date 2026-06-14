"""
replay.py - Match replay recorder and storage for CodeDuel.

Each game's events are stored as a JSON file in data/replays/.
"""

import json
import os
import time
from typing import Any

REPLAYS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "replays")
os.makedirs(REPLAYS_DIR, exist_ok=True)


class ReplayRecorder:
    """Records all events during a match for later playback."""

    def __init__(self, room_id: str, players: list[str]):
        self.room_id = room_id
        self.players = players
        self.events: list[dict] = []
        self.started_at = time.time()
        self._record("GAME_START", players=players)

    def _record(self, event_type: str, **kwargs):
        self.events.append({
            "event": event_type,
            "ts": time.time(),
            "elapsed": round(time.time() - self.started_at, 3),
            **kwargs,
        })

    def record_question(self, index: int, question_id: int, question_text: str):
        self._record("QUESTION", index=index, question_id=question_id,
                     question_text=question_text)

    def record_answer(self, username: str, question_index: int, answer: str,
                      correct: bool, points: int, scores: dict, correct_answer: str):
        self._record("ANSWER", username=username, question_index=question_index,
                     answer=answer, correct=correct, points=points, scores=scores,
                     correct_answer=correct_answer)

    def record_timeout(self, question_index: int):
        self._record("TIMEOUT", question_index=question_index)

    def record_disconnect(self, username: str):
        self._record("DISCONNECT", username=username)

    def record_reconnect(self, username: str):
        self._record("RECONNECT", username=username)

    def record_game_over(self, winner: str | None, scores: dict, reason: str):
        self._record("GAME_OVER", winner=winner, scores=scores, reason=reason)

    def save(self):
        """Persist the replay to a JSON file."""
        filename = f"{self.room_id}.json"
        path = os.path.join(REPLAYS_DIR, filename)
        data = {
            "room_id": self.room_id,
            "players": self.players,
            "started_at": self.started_at,
            "events": self.events,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path


def load_replay(room_id: str) -> dict | None:
    """Load a replay by room_id. Returns None if not found."""
    path = os.path.join(REPLAYS_DIR, f"{room_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_replays() -> list[str]:
    """Return a list of available replay room IDs."""
    files = os.listdir(REPLAYS_DIR)
    return [f.removesuffix(".json") for f in files if f.endswith(".json")]
