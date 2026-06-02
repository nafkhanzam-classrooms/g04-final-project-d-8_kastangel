"""
tests/test_protocol.py - Unit tests for the CodeDuel protocol module.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.protocol import (
    validate, encode, decode, make_login_ok, make_question,
    make_game_over, PacketType
)


class TestValidate:
    def test_valid_login(self):
        ok, reason = validate({"type": "LOGIN", "username": "alice"})
        assert ok is True

    def test_login_missing_username(self):
        ok, reason = validate({"type": "LOGIN"})
        assert ok is False
        assert "username" in reason

    def test_login_empty_username(self):
        ok, reason = validate({"type": "LOGIN", "username": ""})
        assert ok is False

    def test_unknown_type(self):
        ok, reason = validate({"type": "HACK", "username": "x"})
        assert ok is False
        assert "Unknown" in reason

    def test_no_type(self):
        ok, reason = validate({"username": "alice"})
        assert ok is False

    def test_not_a_dict(self):
        ok, reason = validate("not a dict")
        assert ok is False

    def test_valid_submit_answer(self):
        ok, _ = validate({
            "type": "SUBMIT_ANSWER",
            "username": "alice",
            "room_id": "ABC123",
            "question_index": 0,
            "answer": "B",
        })
        assert ok is True

    def test_submit_answer_wrong_index_type(self):
        ok, reason = validate({
            "type": "SUBMIT_ANSWER",
            "username": "alice",
            "room_id": "ABC123",
            "question_index": "0",   # string instead of int
            "answer": "B",
        })
        assert ok is False

    def test_valid_ping(self):
        ok, _ = validate({"type": "PING", "username": "bob"})
        assert ok is True

    def test_valid_reconnect(self):
        ok, _ = validate({"type": "RECONNECT", "username": "alice", "room_id": "X"})
        assert ok is True


class TestEncodeDecode:
    def test_roundtrip(self):
        pkt = {"type": "LOGIN_OK", "username": "alice", "ts": 1234.5}
        raw = encode(pkt)
        assert raw.endswith(b"\n")
        decoded = decode(raw.decode("utf-8"))
        assert decoded == pkt

    def test_unicode(self):
        pkt = {"type": "ERROR", "message": "Kesalahan – soal tidak ditemukan"}
        raw = encode(pkt)
        decoded = decode(raw.decode("utf-8"))
        assert decoded["message"] == pkt["message"]


class TestPacketBuilders:
    def test_make_login_ok(self):
        pkt = make_login_ok("alice", "token123")
        assert pkt["type"] == PacketType.LOGIN_OK
        assert pkt["username"] == "alice"

    def test_make_question(self):
        q = {"id": 1, "question": "Q?", "choices": {"A": "x"}}
        pkt = make_question("ROOM1", 0, 5, q, 20)
        assert pkt["type"] == PacketType.QUESTION
        assert pkt["room_id"] == "ROOM1"
        assert pkt["time_limit"] == 20

    def test_make_game_over_draw(self):
        pkt = make_game_over("R1", None, {"a": 100, "b": 100})
        assert pkt["winner"] is None

    def test_make_game_over_winner(self):
        pkt = make_game_over("R1", "alice", {"alice": 300, "bob": 100})
        assert pkt["winner"] == "alice"
