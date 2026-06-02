"""
client.py - CodeDuel terminal client.

Features:
- Login
- Matchmaking / Join room / Spectate
- Real-time quiz battle UI
- Ping/Latency indicator
- Reconnect handling
- Ranking display
- Match replay viewer

Usage:
    python -m client.client [--host HOST] [--port PORT]
"""

import argparse
import json
import socket
import sys
import threading
import time
import os

# Allow running as a module from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from client.ui import CodeDuelUI

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9000
BUFFER_SIZE = 4096


class GameClient:
    """Manages the TCP connection and delegates UI updates."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.username: str = ""
        self.room_id: str = ""
        self.ui = CodeDuelUI(self)
        self._send_lock = threading.Lock()
        self._running   = False
        self._last_ping_ts = 0.0
        self.latency_ms = 0.0

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None)
            self._running = True
            return True
        except Exception as e:
            return False

    def disconnect(self):
        self._running = False
        if self.sock:
            try:
                self.send({"type": "DISCONNECT", "username": self.username})
                self.sock.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Send / receive
    # ------------------------------------------------------------------

    def send(self, packet: dict):
        if not self.sock:
            return
        try:
            raw = (json.dumps(packet) + "\n").encode("utf-8")
            with self._send_lock:
                self.sock.sendall(raw)
        except Exception:
            self._running = False

    def start_receive_loop(self):
        t = threading.Thread(target=self._recv_loop, daemon=True)
        t.start()

    def _recv_loop(self):
        buf = ""
        while self._running:
            try:
                data = self.sock.recv(BUFFER_SIZE)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            pkt = json.loads(line)
                            self._handle_packet(pkt)
                        except json.JSONDecodeError:
                            pass
            except Exception:
                break

        self._running = False
        self.ui.on_disconnected()

    def _handle_packet(self, pkt: dict):
        ptype = pkt.get("type", "")
        handlers = {
            "LOGIN_OK":            self.ui.on_login_ok,
            "LOGIN_FAIL":          self.ui.on_login_fail,
            "MATCHED":             self.ui.on_matched,
            "ROOM_JOINED":         self.ui.on_room_joined,
            "SPECTATE_OK":         self.ui.on_spectate_ok,
            "SPECTATE_FAIL":       self.ui.on_spectate_fail,
            "START_GAME":          self.ui.on_start_game,
            "QUESTION":            self.ui.on_question,
            "ANSWER_RESULT":       self.ui.on_answer_result,
            "GAME_STATE":          self.ui.on_game_state,
            "GAME_OVER":           self.ui.on_game_over,
            "PONG":                self._on_pong,
            "RECONNECT_OK":        self.ui.on_reconnect_ok,
            "RECONNECT_FAIL":      self.ui.on_reconnect_fail,
            "RANKING":             self.ui.on_ranking,
            "REPLAY":              self.ui.on_replay,
            "ROOMS_LIST":          self.ui.on_rooms_list,
            "PLAYER_DISCONNECTED": self.ui.on_player_disconnected,
            "PLAYER_RECONNECTED":  self.ui.on_player_reconnected,
            "ERROR":               self.ui.on_error,
            "INVALID_PACKET":      self.ui.on_error,
        }
        fn = handlers.get(ptype)
        if fn:
            fn(pkt)

    # ------------------------------------------------------------------
    # Ping
    # ------------------------------------------------------------------

    def start_ping_loop(self):
        t = threading.Thread(target=self._ping_loop, daemon=True)
        t.start()

    def _ping_loop(self):
        while self._running:
            time.sleep(5)
            if self.username and self._running:
                self._last_ping_ts = time.time()
                self.send({"type": "PING", "username": self.username,
                           "ts": self._last_ping_ts})

    def _on_pong(self, pkt: dict):
        server_ts = float(pkt.get("timestamp", 0))
        if server_ts:
            self.latency_ms = (time.time() - server_ts) * 1000
            self.ui.update_latency(self.latency_ms)

    # ------------------------------------------------------------------
    # High-level actions
    # ------------------------------------------------------------------

    def login(self, username: str):
        self.username = username
        self.send({"type": "LOGIN", "username": username})

    def matchmake(self):
        self.send({"type": "MATCHMAKE", "username": self.username})

    def join_room(self, room_id: str):
        self.room_id = room_id
        self.send({"type": "JOIN_ROOM", "username": self.username,
                   "room_id": room_id})

    def spectate(self, room_id: str):
        self.room_id = room_id
        self.send({"type": "SPECTATE", "username": self.username,
                   "room_id": room_id})

    def submit_answer(self, q_index: int, answer: str):
        self.send({
            "type": "SUBMIT_ANSWER",
            "username": self.username,
            "room_id": self.room_id,
            "question_index": q_index,
            "answer": answer,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    def get_ranking(self):
        self.send({"type": "GET_RANKING"})

    def get_replay(self, room_id: str):
        self.send({"type": "GET_REPLAY", "room_id": room_id})

    def list_rooms(self):
        self.send({"type": "LIST_ROOMS"})

    def reconnect(self, username: str, room_id: str):
        self.username = username
        self.room_id  = room_id
        self.send({"type": "RECONNECT", "username": username, "room_id": room_id})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CodeDuel Client")
    parser.add_argument("--host", default=SERVER_HOST)
    parser.add_argument("--port", type=int, default=SERVER_PORT)
    args = parser.parse_args()

    client = GameClient(args.host, args.port)

    print(f"\n{'='*50}")
    print("  ██████╗ ██████╗ ██████╗ ███████╗")
    print("  ██╔════╝██╔═══██╗██╔══██╗██╔════╝")
    print("  ██║     ██║   ██║██║  ██║█████╗  ")
    print("  ██║     ██║   ██║██║  ██║██╔══╝  ")
    print("  ╚██████╗╚██████╔╝██████╔╝███████╗")
    print("   ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝")
    print("         D U E L  v1.0")
    print(f"{'='*50}\n")
    print(f"Connecting to {args.host}:{args.port} ...", end=" ", flush=True)

    if not client.connect():
        print("FAILED")
        print("Could not connect to the server. Is it running?")
        sys.exit(1)

    print("OK ✓\n")
    client.start_receive_loop()
    client.start_ping_loop()
    client.ui.run()


if __name__ == "__main__":
    main()
