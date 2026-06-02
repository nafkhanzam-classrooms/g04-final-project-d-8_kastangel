"""
tests/test_game_state.py - Tests for the GameState machine.
"""

import sys
import os
import time
import threading
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.game_state import GameState, GameStatus


SAMPLE_QUESTIONS = [
    {"id": 1, "question": "Q1?", "choices": {"A": "1", "B": "2", "C": "3", "D": "4"},
     "answer": "A", "points": 100, "category": "Test"},
    {"id": 2, "question": "Q2?", "choices": {"A": "1", "B": "2", "C": "3", "D": "4"},
     "answer": "B", "points": 100, "category": "Test"},
]

PLAYERS = ["alice", "bob"]


class TestGameState:
    def _make_state(self):
        events = {"questions": [], "answers": [], "states": [], "game_over": []}

        def on_q(s):     events["questions"].append(s.q_index)
        def on_ans(s, u, c, p): events["answers"].append((u, c, p))
        def on_gs(s):    events["states"].append(dict(s.scores))
        def on_go(s):    events["game_over"].append(getattr(s, "_winner", None))

        gs = GameState(
            room_id="TEST",
            players=PLAYERS,
            questions=SAMPLE_QUESTIONS,
            on_question=on_q,
            on_answer_result=on_ans,
            on_game_state=on_gs,
            on_game_over=on_go,
        )
        return gs, events

    def test_initial_status(self):
        gs, _ = self._make_state()
        assert gs.status == GameStatus.WAITING

    def test_start_changes_status(self):
        gs, events = self._make_state()
        gs.start()
        time.sleep(0.5)  # Wait for countdown + first question
        assert gs.status in (GameStatus.QUESTION, GameStatus.COUNTDOWN)

    def test_correct_answer_adds_points(self):
        gs, events = self._make_state()
        gs.start()
        time.sleep(2.5)  # Wait for first question to arrive
        gs.submit_answer("alice", 0, "A")  # correct
        time.sleep(0.2)
        assert gs.scores["alice"] == 100

    def test_wrong_answer_no_points(self):
        gs, events = self._make_state()
        gs.start()
        time.sleep(2.5)
        gs.submit_answer("alice", 0, "C")  # wrong
        time.sleep(0.2)
        assert gs.scores["alice"] == 0

    def test_duplicate_answer_rejected(self):
        gs, events = self._make_state()
        gs.start()
        time.sleep(2.5)
        gs.submit_answer("alice", 0, "A")
        result = gs.submit_answer("alice", 0, "A")  # duplicate
        assert result is False

    def test_wrong_question_index_rejected(self):
        gs, events = self._make_state()
        gs.start()
        time.sleep(2.5)
        result = gs.submit_answer("alice", 99, "A")  # wrong index
        assert result is False

    def test_game_over_after_all_questions(self):
        gs, events = self._make_state()
        gs.start()
        # Answer all questions quickly
        time.sleep(2.5)
        gs.submit_answer("alice", 0, "A")
        gs.submit_answer("bob",   0, "C")
        time.sleep(3.5)   # review + next question
        gs.submit_answer("alice", 1, "B")
        gs.submit_answer("bob",   1, "B")
        time.sleep(3.5)   # review + game over
        assert gs.status == GameStatus.GAME_OVER

    def test_winner_has_higher_score(self):
        gs, events = self._make_state()
        gs.start()
        time.sleep(2.5)
        gs.submit_answer("alice", 0, "A")   # correct: alice +100
        gs.submit_answer("bob",   0, "D")   # wrong
        time.sleep(3.5)
        gs.submit_answer("alice", 1, "B")   # correct: alice +100
        gs.submit_answer("bob",   1, "D")   # wrong
        time.sleep(4)
        assert gs.status == GameStatus.GAME_OVER
        assert gs._winner == "alice"

    def test_snapshot_structure(self):
        gs, _ = self._make_state()
        snap = gs.snapshot()
        required_keys = {"room_id", "status", "players", "scores",
                         "question_index", "total_questions",
                         "time_remaining", "players_answered"}
        assert required_keys.issubset(snap.keys())
