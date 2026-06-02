# CodeDuel - Architecture Overview

## Project Structure

```
codeduel/
├── server/
│   ├── server.py          # Main TCP server entry point
│   ├── game_server.py     # Dedicated game server logic
│   ├── matchmaking.py     # Matchmaking queue system
│   ├── room.py            # Room / game session management
│   ├── game_state.py      # Game state machine
│   ├── protocol.py        # Packet definitions & validation
│   ├── ranking.py         # Ranking system (ELO / win-based)
│   ├── replay.py          # Match replay recorder
│   ├── logger.py          # Activity logger
│   └── questions.py       # Question bank loader
├── client/
│   ├── client.py          # CLI client entry point
│   └── ui.py              # Terminal UI (curses)
├── data/
│   ├── questions.json     # Question bank
│   ├── ranking.json       # Persistent ranking data
│   └── replays/           # Stored match replays
└── tests/
    ├── test_protocol.py
    ├── test_matchmaking.py
    └── test_game_state.py
```

## Communication Protocol

All messages are JSON-encoded and newline-delimited over TCP.

### Packet Types
- LOGIN / LOGIN_OK / LOGIN_FAIL
- MATCHMAKE / MATCHED
- JOIN_ROOM / ROOM_FULL / ROOM_JOINED
- SPECTATE / SPECTATE_OK
- START_GAME
- QUESTION
- SUBMIT_ANSWER / ANSWER_RESULT
- GAME_STATE
- PING / PONG
- RECONNECT / RECONNECT_OK / RECONNECT_FAIL
- GAME_OVER
- GET_RANKING / RANKING
- GET_REPLAY / REPLAY
- ERROR
