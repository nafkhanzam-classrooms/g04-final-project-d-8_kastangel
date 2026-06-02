"""
tests/test_matchmaking.py - Tests for the matchmaking queue.
"""

import sys
import os
import time
import threading
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.matchmaking import MatchmakingQueue


class MockHandler:
    """Stub for ClientHandler used in tests."""
    def __init__(self, username: str):
        self.username = username
        self.room = None
        self.packets: list = []

    def send(self, pkt):
        self.packets.append(pkt)


class TestMatchmakingQueue:
    def test_enqueue_dequeue(self):
        q = MatchmakingQueue()
        h = MockHandler("alice")
        q.enqueue("alice", h)
        assert q.queue_length() == 1
        q.dequeue("alice")
        assert q.queue_length() == 0

    def test_no_duplicate_enqueue(self):
        q = MatchmakingQueue()
        h = MockHandler("alice")
        q.enqueue("alice", h)
        q.enqueue("alice", h)   # duplicate
        assert q.queue_length() == 1

    def test_match_two_players(self):
        q = MatchmakingQueue()
        h1 = MockHandler("alice")
        h2 = MockHandler("bob")
        q.enqueue("alice", h1)
        q.enqueue("bob", h2)

        # Wait for the background matcher to run
        time.sleep(0.5)

        # Both should have been matched (sent MATCHED packet)
        matched_types = [p.get("type") for p in h1.packets]
        assert "MATCHED" in matched_types or "ROOM_JOINED" in matched_types

    def test_single_player_not_matched(self):
        q = MatchmakingQueue()
        h1 = MockHandler("solo")
        q.enqueue("solo", h1)
        time.sleep(0.3)
        # No MATCHED packet should have been sent
        matched_types = [p.get("type") for p in h1.packets]
        assert "MATCHED" not in matched_types
