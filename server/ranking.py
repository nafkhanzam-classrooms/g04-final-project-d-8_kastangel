"""
ranking.py - Ranking / leaderboard system for CodeDuel.

Rankings are persisted in data/ranking.json.
"""

import json
import os
import threading
from typing import Optional

RANKING_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "ranking.json")

_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(RANKING_FILE):
        return {}
    with open(RANKING_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(RANKING_FILE), exist_ok=True)
    with open(RANKING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _default_entry(username: str) -> dict:
    return {
        "username": username,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "total_games": 0,
        "total_score": 0,
        "elo": 1000,
    }


def _elo_update(winner_elo: int, loser_elo: int, k: int = 32) -> tuple[int, int]:
    """Return (new_winner_elo, new_loser_elo)."""
    expected_w = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_l = 1 - expected_w
    new_w = round(winner_elo + k * (1 - expected_w))
    new_l = round(loser_elo + k * (0 - expected_l))
    return new_w, new_l


def record_result(winner: Optional[str], loser: Optional[str],
                  scores: dict):
    """
    Record a match result. Pass winner=None for a draw.
    scores = {username: total_points}
    """
    with _lock:
        data = _load()

        players = list(scores.keys())
        for p in players:
            if p not in data:
                data[p] = _default_entry(p)
            data[p]["total_games"] += 1
            data[p]["total_score"] += scores.get(p, 0)

        if winner and loser:
            data[winner]["wins"] += 1
            data[loser]["losses"] += 1
            # ELO update
            w_elo, l_elo = _elo_update(
                data[winner]["elo"], data[loser]["elo"]
            )
            data[winner]["elo"] = w_elo
            data[loser]["elo"] = l_elo
        else:
            # Draw
            for p in players:
                data[p]["draws"] += 1

        _save(data)


def get_ranking(limit: int = 20, sort_by: str = "elo") -> list[dict]:
    """
    Return top-N players sorted by the given key.
    sort_by: 'elo' | 'wins' | 'total_score'
    """
    with _lock:
        data = _load()

    entries = list(data.values())
    entries.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    for i, entry in enumerate(entries[:limit]):
        entry["rank"] = i + 1
    return entries[:limit]


def get_player_rank(username: str) -> Optional[dict]:
    """Get a specific player's ranking entry."""
    with _lock:
        data = _load()
    return data.get(username)


def ensure_player(username: str):
    """Create a ranking entry for a player if one doesn't exist."""
    with _lock:
        data = _load()
        if username not in data:
            data[username] = _default_entry(username)
            _save(data)
