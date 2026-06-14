"""
game_server.py - Dedicated TCP game server for Duels.

Each client connection is handled in a dedicated thread.
The server validates all incoming packets and dispatches them
to the appropriate subsystem (matchmaking, room, ranking, replay).
"""

import socket
import threading
import time
import traceback
from typing import Optional

from . import logger, protocol, ranking
from .matchmaking import get_queue
from .protocol import PacketType, validate, encode, decode
from .replay import load_replay
from .room import get_room, list_rooms, Room

BUFFER_SIZE  = 4096
RECV_TIMEOUT = 120  # seconds; after this the connection is closed

# Rate limiting for SUBMIT_ANSWER
RATE_LIMIT_WINDOW = 2.0   # seconds
RATE_LIMIT_MAX    = 5     # max submits within the window


class ClientHandler(threading.Thread):
    """
    Handles one client connection.

    Lifecycle:
        connect → LOGIN → (MATCHMAKE | JOIN_ROOM | SPECTATE | GET_RANKING | …)
        → game packets → disconnect
    """

    def __init__(self, conn: socket.socket, addr: tuple, server: "GameServer"):
        super().__init__(daemon=True)
        self.conn     = conn
        self.addr     = addr
        self.server   = server
        self.username : Optional[str] = None
        self.room     : Optional[Room] = None
        self.is_spectator = False
        self._send_lock = threading.Lock()
        self._running   = True
        self.latency    = 0.0

        # Rate limiting state
        self._answer_times: list[float] = []

    # ------------------------------------------------------------------
    # Send / receive
    # ------------------------------------------------------------------

    def send(self, packet: dict):
        try:
            with self._send_lock:
                self.conn.sendall(encode(packet))
        except Exception:
            self._running = False

    def run(self):
        """Main receive loop."""
        self.conn.settimeout(RECV_TIMEOUT)
        buf = ""
        try:
            while self._running:
                try:
                    data = self.conn.recv(BUFFER_SIZE)
                except socket.timeout:
                    break
                if not data:
                    break

                buf += data.decode("utf-8", errors="replace")

                # Process newline-delimited packets
                while "\n" in buf:
                    raw, buf = buf.split("\n", 1)
                    raw = raw.strip()
                    if not raw:
                        continue
                    self._handle_raw(raw)

        except Exception as e:
            logger.log_error(f"ClientHandler {self.addr}", e)
        finally:
            self._cleanup()

    def _handle_raw(self, raw: str):
        # --- Parse ---
        try:
            packet = decode(raw)
        except Exception:
            logger.log_invalid_packet(str(self.addr), "JSON parse error", raw)
            self.send(protocol.make_invalid_packet("JSON parse error"))
            return

        # --- Validate ---
        ok, reason = validate(packet)
        if not ok:
            logger.log_invalid_packet(str(self.addr), reason, raw)
            self.send(protocol.make_invalid_packet(reason))
            return

        # --- Dispatch ---
        ptype = packet.get("type")
        try:
            self._dispatch(ptype, packet)
        except Exception as e:
            logger.log_error(f"Dispatch {ptype}", e)
            self.send(protocol.make_error(f"Server error handling {ptype}"))

    def _dispatch(self, ptype: str, pkt: dict):
        # Un-authenticated commands
        if ptype == PacketType.LOGIN:
            self._handle_login(pkt)
            return

        if ptype == PacketType.RECONNECT:
            self._handle_reconnect(pkt)
            return

        if ptype == PacketType.GET_RANKING:
            self._handle_get_ranking(pkt)
            return

        if ptype == PacketType.LIST_ROOMS:
            self._handle_list_rooms(pkt)
            return

        # All other packets require login
        if not self.username:
            self.send(protocol.make_error("Not logged in"))
            return

        dispatch = {
            PacketType.MATCHMAKE:        self._handle_matchmake,
            PacketType.CANCEL_MATCHMAKE: self._handle_cancel_matchmake,
            PacketType.JOIN_ROOM:        self._handle_join_room,
            PacketType.SPECTATE:         self._handle_spectate,
            PacketType.SUBMIT_ANSWER:    self._handle_submit_answer,
            PacketType.PING:             self._handle_ping,
            PacketType.PONG:             self._handle_pong,
            PacketType.GET_REPLAY:       self._handle_get_replay,
            PacketType.DISCONNECT:       self._handle_client_disconnect,
            PacketType.VOICE_SIGNAL:     self._handle_voice_signal,
        }

        handler = dispatch.get(ptype)
        if handler:
            handler(pkt)
        else:
            self.send(protocol.make_error(f"Unhandled packet type: {ptype}"))

    # ------------------------------------------------------------------
    # Packet handlers
    # ------------------------------------------------------------------

    def _handle_login(self, pkt: dict):
        username = pkt["username"].strip()
        if not username or len(username) > 20:
            self.send(protocol.make_login_fail("Invalid username (1–20 chars)"))
            return

        # Check duplicate in active sessions
        if self.server.is_logged_in(username):
            self.server.kick_user(username)

        self.username = username
        token = f"{username}-{int(time.time())}"
        self.server.register(self)
        ranking.ensure_player(username)
        logger.log_login(username, str(self.addr))
        self.send(protocol.make_login_ok(username, token))

    def _handle_matchmake(self, pkt: dict):
        if self.room:
            if not getattr(self.room, "_finished", False) and not self.is_spectator:
                self.send(protocol.make_error("Already in an active room"))
                return
            # Leave previous room
            if self.is_spectator:
                self.room.remove_spectator(self)
                self.is_spectator = False
            else:
                self.room.remove_player(self.username)
            self.room = None
            
        get_queue().enqueue(self.username, self)

    def _handle_cancel_matchmake(self, pkt: dict):
        get_queue().dequeue(self.username)
        logger.log_info(f"{self.username} cancelled matchmaking")

    def _handle_join_room(self, pkt: dict):
        room_id = pkt["room_id"]
        room = get_room(room_id)
        if not room:
            self.send(protocol.make_error("Room not found"))
            return
        if room.is_full():
            self.send(protocol.make_error("Room is full"))
            return

        added = room.add_player(self.username, self)
        if not added:
            self.send(protocol.make_error("Could not join room"))
            return

        self.room = room
        logger.log_join_room(self.username, room_id)
        self.send(protocol.make_room_joined(
            room_id, room.get_player_names(), room.spectator_count()
        ))
        room.broadcast(
            protocol.make_room_joined(room_id, room.get_player_names(),
                                      room.spectator_count()),
            exclude=self.username
        )
        room.try_start_game()

    def _handle_spectate(self, pkt: dict):
        room_id = pkt["room_id"]
        room = get_room(room_id)
        if not room:
            self.send(protocol.make_spectate_fail("Room not found"))
            return

        room.add_spectator(self)
        self.room = room
        self.is_spectator = True
        logger.log_spectate(self.username, room_id)

        snap = room.game.snapshot() if room.game else {}
        if room.game:
            with room._lock:
                snap["latencies"] = {
                    u: getattr(h, "latency", 0.0) for u, h in room.players.items()
                }
        self.send(protocol.make_spectate_ok(room_id, snap))

    def _handle_submit_answer(self, pkt: dict):
        if not self.room or not self.room.game:
            self.send(protocol.make_error("Not in an active game"))
            return

        # Rate limiting
        now = time.time()
        self._answer_times = [t for t in self._answer_times
                               if now - t < RATE_LIMIT_WINDOW]
        if len(self._answer_times) >= RATE_LIMIT_MAX:
            self.send(protocol.make_error("Rate limit exceeded — slow down!"))
            logger.log_info(f"Rate limit hit by {self.username}")
            return
        self._answer_times.append(now)

        accepted = self.room.game.submit_answer(
            self.username, pkt["question_index"], pkt["answer"]
        )
        if not accepted:
            self.send(protocol.make_error("Answer rejected"))

    def _handle_ping(self, pkt: dict):
        self.latency = float(pkt.get("latency", 0.0))
        # Server replies with PONG carrying the client's timestamp
        self.send(protocol.make_pong(self.username, pkt.get("ts", time.time())))

    def _handle_pong(self, pkt: dict):
        # Client acknowledged our PONG — compute latency
        client_ts = float(pkt.get("timestamp", 0))
        if client_ts:
            latency_ms = (time.time() - client_ts) * 1000
            logger.log_ping(self.username, latency_ms)

    def _handle_reconnect(self, pkt: dict):
        username = pkt["username"]
        room_id  = pkt["room_id"]
        room     = get_room(room_id)

        if not room:
            self.send(protocol.make_reconnect_fail("Room not found"))
            return
        if not room.has_player(username):
            self.send(protocol.make_reconnect_fail("No pending reconnect for this player"))
            return

        ok = room.reconnect_player(username, self)
        if not ok:
            self.send(protocol.make_reconnect_fail("Reconnect window expired"))
            return

        self.username = username
        self.room     = room
        self.server.register(self)

        snap = room.game.snapshot() if room.game else {}
        if room.game:
            with room._lock:
                snap["latencies"] = {
                    u: getattr(h, "latency", 0.0) for u, h in room.players.items()
                }
        self.send(protocol.make_reconnect_ok(room_id, snap))
        # Notify other players
        room.broadcast(
            {"type": "PLAYER_RECONNECTED", "username": username},
            exclude=username
        )

    def _handle_get_ranking(self, pkt: dict):
        entries = ranking.get_ranking(limit=20)
        self.send(protocol.make_ranking(entries))

    def _handle_get_replay(self, pkt: dict):
        room_id = pkt["room_id"]
        data = load_replay(room_id)
        if not data:
            self.send(protocol.make_error(f"Replay not found for room {room_id}"))
            return
        self.send(protocol.make_replay(room_id, data["events"]))

    def _handle_list_rooms(self, pkt: dict):
        self.send(protocol.make_rooms_list(list_rooms()))

    def _handle_client_disconnect(self, pkt: dict):
        self._running = False

    def _handle_voice_signal(self, pkt: dict):
        """Relay a WebRTC signaling packet to all other room members."""
        if not self.room:
            self.send(protocol.make_error("Not in a room"))
            return
        relay = protocol.make_voice_signal(
            from_user   = self.username,
            signal_type = pkt["signal_type"],
            data        = pkt["data"],
        )
        # Broadcast to everyone except the sender
        self.room.broadcast(relay, exclude=self.username)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self):
        self._running = False
        try:
            self.conn.close()
        except Exception:
            pass

        if self.username:
            self.server.unregister(self)

        if self.room and self.username:
            if self.is_spectator:
                self.room.remove_spectator(self)
            else:
                removed = self.room.remove_player(self.username, self)
                # If game is ongoing, notify others
                if removed and self.room.game and self.room.game.status.name not in ("GAME_OVER",):
                    self.room.broadcast(
                        {"type": "PLAYER_DISCONNECTED", "username": self.username},
                        exclude=self.username
                    )

        logger.log_disconnect(self.username or str(self.addr), str(self.addr))

        # Remove from matchmaking queue if they were waiting
        if self.username:
            get_queue().dequeue(self.username)


# ---------------------------------------------------------------------------
# Game Server
# ---------------------------------------------------------------------------

class GameServer:
    """
    TCP server that accepts connections and spawns ClientHandler threads.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9000):
        self.host = host
        self.port = port
        self._sessions: dict[str, ClientHandler] = {}  # username → handler
        self._sessions_lock = threading.Lock()

    def is_logged_in(self, username: str) -> bool:
        with self._sessions_lock:
            return username in self._sessions

    def kick_user(self, username: str):
        with self._sessions_lock:
            handler = self._sessions.get(username)
            if handler:
                handler.send(protocol.make_error("Logged in from another location"))
                handler._running = False
                del self._sessions[username]

    def register(self, handler: ClientHandler):
        with self._sessions_lock:
            self._sessions[handler.username] = handler

    def unregister(self, handler: ClientHandler):
        with self._sessions_lock:
            if handler.username in self._sessions:
                del self._sessions[handler.username]

    def active_sessions(self) -> int:
        with self._sessions_lock:
            return len(self._sessions)

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(50)

        logger.log_info(f"Duels server listening on {self.host}:{self.port}")

        try:
            while True:
                conn, addr = sock.accept()
                handler = ClientHandler(conn, addr, self)
                handler.start()
                logger.log_info(
                    f"New connection from {addr} | active={self.active_sessions()}"
                )
        except KeyboardInterrupt:
            logger.log_info("Server shutting down.")
        finally:
            sock.close()
