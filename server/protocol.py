"""
protocol.py - Packet definitions, validation, and serialization for Duels.

All packets are newline-delimited JSON objects transmitted over TCP.
"""

import json
import time
from typing import Optional, Any


# ---------------------------------------------------------------------------
# Packet type constants
# ---------------------------------------------------------------------------

class PacketType:
    # Auth
    LOGIN           = "LOGIN"
    LOGIN_OK        = "LOGIN_OK"
    LOGIN_FAIL      = "LOGIN_FAIL"

    # Matchmaking
    MATCHMAKE       = "MATCHMAKE"
    CANCEL_MATCHMAKE = "CANCEL_MATCHMAKE"
    MATCHED         = "MATCHED"

    # Room
    JOIN_ROOM       = "JOIN_ROOM"
    ROOM_JOINED     = "ROOM_JOINED"
    ROOM_FULL       = "ROOM_FULL"
    ROOM_NOT_FOUND  = "ROOM_NOT_FOUND"

    # Spectate
    SPECTATE        = "SPECTATE"
    SPECTATE_OK     = "SPECTATE_OK"
    SPECTATE_FAIL   = "SPECTATE_FAIL"

    # Game flow
    START_GAME      = "START_GAME"
    QUESTION        = "QUESTION"
    SUBMIT_ANSWER   = "SUBMIT_ANSWER"
    ANSWER_RESULT   = "ANSWER_RESULT"
    GAME_STATE      = "GAME_STATE"
    GAME_OVER       = "GAME_OVER"

    # Connectivity
    PING            = "PING"
    PONG            = "PONG"
    RECONNECT       = "RECONNECT"
    RECONNECT_OK    = "RECONNECT_OK"
    RECONNECT_FAIL  = "RECONNECT_FAIL"
    DISCONNECT      = "DISCONNECT"

    # Data retrieval
    GET_RANKING     = "GET_RANKING"
    RANKING         = "RANKING"
    GET_REPLAY      = "GET_REPLAY"
    REPLAY          = "REPLAY"
    LIST_ROOMS      = "LIST_ROOMS"
    ROOMS_LIST      = "ROOMS_LIST"

    # Errors
    ERROR           = "ERROR"
    INVALID_PACKET  = "INVALID_PACKET"

    # Voice chat (WebRTC signaling relay)
    VOICE_SIGNAL    = "VOICE_SIGNAL"


# ---------------------------------------------------------------------------
# Required fields per packet type (anti-invalid-packet validation)
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: dict[str, list[str]] = {
    PacketType.LOGIN:             ["username"],
    PacketType.MATCHMAKE:         ["username"],
    PacketType.CANCEL_MATCHMAKE:  ["username"],
    PacketType.JOIN_ROOM:         ["username", "room_id"],
    PacketType.SPECTATE:          ["username", "room_id"],
    PacketType.SUBMIT_ANSWER:     ["username", "room_id", "question_index", "answer"],
    PacketType.PING:              ["username"],
    PacketType.PONG:              ["username", "timestamp"],
    PacketType.RECONNECT:         ["username", "room_id"],
    PacketType.GET_RANKING:       [],
    PacketType.GET_REPLAY:        ["room_id"],
    PacketType.LIST_ROOMS:        [],
    PacketType.DISCONNECT:        ["username"],
    PacketType.VOICE_SIGNAL:      ["username", "room_id", "signal_type", "data"],
}


# ---------------------------------------------------------------------------
# Packet builder helpers
# ---------------------------------------------------------------------------

def _make(ptype: str, **kwargs) -> dict:
    pkt = {"type": ptype, "ts": time.time()}
    pkt.update(kwargs)
    return pkt


def make_login_ok(username: str, session_token: str) -> dict:
    return _make(PacketType.LOGIN_OK, username=username, session_token=session_token)


def make_login_fail(reason: str) -> dict:
    return _make(PacketType.LOGIN_FAIL, reason=reason)


def make_matched(room_id: str, opponent: str) -> dict:
    return _make(PacketType.MATCHED, room_id=room_id, opponent=opponent)


def make_room_joined(room_id: str, players: list, spectators: int = 0) -> dict:
    return _make(PacketType.ROOM_JOINED, room_id=room_id, players=players,
                 spectators=spectators)


def make_start_game(room_id: str, players: list, total_questions: int) -> dict:
    return _make(PacketType.START_GAME, room_id=room_id, players=players,
                 total_questions=total_questions)


def make_question(room_id: str, index: int, total: int, question: dict,
                  time_limit: int) -> dict:
    return _make(PacketType.QUESTION, room_id=room_id, index=index, total=total,
                 question=question, time_limit=time_limit)


def make_answer_result(room_id: str, username: str, correct: bool,
                       points: int, scores: dict, hp: dict) -> dict:
    return _make(PacketType.ANSWER_RESULT, room_id=room_id, username=username,
                 correct=correct, points=points, scores=scores, hp=hp)


def make_game_state(room_id: str, scores: dict, hp: dict, question_index: int,
                    status: str, players_answered: list, latencies: dict = None) -> dict:
    return _make(PacketType.GAME_STATE, room_id=room_id, scores=scores, hp=hp,
                 question_index=question_index, status=status,
                 players_answered=players_answered, latencies=latencies or {})


def make_game_over(room_id: str, winner: Optional[str], scores: dict, hp: dict,
                   reason: str = "all_questions_done") -> dict:
    return _make(PacketType.GAME_OVER, room_id=room_id, winner=winner,
                 scores=scores, hp=hp, reason=reason)


def make_pong(username: str, client_timestamp: float) -> dict:
    return _make(PacketType.PONG, username=username, timestamp=client_timestamp)


def make_reconnect_ok(room_id: str, game_state: dict) -> dict:
    return _make(PacketType.RECONNECT_OK, room_id=room_id, game_state=game_state)


def make_reconnect_fail(reason: str) -> dict:
    return _make(PacketType.RECONNECT_FAIL, reason=reason)


def make_ranking(entries: list) -> dict:
    return _make(PacketType.RANKING, entries=entries)


def make_replay(room_id: str, events: list) -> dict:
    return _make(PacketType.REPLAY, room_id=room_id, events=events)


def make_rooms_list(rooms: list) -> dict:
    return _make(PacketType.ROOMS_LIST, rooms=rooms)


def make_error(message: str) -> dict:
    return _make(PacketType.ERROR, message=message)


def make_invalid_packet(reason: str) -> dict:
    return _make(PacketType.INVALID_PACKET, reason=reason)


def make_spectate_ok(room_id: str, game_state: dict) -> dict:
    return _make(PacketType.SPECTATE_OK, room_id=room_id, game_state=game_state)


def make_spectate_fail(reason: str) -> dict:
    return _make(PacketType.SPECTATE_FAIL, reason=reason)


def make_voice_signal(from_user: str, signal_type: str, data) -> dict:
    return _make(PacketType.VOICE_SIGNAL,
                 from_user=from_user, signal_type=signal_type, data=data)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def encode(packet: dict) -> bytes:
    """Serialize a packet dict to a newline-terminated JSON byte string."""
    return (json.dumps(packet, ensure_ascii=False) + "\n").encode("utf-8")


def decode(raw: str) -> dict:
    """Deserialize a JSON string into a packet dict."""
    return json.loads(raw.strip())


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(packet: dict) -> tuple[bool, str]:
    """
    Validate an incoming packet.

    Returns:
        (True, "") if valid
        (False, reason) if invalid
    """
    if not isinstance(packet, dict):
        return False, "Packet must be a JSON object"

    ptype = packet.get("type")
    if not ptype or not isinstance(ptype, str):
        return False, "Missing or invalid 'type' field"

    required = REQUIRED_FIELDS.get(ptype)
    if required is None:
        # Unknown packet type from client
        return False, f"Unknown packet type: {ptype}"

    for field in required:
        if field not in packet:
            return False, f"Missing required field '{field}' for type '{ptype}'"
        if packet[field] is None or packet[field] == "":
            return False, f"Field '{field}' must not be empty"

    # Extra type checks
    if ptype == PacketType.SUBMIT_ANSWER:
        if not isinstance(packet.get("question_index"), int):
            return False, "'question_index' must be an integer"
        if not isinstance(packet.get("answer"), str):
            return False, "'answer' must be a string"

    return True, ""
