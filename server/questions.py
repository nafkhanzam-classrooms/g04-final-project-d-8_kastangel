"""
questions.py - Question bank loader for CodeDuel.
"""

import json
import os
import random
from typing import Optional

QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "questions.json")

_questions: list[dict] = []


def load_questions(path: str = QUESTIONS_FILE) -> list[dict]:
    """Load questions from JSON file."""
    global _questions
    with open(path, "r", encoding="utf-8") as f:
        _questions = json.load(f)
    return _questions


def get_questions(n: int = 10, category: Optional[str] = None,
                  shuffle: bool = True) -> list[dict]:
    """
    Return n questions, optionally filtered by category.
    Questions are shuffled by default.
    """
    if not _questions:
        load_questions()

    pool = _questions
    if category:
        pool = [q for q in pool if q.get("category") == category]

    if shuffle:
        pool = random.sample(pool, min(n, len(pool)))
    else:
        pool = pool[:n]

    # Return sanitized copies (strip answer for transmission to clients)
    return pool


def get_client_question(q: dict) -> dict:
    """Strip the answer from a question before sending to clients."""
    return {k: v for k, v in q.items() if k != "answer"}
