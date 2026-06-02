"""
logger.py - Activity logger for CodeDuel server.

Logs all significant events to a rotating log file and to stdout.
"""

import logging
import logging.handlers
import os
import time
from datetime import datetime


LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "codeduel.log")


def _setup_logger(name: str = "codeduel") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler (10 MB, keep 5 backups)
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    return logger


_logger = _setup_logger()


# ---------------------------------------------------------------------------
# Public logging helpers
# ---------------------------------------------------------------------------

def log_login(username: str, addr: str):
    _logger.info(f"LOGIN      | user={username!r:20s} addr={addr}")


def log_logout(username: str, reason: str = ""):
    _logger.info(f"LOGOUT     | user={username!r:20s} reason={reason!r}")


def log_matchmake(username: str):
    _logger.info(f"MATCHMAKE  | user={username!r:20s} entered queue")


def log_matched(room_id: str, p1: str, p2: str):
    _logger.info(f"MATCHED    | room={room_id}  {p1!r} vs {p2!r}")


def log_join_room(username: str, room_id: str):
    _logger.info(f"JOIN_ROOM  | user={username!r:20s} room={room_id}")


def log_spectate(username: str, room_id: str):
    _logger.info(f"SPECTATE   | user={username!r:20s} room={room_id}")


def log_start_game(room_id: str, players: list):
    _logger.info(f"START_GAME | room={room_id}  players={players}")


def log_answer(username: str, room_id: str, q_idx: int, correct: bool, points: int):
    result = "CORRECT" if correct else "WRONG  "
    _logger.info(
        f"ANSWER     | user={username!r:20s} room={room_id}  "
        f"q={q_idx}  {result}  pts={points:+d}"
    )


def log_game_over(room_id: str, winner: str | None, scores: dict):
    _logger.info(f"GAME_OVER  | room={room_id}  winner={winner!r}  scores={scores}")


def log_disconnect(username: str, addr: str):
    _logger.info(f"DISCONNECT | user={username!r:20s} addr={addr}")


def log_reconnect(username: str, room_id: str, success: bool):
    s = "OK" if success else "FAIL"
    _logger.info(f"RECONNECT  | user={username!r:20s} room={room_id}  result={s}")


def log_invalid_packet(addr: str, reason: str, raw: str):
    snippet = raw[:120].replace("\n", "\\n")
    _logger.warning(
        f"INVALID_PKT| addr={addr}  reason={reason!r}  raw={snippet!r}"
    )


def log_ping(username: str, latency_ms: float):
    _logger.debug(f"PING       | user={username!r:20s} latency={latency_ms:.1f}ms")


def log_error(context: str, exc: Exception):
    _logger.error(f"ERROR      | {context}: {exc}", exc_info=True)


def log_info(msg: str):
    _logger.info(msg)


def log_debug(msg: str):
    _logger.debug(msg)
