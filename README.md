# CodeDuel 🎮⚔️

**Multiplayer Coding Quiz Battle** — Final Project Pemrograman Jaringan

---

## Fitur Utama

| Fitur | Deskripsi |
|---|---|
| Authentication | Login sederhana berbasis username |
| Matchmaking | Auto-match dua pemain ke satu room |
| Room System | 1v1 room, max 2 pemain aktif |
| Game State Sync | Sinkronisasi soal, skor, timer ke semua client |
| Real-Time Battle | 20 detik per soal, skor langsung diperbarui |
| Latency Indicator | Ping/PONG setiap 5 detik, tampil di UI |
| Reconnect Handling | Grace period 30 detik untuk reconnect |
| Spectator Mode | Tonton match yang sedang berjalan |
| Ranking System | ELO rating + win/loss, persisten ke JSON |
| Match Replay | Semua event tersimpan, bisa diputar ulang |
| Anti-Invalid Packet | Validasi format & field wajib tiap packet |
| Activity Logging | Semua event dicatat ke log file + console |

---

## Arsitektur

```
[Player Client 1] ──┐
                    ├──► [TCP Game Server :9000] ──► [ranking.json]
[Player Client 2] ──┤                           ──► [replays/*.json]
                    │                           ──► [logs/codeduel.log]
[Spectator]     ────┘
```

**Stack:** Python 3.10+, stdlib only (socket, threading, json, logging)

---

## Struktur Direktori

```
codeduel/
├── server/
│   ├── server.py        # Entry point server
│   ├── game_server.py   # TCP server + ClientHandler
│   ├── matchmaking.py   # Matchmaking queue
│   ├── room.py          # Room management
│   ├── game_state.py    # Game state machine
│   ├── protocol.py      # Packet definitions & validation
│   ├── ranking.py       # ELO ranking system
│   ├── replay.py        # Match replay recorder
│   ├── logger.py        # Activity logger
│   └── questions.py     # Question bank loader
├── client/
│   ├── client.py        # Client entry point
│   └── ui.py            # Terminal UI (ANSI)
├── data/
│   ├── questions.json   # 20 soal (Python, Networking, DS, OOP)
│   ├── ranking.json     # (auto-generated)
│   └── replays/         # (auto-generated)
└── tests/
    ├── test_protocol.py
    ├── test_matchmaking.py
    └── test_game_state.py
```

---

## Cara Menjalankan

### 1. Jalankan Server

```bash
python -m server.server
# atau dengan opsi:
python -m server.server --host 0.0.0.0 --port 9000
```

### 2. Jalankan Client

```bash
# Terminal 1
python -m client.client

# Terminal 2 (pemain kedua / spectator)
python -m client.client --host 127.0.0.1 --port 9000
```

### 3. Jalankan Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Protokol Komunikasi

Semua pesan menggunakan **newline-delimited JSON** over **TCP**.

### Format Packet

```json
{
  "type": "SUBMIT_ANSWER",
  "username": "player1",
  "room_id": "ROOM123",
  "question_index": 2,
  "answer": "B",
  "ts": 1717200000.0
}
```

### Tabel Packet Type

| Arah | Type | Deskripsi |
|---|---|---|
| C→S | `LOGIN` | Login dengan username |
| S→C | `LOGIN_OK` | Login berhasil + session token |
| S→C | `LOGIN_FAIL` | Login gagal + alasan |
| C→S | `MATCHMAKE` | Masuk antrian matchmaking |
| S→C | `MATCHED` | Berhasil dicocokkan, info room + lawan |
| C→S | `JOIN_ROOM` | Bergabung ke room tertentu |
| S→C | `ROOM_JOINED` | Konfirmasi masuk room |
| C→S | `SPECTATE` | Masuk sebagai spectator |
| S→C | `SPECTATE_OK` | Konfirmasi spectate + current state |
| S→C | `START_GAME` | Pertandingan dimulai |
| S→C | `QUESTION` | Soal baru dikirim |
| C→S | `SUBMIT_ANSWER` | Kirim jawaban |
| S→C | `ANSWER_RESULT` | Hasil jawaban (benar/salah + poin) |
| S→C | `GAME_STATE` | Update state (skor, status, dll) |
| S→C | `GAME_OVER` | Pertandingan selesai + pemenang |
| C→S | `PING` | Cek latency |
| S→C | `PONG` | Balasan ping |
| C→S | `RECONNECT` | Minta reconnect ke room |
| S→C | `RECONNECT_OK` | Reconnect berhasil + state saat ini |
| S→C | `RECONNECT_FAIL` | Reconnect gagal + alasan |
| C→S | `GET_RANKING` | Minta data ranking |
| S→C | `RANKING` | Data leaderboard |
| C→S | `GET_REPLAY` | Minta replay suatu room |
| S→C | `REPLAY` | Event history pertandingan |
| C→S | `LIST_ROOMS` | Daftar room aktif |
| S→C | `ROOMS_LIST` | Info semua room |
| S→C | `ERROR` | Pesan error |
| S→C | `INVALID_PACKET` | Packet tidak valid |

---

## Alur Game

```
1. Client connect → LOGIN
2. Server validasi username → LOGIN_OK
3. Client pilih MATCHMAKE atau JOIN_ROOM
4. Server cocokkan 2 player → MATCHED + ROOM_JOINED
5. Server kirim START_GAME
6. Untuk setiap soal:
   a. Server kirim QUESTION (dengan timer 20 detik)
   b. Players kirim SUBMIT_ANSWER
   c. Server validasi → ANSWER_RESULT + GAME_STATE
   d. Setelah semua jawab atau timeout → soal berikutnya
7. Setelah semua soal selesai → GAME_OVER
8. Server update ranking (ELO) + simpan replay
```

---

## Ranking System

Menggunakan **ELO Rating** (standar chess rating):
- Rating awal: 1000
- K-factor: 32
- Formula: `new_elo = old_elo + K * (actual - expected)`
- Ranking disimpan di `data/ranking.json`

---

## Match Replay

Setiap pertandingan disimpan di `data/replays/<room_id>.json` berisi:
- Daftar event: `GAME_START`, `QUESTION`, `ANSWER`, `TIMEOUT`, `DISCONNECT`, `RECONNECT`, `GAME_OVER`
- Timestamp relatif (elapsed) setiap event
- Semua data jawaban dan skor

---

## Kelompok

> **G04 - Final Project D-8 Kastangel**
> Pemrograman Jaringan — 2026
