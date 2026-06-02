"""
ui.py - Terminal UI for CodeDuel client.

Uses only Python stdlib (no curses) so it works on any terminal.
Provides a clean interactive menu-driven interface.
"""

import sys
import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .client import GameClient

# ANSI color codes
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_BLUE = "\033[44m"
    BG_RED  = "\033[41m"
    BG_GREEN= "\033[42m"
    BG_DIM  = "\033[100m"


def _hr(char="─", width=60, color=C.DIM):
    return f"{color}{char * width}{C.RESET}"


def _banner(text: str, color=C.CYAN):
    w = 60
    pad = (w - len(text) - 2) // 2
    line = f"{'█'*pad} {text} {'█'*pad}"
    return f"{color}{C.BOLD}{line[:w]}{C.RESET}"


def _input(prompt: str) -> str:
    try:
        return input(f"{C.CYAN}▶ {C.RESET}{prompt}").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _print_menu(title: str, options: list[tuple[str, str]]):
    print(f"\n{_banner(title)}")
    print(_hr())
    for key, desc in options:
        print(f"  {C.YELLOW}{C.BOLD}[{key}]{C.RESET}  {desc}")
    print(_hr())


class CodeDuelUI:
    """
    Drives the client terminal UI.

    The UI is event-driven: server packets trigger callbacks which update
    internal state and print to stdout. Input is gathered synchronously.
    """

    def __init__(self, client: "GameClient"):
        self.client      = client
        self._state      = "MENU"     # MENU, WAITING, IN_GAME, SPECTATING, DONE
        self._event      = threading.Event()
        self._lock       = threading.Lock()
        self._latency    = 0.0
        self._scores: dict[str, int] = {}
        self._current_q: Optional[dict] = None
        self._q_index    = 0
        self._q_total    = 0
        self._answered   = False
        self._time_limit = 20
        self._q_received_at = 0.0
        self._room_id    = ""
        self._players: list[str] = []
        self._timer_thread: Optional[threading.Thread] = None
        self._timer_stop  = threading.Event()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        self._do_login()
        # _main_menu() blocks the main thread here.
        # The receive loop runs in a daemon thread independently.
        self._main_menu()

    def _do_login(self):
        print(f"\n{C.BOLD}{C.WHITE}Welcome to CodeDuel!{C.RESET}")
        while True:
            username = _input("Enter your username (1–20 chars): ")
            if 1 <= len(username) <= 20:
                self.client.login(username)
                self._event.wait(timeout=10)
                self._event.clear()
                if self._state == "LOGGED_IN":
                    break
                # LOGIN_FAIL already printed
            else:
                print(f"{C.RED}Username must be 1–20 characters.{C.RESET}")

    def _main_menu(self):
        while self._state not in ("DISCONNECTED",):
            _print_menu("MAIN MENU", [
                ("1", "Matchmaking  — Auto-match with another player"),
                ("2", "Join Room   — Enter a specific Room ID"),
                ("3", "Spectate    — Watch an ongoing match"),
                ("4", "Ranking     — View leaderboard"),
                ("5", "Replay      — Watch a past match"),
                ("6", "List Rooms  — Show active rooms"),
                ("7", "Reconnect   — Rejoin a disconnected game"),
                ("Q", "Quit"),
            ])
            print(f"  {C.DIM}Latency: {self._latency:.0f}ms{C.RESET}")
            choice = _input("Choice: ").upper()

            if choice == "1":
                self._do_matchmake()
            elif choice == "2":
                self._do_join_room()
            elif choice == "3":
                self._do_spectate()
            elif choice == "4":
                self._do_ranking()
            elif choice == "5":
                self._do_replay()
            elif choice == "6":
                self._do_list_rooms()
            elif choice == "7":
                self._do_reconnect()
            elif choice == "Q":
                self.client.disconnect()
                print(f"\n{C.YELLOW}Goodbye! 👋{C.RESET}\n")
                sys.exit(0)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _do_matchmake(self):
        print(f"\n{C.CYAN}Entering matchmaking queue...{C.RESET}")
        print(f"{C.DIM}Waiting for opponent. Press Ctrl+C to cancel.{C.RESET}")
        self._state = "WAITING"
        self.client.matchmake()
        try:
            self._event.wait()  # Set by on_start_game
            self._event.clear()
        except KeyboardInterrupt:
            self._state = "LOGGED_IN"
            self._event.clear()
            return
        # Game started — run input loop in main thread
        if self._state == "IN_GAME":
            self._do_game_input()

    def _do_join_room(self):
        room_id = _input("Room ID: ").upper()
        if not room_id:
            return
        print(f"{C.CYAN}Joining room {room_id}...{C.RESET}")
        self._state = "WAITING"
        self.client.join_room(room_id)
        try:
            self._event.wait(timeout=15)  # Set by on_start_game
            self._event.clear()
        except KeyboardInterrupt:
            self._state = "LOGGED_IN"
            self._event.clear()
            return
        if self._state == "IN_GAME":
            self._do_game_input()

    def _do_spectate(self):
        room_id = _input("Room ID to spectate: ").upper()
        if not room_id:
            return
        self._state = "SPECTATING"
        self.client.spectate(room_id)
        try:
            # Block until game over or user interrupts
            while self._state == "SPECTATING":
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        self._state = "LOGGED_IN"
        self._event.clear()

    def _do_ranking(self):
        print(f"\n{C.CYAN}Fetching ranking...{C.RESET}")
        self.client.get_ranking()
        self._event.wait(timeout=10)
        self._event.clear()

    def _do_replay(self):
        room_id = _input("Room ID for replay: ").upper()
        if not room_id:
            return
        print(f"{C.CYAN}Fetching replay for room {room_id}...{C.RESET}")
        self.client.get_replay(room_id)
        self._event.wait(timeout=10)
        self._event.clear()

    def _do_list_rooms(self):
        print(f"\n{C.CYAN}Fetching active rooms...{C.RESET}")
        self.client.list_rooms()
        self._event.wait(timeout=10)
        self._event.clear()

    def _do_reconnect(self):
        username = _input(f"Username [{self.client.username}]: ") or self.client.username
        room_id  = _input("Room ID: ").upper()
        if not room_id:
            return
        print(f"{C.CYAN}Reconnecting...{C.RESET}")
        self.client.reconnect(username, room_id)
        self._event.wait(timeout=15)
        self._event.clear()

    def _do_game_input(self):
        """
        Blocking input loop for the active match.
        Runs in the main thread so there's no stdin conflict with the menu.
        Returns when the game ends (state leaves IN_GAME).
        """
        while self._state == "IN_GAME":
            if self._current_q and not self._answered:
                self._print_question()
                try:
                    ans = _input("Your answer [A/B/C/D]: ").upper()
                except KeyboardInterrupt:
                    break
                if ans in ("A", "B", "C", "D"):
                    self.client.submit_answer(self._q_index, ans)
                    self._answered = True
                    print(f"{C.DIM}Answer submitted. Waiting for result...{C.RESET}")
                elif ans == "Q":
                    break
                else:
                    print(f"{C.RED}Invalid choice. Use A, B, C, or D.{C.RESET}")
            else:
                # Waiting for next question or game over
                time.sleep(0.2)

    # ------------------------------------------------------------------
    # Print helpers
    # ------------------------------------------------------------------

    def _print_question(self):
        if not self._current_q:
            return
        q = self._current_q
        elapsed = time.time() - self._q_received_at
        remaining = max(0, self._time_limit - elapsed)

        print(f"\n{_hr('═')}")
        print(f"  {C.BOLD}{C.WHITE}Question {self._q_index + 1} / {self._q_total}{C.RESET}"
              f"   {C.YELLOW}⏱  {remaining:.0f}s remaining{C.RESET}"
              f"   {C.DIM}Ping: {self._latency:.0f}ms{C.RESET}")
        print(f"  {C.CYAN}[{q.get('category', '?')}]{C.RESET}  {C.BOLD}{q['question']}{C.RESET}")
        print(_hr())

        choices = q.get("choices", {})
        for key in ("A", "B", "C", "D"):
            val = choices.get(key, "")
            if val:
                print(f"  {C.YELLOW}{C.BOLD}[{key}]{C.RESET}  {val}")

        print(_hr())
        self._print_scores()

    def _print_scores(self):
        if not self._scores:
            return
        parts = []
        for user, pts in self._scores.items():
            marker = f"{C.GREEN}★ {C.RESET}" if user == self.client.username else ""
            parts.append(f"{marker}{C.BOLD}{user}{C.RESET}: {C.CYAN}{pts}{C.RESET} pts")
        print("  " + "   |   ".join(parts))

    def _start_question_timer(self):
        """Print a countdown in a background thread."""
        self._timer_stop.clear()

        def _countdown():
            while not self._timer_stop.is_set():
                elapsed = time.time() - self._q_received_at
                remaining = max(0, self._time_limit - elapsed)
                if remaining <= 0:
                    break
                time.sleep(1)

        self._timer_thread = threading.Thread(target=_countdown, daemon=True)
        self._timer_thread.start()

    # ------------------------------------------------------------------
    # Server packet callbacks
    # ------------------------------------------------------------------

    def on_login_ok(self, pkt: dict):
        username = pkt.get("username", "")
        self.client.username = username
        self._state = "LOGGED_IN"
        print(f"\n{C.GREEN}{C.BOLD}✓ Logged in as {username!r}{C.RESET}")
        # Unblock _do_login() in run(); _main_menu() will be called next by run()
        self._event.set()

    def on_login_fail(self, pkt: dict):
        reason = pkt.get("reason", "Unknown error")
        print(f"\n{C.RED}✗ Login failed: {reason}{C.RESET}")
        self._event.set()

    def on_matched(self, pkt: dict):
        opponent = pkt.get("opponent", "?")
        room_id  = pkt.get("room_id", "")
        self._room_id = room_id
        self.client.room_id = room_id
        print(f"\n{C.GREEN}{C.BOLD}⚔  Matched!{C.RESET} "
              f"Room: {C.CYAN}{room_id}{C.RESET}  vs  {C.MAGENTA}{opponent}{C.RESET}")

    def on_room_joined(self, pkt: dict):
        room_id = pkt.get("room_id", "")
        players = pkt.get("players", [])
        self._room_id = room_id
        self._players = players
        self.client.room_id = room_id
        print(f"\n{C.CYAN}Room {room_id} — waiting for game to start...{C.RESET}")
        print(f"  Players: {', '.join(players)}")

    def on_spectate_ok(self, pkt: dict):
        room_id = pkt.get("room_id", "")
        snap    = pkt.get("game_state", {})
        print(f"\n{C.CYAN}Spectating room {room_id}{C.RESET}")
        self._room_id = room_id
        if snap:
            print(f"  Status: {snap.get('status')}")
            self._scores = snap.get("scores", {})
            self._print_scores()

    def on_spectate_fail(self, pkt: dict):
        reason = pkt.get("reason", "Unknown")
        print(f"\n{C.RED}Cannot spectate: {reason}{C.RESET}")
        self._state = "LOGGED_IN"
        self._event.set()

    def on_start_game(self, pkt: dict):
        players = pkt.get("players", [])
        total   = pkt.get("total_questions", 0)
        self._players  = players
        self._q_total  = total
        self._scores   = {p: 0 for p in players}
        self._state    = "IN_GAME"

        print(f"\n{_hr('═', color=C.GREEN)}")
        print(f"{C.GREEN}{C.BOLD}  🎮 GAME STARTED!{C.RESET}")
        print(f"  Players: {C.MAGENTA}{' vs '.join(players)}{C.RESET}")
        print(f"  Total questions: {C.YELLOW}{total}{C.RESET}")
        print(_hr('═', color=C.GREEN))

        # Signal _do_matchmake/_do_join_room to unblock and run _do_game_input
        self._event.set()

    def on_question(self, pkt: dict):
        self._q_index       = pkt.get("index", 0)
        self._q_total       = pkt.get("total", self._q_total)
        self._current_q     = pkt.get("question", {})
        self._time_limit    = pkt.get("time_limit", 20)
        self._q_received_at = time.time()
        self._answered      = False
        self._state         = "IN_GAME"
        self._timer_stop.set()
        self._start_question_timer()
        # The game input loop will detect the new question and print it

    def on_answer_result(self, pkt: dict):
        username = pkt.get("username", "")
        correct  = pkt.get("correct", False)
        points   = pkt.get("points", 0)
        self._scores = pkt.get("scores", self._scores)

        if username == self.client.username:
            if correct:
                print(f"\n  {C.BG_GREEN}{C.BOLD} ✓ CORRECT! +{points} pts {C.RESET}")
            else:
                print(f"\n  {C.BG_RED}{C.BOLD} ✗ WRONG! {C.RESET}")
        else:
            mark = "✓" if correct else "✗"
            print(f"\n  {C.DIM}{username} answered: {mark} ({'+' if correct else ''}{points}){C.RESET}")

    def on_game_state(self, pkt: dict):
        self._scores = pkt.get("scores", self._scores)

    def on_game_over(self, pkt: dict):
        winner = pkt.get("winner")
        scores = pkt.get("scores", {})
        reason = pkt.get("reason", "")

        print(f"\n{_hr('═', color=C.MAGENTA)}")
        print(f"{C.MAGENTA}{C.BOLD}  🏁 GAME OVER{C.RESET}")
        if winner:
            if winner == self.client.username:
                print(f"  {C.GREEN}{C.BOLD}🏆 YOU WIN!{C.RESET}")
            else:
                print(f"  {C.RED}{C.BOLD}💔 You lost. {winner} wins.{C.RESET}")
        else:
            print(f"  {C.YELLOW}{C.BOLD}🤝 Draw!{C.RESET}")

        print(f"\n  Final Scores:")
        for player, pts in sorted(scores.items(), key=lambda x: -x[1]):
            marker = " ← you" if player == self.client.username else ""
            print(f"    {C.CYAN}{player}{C.RESET}: {C.BOLD}{pts}{C.RESET} pts{C.DIM}{marker}{C.RESET}")
        print(_hr('═', color=C.MAGENTA))
        print(f"\n{C.DIM}Press Enter to return to menu...{C.RESET}")

        # Changing state to LOGGED_IN causes _do_game_input loop to exit
        self._state     = "LOGGED_IN"
        self._current_q = None
        self._room_id   = ""
        self.client.room_id = ""
        self._timer_stop.set()

    def on_reconnect_ok(self, pkt: dict):
        snap = pkt.get("game_state", {})
        print(f"\n{C.GREEN}✓ Reconnected to room {pkt.get('room_id')}!{C.RESET}")
        if snap:
            self._scores  = snap.get("scores", {})
            self._q_index = snap.get("question_index", 0)
            self._state   = "IN_GAME"
        self._event.set()  # Unblock _do_reconnect()

    def on_reconnect_fail(self, pkt: dict):
        reason = pkt.get("reason", "Unknown")
        print(f"\n{C.RED}✗ Reconnect failed: {reason}{C.RESET}")
        self._event.set()

    def on_ranking(self, pkt: dict):
        entries = pkt.get("entries", [])
        print(f"\n{_banner('🏆 LEADERBOARD', C.YELLOW)}")
        print(_hr())
        header = f"{'#':>3}  {'Username':<20}  {'ELO':>5}  {'W':>4}  {'L':>4}  {'Score':>7}"
        print(f"  {C.BOLD}{header}{C.RESET}")
        print(_hr('-'))
        for e in entries:
            rank = e.get('rank', '?')
            user = e.get('username', '?')
            elo  = e.get('elo', 0)
            wins = e.get('wins', 0)
            loss = e.get('losses', 0)
            scr  = e.get('total_score', 0)
            color = C.YELLOW if rank == 1 else (C.WHITE if rank <= 3 else C.DIM)
            row = f"{rank:>3}  {user:<20}  {elo:>5}  {wins:>4}  {loss:>4}  {scr:>7}"
            print(f"  {color}{row}{C.RESET}")
        print(_hr())
        self._event.set()

    def on_replay(self, pkt: dict):
        room_id = pkt.get("room_id", "?")
        events  = pkt.get("events", [])
        print(f"\n{_banner(f'REPLAY: {room_id}', C.BLUE)}")
        print(_hr())
        for ev in events:
            elapsed = ev.get("elapsed", 0)
            etype   = ev.get("event", "?")
            ts_str  = f"[+{elapsed:.1f}s]"

            if etype == "GAME_START":
                players = ev.get("players", [])
                print(f"  {C.DIM}{ts_str}{C.RESET}  {C.GREEN}GAME START{C.RESET}  {' vs '.join(players)}")
            elif etype == "QUESTION":
                idx  = ev.get("index", 0)
                text = ev.get("question_text", "")
                print(f"  {C.DIM}{ts_str}{C.RESET}  {C.CYAN}Q{idx+1}{C.RESET}  {text[:60]}")
            elif etype == "ANSWER":
                user    = ev.get("username", "?")
                answer  = ev.get("answer", "?")
                correct = ev.get("correct", False)
                pts     = ev.get("points", 0)
                mark    = f"{C.GREEN}✓" if correct else f"{C.RED}✗"
                print(f"  {C.DIM}{ts_str}{C.RESET}  {C.BOLD}{user}{C.RESET} → {answer}  {mark}{C.RESET}  {pts:+d}pts")
            elif etype == "TIMEOUT":
                qidx = ev.get("question_index", 0)
                print(f"  {C.DIM}{ts_str}{C.RESET}  {C.YELLOW}TIMEOUT Q{qidx+1}{C.RESET}")
            elif etype == "GAME_OVER":
                winner = ev.get("winner", "Draw")
                scores = ev.get("scores", {})
                scr_str = "  ".join(f"{u}:{p}" for u, p in scores.items())
                print(f"  {C.DIM}{ts_str}{C.RESET}  {C.MAGENTA}GAME OVER{C.RESET}  Winner: {winner}  [{scr_str}]")
        print(_hr())
        self._event.set()

    def on_rooms_list(self, pkt: dict):
        rooms = pkt.get("rooms", [])
        print(f"\n{_banner('ACTIVE ROOMS', C.BLUE)}")
        print(_hr())
        if not rooms:
            print(f"  {C.DIM}No active rooms.{C.RESET}")
        for r in rooms:
            players = ", ".join(r.get("players", []))
            status  = r.get("status", "?")
            specs   = r.get("spectators", 0)
            color   = C.GREEN if status == "waiting" else C.YELLOW
            print(f"  {color}{r['room_id']}{C.RESET}  [{status}]  {players}  👁 {specs}")
        print(_hr())
        self._event.set()

    def on_player_disconnected(self, pkt: dict):
        username = pkt.get("username", "?")
        print(f"\n{C.YELLOW}⚠  {username} disconnected. Waiting for reconnect...{C.RESET}")

    def on_player_reconnected(self, pkt: dict):
        username = pkt.get("username", "?")
        print(f"\n{C.GREEN}✓ {username} reconnected!{C.RESET}")

    def on_error(self, pkt: dict):
        msg = pkt.get("message") or pkt.get("reason") or "Unknown error"
        print(f"\n{C.RED}⚠  Server: {msg}{C.RESET}")

    def on_disconnected(self):
        print(f"\n{C.RED}Connection lost.{C.RESET}")
        self._state = "DISCONNECTED"
        self._event.set()

    def update_latency(self, ms: float):
        self._latency = ms

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state
