"""
web_server.py - WebSocket-based web gateway for CodeDuel.

Bridges between browser WebSocket clients and the backend TCP game server.
Also serves the static web frontend on HTTP.

Usage:
    python -m web.web_server [--host HOST] [--port PORT] [--game-host HOST] [--game-port PORT]

Dependencies (stdlib only + websockets):
    pip install websockets
"""

import argparse
import asyncio
import json
import os
import socket
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# ---------------------------------------------------------------------------
# Try to import websockets; provide helpful error if missing
# ---------------------------------------------------------------------------
try:
    import websockets
    import websockets.exceptions
except ImportError:
    print("ERROR: 'websockets' package not found.")
    print("Install it with: pip install websockets")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WEB_DIR = os.path.join(os.path.dirname(__file__), "static")
GAME_HOST = "127.0.0.1"
GAME_PORT = 9000
WS_HOST   = "0.0.0.0"
WS_PORT   = 8765
HTTP_PORT = 8080

BUFFER_SIZE = 4096


# ---------------------------------------------------------------------------
# TCP → WebSocket Bridge
# ---------------------------------------------------------------------------

class TCPBridge:
    """
    Maintains a TCP connection to the game server on behalf of one
    WebSocket browser client.  Forwards packets bidirectionally.
    """

    def __init__(self, ws, game_host: str, game_port: int):
        self.ws        = ws
        self.game_host = game_host
        self.game_port = game_port
        self.tcp_sock  = None
        self._running  = False

    async def run(self):
        # Connect to the game server
        loop = asyncio.get_event_loop()
        try:
            self.tcp_sock = await loop.run_in_executor(
                None, self._tcp_connect
            )
        except Exception as e:
            await self.ws.send(json.dumps({
                "type": "ERROR",
                "message": f"Cannot connect to game server: {e}"
            }))
            return

        self._running = True

        # Start the TCP → WS forwarder in a background thread
        fwd_task = asyncio.create_task(self._tcp_to_ws())

        try:
            # WS → TCP: forward every message the browser sends
            async for raw in self.ws:
                if not self._running:
                    break
                try:
                    # Validate it's JSON and add newline for TCP protocol
                    pkt = json.loads(raw)
                    data = (json.dumps(pkt) + "\n").encode("utf-8")
                    await loop.run_in_executor(None, self._tcp_send, data)
                except json.JSONDecodeError:
                    await self.ws.send(json.dumps({
                        "type": "INVALID_PACKET",
                        "reason": "Not valid JSON"
                    }))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._running = False
            self._tcp_close()
            fwd_task.cancel()

    def _tcp_connect(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((self.game_host, self.game_port))
        s.settimeout(None)
        return s

    def _tcp_send(self, data: bytes):
        if self.tcp_sock:
            try:
                self.tcp_sock.sendall(data)
            except Exception:
                self._running = False

    def _tcp_close(self):
        if self.tcp_sock:
            try:
                self.tcp_sock.close()
            except Exception:
                pass
            self.tcp_sock = None

    async def _tcp_to_ws(self):
        """Read newline-delimited JSON from TCP and push to WebSocket."""
        loop = asyncio.get_event_loop()
        buf  = ""
        while self._running:
            try:
                data = await loop.run_in_executor(None, self._tcp_recv)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            await self.ws.send(line)
                        except websockets.exceptions.ConnectionClosed:
                            self._running = False
                            return
            except Exception:
                break
        self._running = False
        # Notify browser of disconnect
        try:
            await self.ws.send(json.dumps({
                "type": "SERVER_DISCONNECTED",
                "message": "Connection to game server lost"
            }))
        except Exception:
            pass

    def _tcp_recv(self) -> bytes:
        if not self.tcp_sock:
            return b""
        try:
            return self.tcp_sock.recv(BUFFER_SIZE)
        except Exception:
            return b""


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

async def ws_handler(websocket, game_host: str, game_port: int):
    """Entry point for each new WebSocket connection."""
    bridge = TCPBridge(websocket, game_host, game_port)
    await bridge.run()


# ---------------------------------------------------------------------------
# HTTP static file server (runs in a separate thread)
# ---------------------------------------------------------------------------

class QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # suppress access logs


def run_http_server(port: int):
    os.makedirs(WEB_DIR, exist_ok=True)
    httpd = HTTPServer(("0.0.0.0", port), QuietHandler)
    print(f"[HTTP] Static files served at http://0.0.0.0:{port}/")
    httpd.serve_forever()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(ws_host: str, ws_port: int, game_host: str, game_port: int,
               http_port: int):

    handler = lambda ws: ws_handler(ws, game_host, game_port)

    print(f"[WS]   WebSocket bridge on ws://{ws_host}:{ws_port}")
    print(f"[GAME] Forwarding to TCP {game_host}:{game_port}")
    print(f"[HTTP] Web frontend: http://localhost:{http_port}/")

    async with websockets.serve(handler, ws_host, ws_port):
        await asyncio.Future()   # run forever


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CodeDuel Web Gateway")
    parser.add_argument("--host",       default=WS_HOST,   help="WebSocket bind host")
    parser.add_argument("--port",       type=int, default=WS_PORT,   help="WebSocket port")
    parser.add_argument("--game-host",  default=GAME_HOST, help="Game server host")
    parser.add_argument("--game-port",  type=int, default=GAME_PORT, help="Game server port")
    parser.add_argument("--http-port",  type=int, default=HTTP_PORT, help="HTTP static server port")
    args = parser.parse_args()

    # Start HTTP server in a daemon thread
    t = threading.Thread(
        target=run_http_server, args=(args.http_port,), daemon=True
    )
    t.start()

    try:
        asyncio.run(main(args.host, args.port, args.game_host, args.game_port,
                         args.http_port))
    except KeyboardInterrupt:
        print("\n[WEB] Shutting down.")
