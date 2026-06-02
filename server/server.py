"""
server.py - Entry point for the CodeDuel game server.

Usage:
    python -m server.server [--host HOST] [--port PORT]
"""

import argparse
import sys
import os

# Ensure the project root is on the path when running as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.game_server import GameServer
from server.questions import load_questions
from server import logger


def main():
    parser = argparse.ArgumentParser(description="CodeDuel Game Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9000, help="Port (default: 9000)")
    args = parser.parse_args()

    # Pre-load questions
    try:
        qs = load_questions()
        logger.log_info(f"Loaded {len(qs)} questions from bank.")
    except Exception as e:
        logger.log_error("Failed to load questions", e)
        sys.exit(1)

    server = GameServer(host=args.host, port=args.port)
    server.start()


if __name__ == "__main__":
    main()
