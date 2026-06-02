# Progress Log — CodeDuel

> **G04 - Final Project D-8 Kastangel** | Pemrograman Jaringan 2026

---

## Yang Sudah Dikerjakan

### Kenapa TCP?

Kami memilih **TCP (Transmission Control Protocol)** sebagai transport layer karena:

- **Reliable delivery** — Soal, jawaban, dan skor harus sampai ke semua client tanpa hilang. Kalau paket hilang di UDP, pemain bisa tidak menerima soal atau skor tidak sinkron.
- **Ordered** — Urutan packet penting: `START_GAME` harus diterima sebelum `QUESTION`, dan `QUESTION` harus diterima sebelum `ANSWER_RESULT`. TCP menjamin urutan ini.
- **No duplication** — Tidak ada risiko jawaban dikirim dua kali karena retransmit otomatis TCP, berbeda dengan UDP yang harus ditangani manual.
- **Simpel untuk aplikasi ini** — Karena game berbasis teks (bukan game FPS yang butuh low-latency ekstrem), overhead TCP tidak menjadi masalah. Latency 50–200ms masih perfectly playable.

UDP baru relevan kalau kita butuh streaming audio/video real-time (misalnya fitur voice chat ke depannya).

---

### Bagaimana Cara Kerjanya

#### Arsitektur Client-Server

```
[Client] ──TCP──► [Server :9000]
                      │
              ┌───────┼────────────┐
         Matchmaking  Room    GameState
              │       │            │
           queue   players    questions
                              timer
                              scoring
```

Server adalah **single source of truth** — semua game logic (validasi jawaban, hitung skor, timer soal) dijalankan di server. Client hanya mengirim input dan menampilkan state yang dikirim server.

#### Thread Model

Setiap client connection mendapatkan satu **thread** tersendiri (`ClientHandler`). Ini adalah model **thread-per-connection** yang simpel dan cukup untuk skala project ini.

```
Main Thread: accept() loop
├── ClientHandler Thread (player 1)
├── ClientHandler Thread (player 2)
├── ClientHandler Thread (spectator)
└── MatchmakingQueue Thread (background matcher)
```

Shared state (rooms, sessions, ranking) dilindungi dengan `threading.Lock()`.

#### Format Protokol

Semua pesan adalah **newline-delimited JSON** — setiap paket diakhiri `\n` dan di-parse per baris. Ini memudahkan debugging (bisa dibaca manusia) dan tidak perlu length-prefix framing.

```
CLIENT → SERVER: {"type":"SUBMIT_ANSWER","username":"ata","room_id":"AB12","question_index":3,"answer":"B","ts":1717...}\n
SERVER → CLIENT: {"type":"ANSWER_RESULT","correct":true,"points":100,"scores":{"ata":300,"bob":100},"ts":1717...}\n
```

---

### Fitur yang Sudah Jalan

| Fitur | Status | Catatan |
|---|---|---|
| TCP Server (multi-client) | ✅ Done | Thread-per-connection |
| Authentication (username) | ✅ Done | Duplicate check antar sesi aktif |
| Matchmaking Queue | ✅ Done | Auto-pair, background thread |
| Room System (1v1) | ✅ Done | Max 2 player, room registry global |
| Game State Machine | ✅ Done | WAITING→COUNTDOWN→QUESTION→GAME_OVER |
| Real-Time Quiz (20s/soal) | ✅ Done | Timer thread per pertandingan |
| Game State Sync | ✅ Done | Broadcast ke semua player + spectator |
| Anti-Invalid Packet | ✅ Done | Validasi type + required fields |
| Latency Indicator (Ping) | ✅ Done | PING/PONG setiap 5 detik |
| Reconnect Handling | ✅ Done | Grace period 30 detik |
| Spectator Mode | ✅ Done | Terima semua broadcast, read-only |
| Ranking System (ELO) | ✅ Done | Persisten ke `data/ranking.json` |
| Match Replay | ✅ Done | Event log per game di `data/replays/` |
| Activity Logging | ✅ Done | Rotating file + console |
| Terminal UI (CLI) | ✅ Done | ANSI colors, menu interaktif |
| Unit Tests (29 tests) | ✅ Done | Protocol, matchmaking, game state |

---

## Yang Mau Dikerjakan Selanjutnya

### 1. Web UI (Prioritas Tinggi)

Ganti terminal client dengan antarmuka berbasis browser.

**Rencana stack:**
- **Backend bridge**: WebSocket server (Python `websockets` atau `aiohttp`) yang relay antara browser dan TCP game server
- **Frontend**: HTML/CSS/JS murni (vanilla), tanpa framework besar

**Tampilan yang diinginkan:**
- Lobby: list room aktif, tombol matchmaking, leaderboard sidebar
- Game view: soal di tengah, countdown timer visual (lingkaran), skor real-time kedua pemain
- Replay viewer: timeline event bisa di-scrub maju/mundur
- Animasi jawaban benar/salah (flash hijau/merah)

**Catatan teknis:** Karena browser tidak bisa buka raw TCP socket, perlu layer WebSocket-to-TCP proxy di server side. Alternatif: refactor server untuk langsung support WebSocket.

---

### 2. Voice Chat

Pemain bisa ngobrol selama pertandingan berlangsung.

**Rencana:**
- Protokol: **UDP** (bukan TCP) — audio streaming butuh low latency, packet loss sesekali masih OK
- Encoding: PCM 16-bit → kompres dengan Opus codec
- Transport: Server relay audio stream antar dua client dalam satu room
- Library kandidat: `pyaudio` (capture/playback), `opuslib` (encode/decode)

**Tantangan:**
- UDP hole punching kalau client di belakang NAT
- Sinkronisasi jitter buffer
- Perlu thread/process tersendiri agar tidak ganggu game TCP thread

**Opsi simpel dulu:** Push-to-talk (kirim hanya saat tombol ditekan) untuk kurangi bandwidth dan kompleksitas.

---

### 3. Hal Kecil yang Masih Perlu Dibenahi

- [ ] Rate limiting submit_answer (cegah spam)
- [ ] Timeout untuk player yang AFK di lobby (tidak jawab apapun)
- [ ] Kategori soal bisa dipilih saat matchmaking
- [ ] Admin endpoint (misal via socket terpisah) untuk monitoring koneksi aktif
- [ ] Graceful shutdown server (kirim notif ke semua client sebelum mati)
- [ ] Docker compose untuk deploy server + client mudah

---

## Timeline Kasar

```
Week 1 (sekarang) — Core TCP server + CLI client ✅
Week 2            — Web UI (WebSocket bridge + frontend)
Week 3            — Voice chat (UDP)
Week 4            — Polish, testing, demo prep
```
