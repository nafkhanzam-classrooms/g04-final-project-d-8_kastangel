/* ============================================================
   Duels – JavaScript Logic (Light Theme & HP System)
   ============================================================ */

'use strict';

// ── State ─────────────────────────────────────────────────────
const state = {
  ws: null,
  username: '',
  roomId: '',
  players: [],
  scores: {},
  hp: {},
  qIndex: 0,
  qTotal: 0,
  qData: null,
  timeLimit: 20,
  qReceivedAt: 0,
  answered: false,
  locked: false,
  latency: 0,
  timerInterval: null,
  pingInterval: null,
  isSpectator: false,
  _pingTs: 0,
  specTimerInterval: null,
  matchmakeInterval: null,
  matchmakeStart: 0,
  micEnabled: false
};

let isReconnecting = false;
let autoReconnectInterval = null;

// ── Session Persistence (localStorage) ────────────────────────
const SESSION_KEY = 'duels_session';

function saveSession() {
  if (!state.username) return;
  const serverUrl = document.getElementById('input-server')?.value?.trim() || 'ws://192.168.100.239:8765';
  const session = {
    username: state.username,
    roomId: state.roomId,
    isSpectator: state.isSpectator,
    serverUrl,
    savedAt: Date.now()
  };
  try { localStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch(e) {}
}

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    // Expire sessions older than 30 minutes
    if (Date.now() - s.savedAt > 30 * 60 * 1000) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return s;
  } catch(e) { return null; }
}

function clearSession() {
  try { localStorage.removeItem(SESSION_KEY); } catch(e) {}
}

// ── Screen Management ──────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const target = document.getElementById('screen-' + id);
  if (target) {
    target.classList.add('active');
  }
}

// ── Toast Notifications ─────────────────────────────────────────
function toast(msg, type = 'info', duration = 3500) {
  const icons = { info: 'ℹ️', success: '✅', error: '❌', warn: '⚠️' };
  const container = document.getElementById('toast-container');
  if (!container) return;
  
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] || '💬'}</span><span>${msg}</span>`;
  container.appendChild(el);
  
  setTimeout(() => {
    el.style.animation = 'slideOutRight 0.3s ease forwards';
    setTimeout(() => el.remove(), 300);
  }, duration);
}

// ── Event Logger ───────────────────────────────────────────────
function addLog(msg, type = 'info') {
  const log = document.getElementById('event-log');
  if (!log) return;
  const timeStr = new Date().toLocaleTimeString();
  const el = document.createElement('div');
  el.className = `log-entry ${type}`;
  el.textContent = `[${timeStr}] ${msg}`;
  log.prepend(el);
  
  if (log.children.length > 100) {
    log.lastChild.remove();
  }
}

// ── WebSocket Connection & Lifecycle ───────────────────────────
function doConnect(opts = {}) {
  const serverUrl = opts.serverUrl || document.getElementById('input-server').value.trim();
  const username  = opts.username  || document.getElementById('input-username').value.trim();
  const errEl  = document.getElementById('connect-error');
  const statEl = document.getElementById('connect-status');

  if (errEl)  errEl.classList.add('hidden');
  if (statEl) statEl.classList.add('hidden');

  if (!username || username.length > 20) {
    if (errEl) { errEl.textContent = 'Username must be 1–20 characters.'; errEl.classList.remove('hidden'); }
    return;
  }

  if (statEl) { statEl.textContent = 'Connecting to server...'; statEl.classList.remove('hidden'); }
  const btnConnect = document.getElementById('btn-connect');
  if (btnConnect) btnConnect.disabled = true;

  try {
    state.ws = new WebSocket(serverUrl);
  } catch (e) {
    if (errEl) { errEl.textContent = 'Invalid WebSocket URL: ' + e.message; errEl.classList.remove('hidden'); }
    if (statEl) statEl.classList.add('hidden');
    if (btnConnect) btnConnect.disabled = false;
    return;
  }

  state.ws.onopen = () => {
    if (statEl) statEl.textContent = 'Connected! Logging in...';
    state.username = username;
    sendWS({ type: 'LOGIN', username });
  };

  state.ws.onmessage = (ev) => {
    try {
      const pkt = JSON.parse(ev.data);
      dispatch(pkt);
    } catch (e) {
      console.error('Failed to parse packet:', e);
    }
  };

  state.ws.onerror = () => {
    if (errEl) { errEl.textContent = 'Failed to connect. Check if WebSocket server is running.'; errEl.classList.remove('hidden'); }
    if (statEl) statEl.classList.add('hidden');
    if (btnConnect) btnConnect.disabled = false;
  };

  state.ws.onclose = () => {
    stopPing();
    stopTimer();
    saveSession();
    
    if (state.username) {
      toast('Connection lost. Reconnecting...', 'warn', 5000);
      addLog('Connection lost. Auto-reconnecting...', 'warn');
      isReconnecting = true;
      attemptAutoReconnect();
    } else {
      if (btnConnect) btnConnect.disabled = false;
      showScreen('connect');
    }
  };
}

function attemptAutoReconnect() {
  if (autoReconnectInterval) return;
  autoReconnectInterval = setInterval(() => {
    try {
      const serverUrl = document.getElementById('input-server')?.value?.trim() || 'ws://192.168.100.239:8765';
      const newWs = new WebSocket(serverUrl);
      
      newWs.onopen = () => {
        clearInterval(autoReconnectInterval);
        autoReconnectInterval = null;
        state.ws = newWs;
        
        state.ws.onmessage = (ev) => {
          try { dispatch(JSON.parse(ev.data)); } catch (e) {}
        };
        state.ws.onclose = () => {
          saveSession();
          if (state.username) attemptAutoReconnect();
        };
        state.ws.onerror = () => {};
        
        sendWS({ type: 'LOGIN', username: state.username });
      };
      
      newWs.onerror = () => {}; // silent retry
    } catch (e) {
      console.log("Reconnect failed", e);
    }
  }, 3000);
}

function sendWS(pkt) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(pkt));
  }
}

function doLogout() {
  clearSession();
  if (state.username) {
    sendWS({ type: 'DISCONNECT', username: state.username });
  }
  if (state.ws) {
    state.ws.onclose = null; // prevent auto-reconnect
    state.ws.close();
    state.ws = null;
  }
  isReconnecting = false;
  if (autoReconnectInterval) { clearInterval(autoReconnectInterval); autoReconnectInterval = null; }
  stopPing();
  stopTimer();
  state.username = '';
  state.roomId = '';
  state.isSpectator = false;
  state.players = [];
  showScreen('connect');
  const btnConnect = document.getElementById('btn-connect');
  if (btnConnect) btnConnect.disabled = false;
  const statEl = document.getElementById('connect-status');
  if (statEl) statEl.classList.add('hidden');
}

// ── Ping/Pong & Latency ────────────────────────────────────────
function startPing() {
  stopPing();
  state.pingInterval = setInterval(() => {
    if (state.username) {
      state._pingTs = Date.now();
      sendWS({ type: 'PING', username: state.username, ts: state._pingTs / 1000, latency: state.latency || 0 });
    }
  }, 5000);
}

function stopPing() {
  if (state.pingInterval) {
    clearInterval(state.pingInterval);
    state.pingInterval = null;
  }
}

function onPong(pkt) {
  const ts = pkt.timestamp;
  if (ts) {
    state.latency = (Date.now() / 1000 - ts) * 1000;
    const latencyVal = Math.round(state.latency);
    const display = `${latencyVal} ms`;
    
    // Update headers and game indicators
    const pingTextEls = [document.getElementById('hdr-ping-val'), document.getElementById('game-ping-val')];
    pingTextEls.forEach(el => { if (el) el.textContent = display; });

    const pingDotEls = [document.getElementById('hdr-ping-dot'), document.getElementById('game-ping-dot')];
    pingDotEls.forEach(dot => {
      if (dot) {
        dot.className = 'ping-icon';
        if (latencyVal >= 150) dot.classList.add('error');
        else if (latencyVal >= 50) dot.classList.add('warn');
      }
    });
  }
}

// ── Matchmaking ────────────────────────────────────────────────
function doMatchmake() {
  hideInlineForms();
  document.getElementById('matchmake-waiting').classList.remove('hidden');
  const btn = document.getElementById('btn-matchmake');
  if (btn) btn.style.pointerEvents = 'none';
  
  state.matchmakeStart = Date.now();
  if (state.matchmakeInterval) clearInterval(state.matchmakeInterval);
  state.matchmakeInterval = setInterval(() => {
    const el = document.getElementById('mm-wait-time');
    if (el) el.textContent = Math.floor((Date.now() - state.matchmakeStart) / 1000) + 's';
  }, 1000);

  sendWS({ type: 'MATCHMAKE', username: state.username });
  addLog('Entering matchmaking queue...', 'info');
}

function cancelMatchmake() {
  sendWS({ type: 'CANCEL_MATCHMAKE', username: state.username });
  document.getElementById('matchmake-waiting').classList.add('hidden');
  const btn = document.getElementById('btn-matchmake');
  if (btn) btn.style.pointerEvents = '';
  if (state.matchmakeInterval) clearInterval(state.matchmakeInterval);
  addLog('Cancelled matchmaking.', 'info');
}

function onMatched(pkt) {
  state.roomId = pkt.room_id;
  saveSession();
  if (state.matchmakeInterval) clearInterval(state.matchmakeInterval);
  document.getElementById('matchmake-waiting').classList.add('hidden');
  const btn = document.getElementById('btn-matchmake');
  if (btn) btn.style.pointerEvents = '';

  toast(`Matched! Room: ${pkt.room_id} vs ${pkt.opponent}`, 'success');
  addLog(`Matched vs ${pkt.opponent} in room ${pkt.room_id}`, 'success');
}

// ── Rooms & Inline Forms ───────────────────────────────────────
function showSpectate() {
  hideInlineForms();
  const el = document.getElementById('form-spectate');
  if (el) { el.classList.remove('hidden'); el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
}
function showReplay() {
  hideInlineForms();
  const el = document.getElementById('form-replay');
  if (el) { el.classList.remove('hidden'); el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
}

function hideInlineForms() {
  ['form-spectate', 'form-replay'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  });
}

function onRoomJoined(pkt) {
  state.roomId = pkt.room_id;
  state.players = pkt.players || [];
  saveSession();
  
  document.getElementById('game-room-id').textContent = state.roomId;
  document.getElementById('game-vs-display').textContent = state.players.join(' ⚔ ') || 'Waiting...';
  
  const displayEl = document.getElementById('waiting-room-id-display');
  if (displayEl) {
    displayEl.innerHTML = `Room: <strong>${state.roomId}</strong>`;
  }
  
  document.getElementById('waiting-panel').classList.remove('hidden');
  document.getElementById('active-game').classList.add('hidden');
  showScreen('game');
  addLog(`Joined room ${pkt.room_id}`, 'success');
}

// ── Active Game Logic ──────────────────────────────────────────
function onStartGame(pkt) {
  state.players = pkt.players || [];
  state.qTotal = pkt.total_questions || 0;
  state.scores = {};
  state.hp = {};
  state.players.forEach(p => {
    state.scores[p] = 0;
    state.hp[p] = 100;
  });
  const isPlayer = state.players.includes(state.username);
  if (!isPlayer) {
    state.isSpectator = true;
    const p1 = state.players[0] || 'Player 1';
    const p2 = state.players[1] || 'Player 2';
    document.getElementById('spec-vs-display').textContent = `${p1} ⚔ ${p2}`;
    document.getElementById('spec-name-p1').textContent = p1;
    document.getElementById('spec-name-p2').textContent = p2;
    addLog(`Game started (Spectating)! ${p1} vs ${p2}`, 'success');
    return;
  }
  state.isSpectator = false;

  document.getElementById('game-room-id').textContent = state.roomId;
  const p1 = state.players[0] || 'Player 1';
  const p2 = state.players[1] || 'Player 2';
  document.getElementById('game-vs-display').textContent = `${p1} ⚔ ${p2}`;

  setupScoreBar(p1, p2);
  document.getElementById('game-activity').innerHTML = ''; // clear activity

  document.getElementById('waiting-panel').classList.add('hidden');
  document.getElementById('active-game').classList.remove('hidden');
  showScreen('game');

  addLog(`Game started! ${p1} vs ${p2}`, 'success');
  toast('Game started!', 'success');
  addGameActivity('Game Started!', 'sys');
}

function setupScoreBar(p1, p2) {
  const isP1 = state.username === p1;
  document.getElementById('pp-name-p1').textContent = p1;
  document.getElementById('pp-name-p2').textContent = p2;
  document.getElementById('pp-score-p1').textContent = '0';
  document.getElementById('pp-score-p2').textContent = '0';
  updateHPRender(p1, p2, 100, 100);

  const avatarP1 = document.getElementById('avatar-p1');
  const avatarP2 = document.getElementById('avatar-p2');
  if (avatarP1) avatarP1.textContent = p1.charAt(0).toUpperCase();
  if (avatarP2) avatarP2.textContent = p2.charAt(0).toUpperCase();

  const panelP1 = document.getElementById('panel-p1');
  const panelP2 = document.getElementById('panel-p2');
  if (panelP1) panelP1.classList.toggle('you', isP1);
  if (panelP2) panelP2.classList.toggle('you', !isP1);
}

function onQuestion(pkt) {
  if (state.isSpectator) {
    onSpectateQuestion(pkt);
    return;
  }
  state.qIndex = pkt.index ?? 0;
  state.qTotal = pkt.total ?? state.qTotal;
  state.qData = pkt.question || {};
  state.timeLimit = pkt.time_limit ?? 20;
  state.qReceivedAt = Date.now();
  state.answered = false;
  state.locked = false;

  renderQuestion(state.qData);
  document.getElementById('q-counter').textContent = `Q ${state.qIndex + 1}/${state.qTotal}`;
  document.getElementById('answer-feedback').classList.add('hidden');
  document.getElementById('opponent-status').textContent = '';

  ['A', 'B', 'C', 'D'].forEach(k => {
    const btn = document.getElementById('choice-' + k);
    if (btn) {
      btn.className = 'choice-btn';
      btn.disabled = false;
    }
  });

  startTimer();
  addLog(`Question ${state.qIndex + 1}: ${(state.qData.question || '').slice(0, 50)}...`, 'info');
  addGameActivity(`Question ${state.qIndex + 1} started`, 'sys');
}

function renderQuestion(q) {
  document.getElementById('q-category').textContent = q.category || '—';
  document.getElementById('q-text').textContent = q.question || '';
  document.getElementById('q-num-badge').textContent = `Q${state.qIndex + 1}`;
  
  const choices = q.choices || {};
  ['A', 'B', 'C', 'D'].forEach(k => {
    const el = document.getElementById('choice-text-' + k);
    if (el) el.textContent = choices[k] || '';
  });
}

function submitAnswer(key) {
  if (state.answered || state.locked) return;
  state.answered = true;
  
  const btn = document.getElementById('choice-' + key);
  if (btn) btn.classList.add('selected');
  
  ['A', 'B', 'C', 'D'].forEach(k => {
    const b = document.getElementById('choice-' + k);
    if (b) b.disabled = true;
  });

  sendWS({
    type: 'SUBMIT_ANSWER',
    username: state.username,
    room_id: state.roomId,
    question_index: state.qIndex,
    answer: key
  });
}

function onAnswerResult(pkt) {
  if (state.isSpectator) {
    onSpectateAnswerResult(pkt);
    return;
  }
  const { username, correct, points } = pkt;
  state.scores = pkt.scores || state.scores;
  state.hp = pkt.hp || state.hp;

  if (username === state.username) {
    const fb = document.getElementById('answer-feedback');
    fb.classList.remove('hidden', 'correct', 'wrong', 'locked');
    
    if (correct) {
      fb.classList.add('correct');
      fb.textContent = `✅ Benar! +${points} poin`;
      state.locked = true;
      addGameActivity(`You answered correctly! (+${points})`, 'correct');
      
      // Highlight correctly answered button
      ['A', 'B', 'C', 'D'].forEach(k => {
        const b = document.getElementById('choice-' + k);
        if (b && b.classList.contains('selected')) {
          b.classList.remove('selected');
          b.classList.add('correct');
        }
      });
    } else {
      fb.classList.add('wrong');
      fb.textContent = '❌ Salah! -10 HP. Coba lagi...';
      state.answered = false;
      addGameActivity(`You answered wrong. (-10 HP)`, 'wrong');
      
      // Highlight wrong answer, re-enable other options
      ['A', 'B', 'C', 'D'].forEach(k => {
        const b = document.getElementById('choice-' + k);
        if (b) {
          if (b.classList.contains('selected')) {
            b.classList.remove('selected');
            b.classList.add('wrong');
          } else if (!b.classList.contains('wrong')) {
            b.disabled = false;
          }
        }
      });
    }
  } else {
    // Result for the opponent
    if (correct) {
      state.locked = true;
      document.getElementById('opponent-status').textContent = `${username} menjawab benar — pertanyaan terkunci!`;
      addGameActivity(`${username} answered correctly!`, 'correct');
      
      const fb = document.getElementById('answer-feedback');
      fb.classList.remove('hidden', 'correct', 'wrong');
      fb.classList.add('locked');
      fb.textContent = `🔒 ${username} menjawab benar. Menunggu soal berikutnya...`;
      
      ['A', 'B', 'C', 'D'].forEach(k => {
        const b = document.getElementById('choice-' + k);
        if (b) b.disabled = true;
      });
    } else {
      document.getElementById('opponent-status').textContent = `${username} menjawab salah.`;
      addGameActivity(`${username} answered wrong.`, 'wrong');
    }
  }

  updateScoreDisplay();
}

function onGameState(pkt) {
  state.scores = pkt.scores || state.scores;
  state.hp = pkt.hp || state.hp;
  if (pkt.latencies) {
    state.latencies = pkt.latencies;
  }
  updateScoreDisplay();
}

// ── Voice Chat (WebRTC peer-to-peer audio) ─────────────────────
let _rtcPeer = null;         // RTCPeerConnection
let _localStream = null;     // MediaStream from getUserMedia
let _voiceMuted = false;

const RTC_CONFIG = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
  ]
};

function _sendSignal(signalType, data) {
  if (!state.roomId || !state.username) return;
  sendWS({
    type: 'VOICE_SIGNAL',
    username: state.username,
    room_id: state.roomId,
    signal_type: signalType,
    data: data
  });
}

async function _createPeer(initiator) {
  _closePeer();

  _rtcPeer = new RTCPeerConnection(RTC_CONFIG);

  // Add local audio tracks
  if (_localStream) {
    _localStream.getTracks().forEach(t => _rtcPeer.addTrack(t, _localStream));
  }

  // ICE candidate → relay through server
  _rtcPeer.onicecandidate = (e) => {
    if (e.candidate) {
      _sendSignal('ice-candidate', e.candidate.toJSON());
    }
  };

  _rtcPeer.onconnectionstatechange = () => {
    const s = _rtcPeer?.connectionState;
    console.log('[VOICE] connection state:', s);
    const btn = document.getElementById('btn-mic');
    if (s === 'connected') {
      toast('🎙 Voice chat connected!', 'success', 3000);
      addLog('Voice chat: peer connected', 'success');
      if (btn) btn.title = 'Voice chat connected';
    } else if (s === 'disconnected' || s === 'failed') {
      toast('Voice chat disconnected', 'warn', 3000);
      if (btn) btn.title = 'Voice chat disconnected';
    }
  };

  // Play remote audio when tracks arrive
  _rtcPeer.ontrack = (e) => {
    console.log('[VOICE] remote track received');
    let remoteAudio = document.getElementById('_voice_remote_audio');
    if (!remoteAudio) {
      remoteAudio = document.createElement('audio');
      remoteAudio.id = '_voice_remote_audio';
      remoteAudio.autoplay = true;
      remoteAudio.style.display = 'none';
      document.body.appendChild(remoteAudio);
    }
    remoteAudio.srcObject = e.streams[0];
  };

  if (initiator) {
    // Create and send offer
    const offer = await _rtcPeer.createOffer({ offerToReceiveAudio: true });
    await _rtcPeer.setLocalDescription(offer);
    _sendSignal('offer', { sdp: offer.sdp, type: offer.type });
    addLog('Voice chat: sent offer to peer', 'info');
  }
}

async function _handleVoiceSignal(pkt) {
  const { signal_type, data, from_user } = pkt;
  console.log('[VOICE] signal from', from_user, ':', signal_type);

  if (signal_type === 'offer') {
    // Someone is calling us — create peer as non-initiator
    if (!_localStream) {
      addLog('Voice chat: received call but mic is off', 'warn');
      return;
    }
    await _createPeer(false);
    await _rtcPeer.setRemoteDescription(new RTCSessionDescription(data));
    const answer = await _rtcPeer.createAnswer();
    await _rtcPeer.setLocalDescription(answer);
    _sendSignal('answer', { sdp: answer.sdp, type: answer.type });
    addLog(`Voice chat: answered call from ${from_user}`, 'info');

  } else if (signal_type === 'answer') {
    if (!_rtcPeer) return;
    await _rtcPeer.setRemoteDescription(new RTCSessionDescription(data));

  } else if (signal_type === 'ice-candidate') {
    if (!_rtcPeer) return;
    try {
      await _rtcPeer.addIceCandidate(new RTCIceCandidate(data));
    } catch (e) {
      console.warn('[VOICE] ICE candidate error:', e);
    }

  } else if (signal_type === 'hangup') {
    _closePeer();
    toast(`${from_user} ended voice chat`, 'info', 3000);
    addLog(`Voice chat ended by ${from_user}`, 'info');
  }
}

function _closePeer() {
  if (_rtcPeer) {
    _rtcPeer.close();
    _rtcPeer = null;
  }
  const remoteAudio = document.getElementById('_voice_remote_audio');
  if (remoteAudio) remoteAudio.srcObject = null;
}

async function toggleMic() {
  const btn = document.getElementById('btn-mic');
  state.micEnabled = !state.micEnabled;

  if (state.micEnabled) {
    // Step 1: get microphone access
    try {
      _localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch (e) {
      state.micEnabled = false;
      toast('Microphone access denied. Please allow it in your browser.', 'error', 5000);
      addLog('Mic error: ' + e.message, 'error');
      return;
    }

    if (btn) {
      btn.textContent = '🎙 Mic: On';
      btn.classList.add('btn-primary');
      btn.classList.remove('btn-outline');
    }
    toast('🎙 Voice chat ON — calling other players...', 'success', 3000);
    addLog('Voice chat started. Connecting to peers...', 'info');

    // Step 2: initiate WebRTC as the caller
    await _createPeer(true);

  } else {
    // Hang up
    _sendSignal('hangup', {});
    _closePeer();

    if (_localStream) {
      _localStream.getTracks().forEach(t => t.stop());
      _localStream = null;
    }

    if (btn) {
      btn.textContent = '🎙 Mic: Off';
      btn.classList.add('btn-outline');
      btn.classList.remove('btn-primary');
    }
    toast('Voice chat ended', 'info');
    addLog('Voice chat stopped', 'info');
  }
}


function updateScoreDisplay() {
  const p1 = state.players[0];
  const p2 = state.players[1];
  
  if (p1) {
    const s1 = document.getElementById('pp-score-p1') || document.getElementById('spec-val-p1');
    if (s1) animateScoreChange(s1, state.scores[p1] ?? 0);
  }
  if (p2) {
    const s2 = document.getElementById('pp-score-p2') || document.getElementById('spec-val-p2');
    if (s2) animateScoreChange(s2, state.scores[p2] ?? 0);
  }

  if (!state.isSpectator && p1 && p2) {
    updateHPRender(p1, p2, state.hp[p1] ?? 0, state.hp[p2] ?? 0);
  } else if (state.isSpectator && p1 && p2) {
    updateHPRenderSpec(p1, p2, state.hp[p1] ?? 0, state.hp[p2] ?? 0);
  }

  // Latency display
  if (state.latencies && !state.isSpectator) {
    const s1 = document.getElementById('pp-status-p1');
    const s2 = document.getElementById('pp-status-p2');
    if (s1 && !s1.textContent.includes('Disconnected') && state.latencies[p1] !== undefined) {
      s1.textContent = `Connected (${Math.round(state.latencies[p1])}ms)`;
    }
    if (s2 && !s2.textContent.includes('Disconnected') && state.latencies[p2] !== undefined) {
      s2.textContent = `Connected (${Math.round(state.latencies[p2])}ms)`;
    }
  } else if (state.latencies && state.isSpectator) {
    const sn1 = document.getElementById('spec-name-p1');
    const sn2 = document.getElementById('spec-name-p2');
    if (sn1 && state.latencies[p1] !== undefined) sn1.textContent = `${p1} (${Math.round(state.latencies[p1])}ms)`;
    if (sn2 && state.latencies[p2] !== undefined) sn2.textContent = `${p2} (${Math.round(state.latencies[p2])}ms)`;
  }
}

function animateScoreChange(el, newScore) {
  const current = parseInt(el.textContent) || 0;
  if (current !== newScore) {
    el.textContent = newScore;
    el.style.transform = 'scale(1.2)';
    setTimeout(() => { el.style.transform = 'scale(1)'; }, 200);
  }
}

function updateHPRender(p1, p2, hp1, hp2) {
  _applyHP('hp-fill-p1', 'hp-val-p1', hp1);
  _applyHP('hp-fill-p2', 'hp-val-p2', hp2);
}

function updateHPRenderSpec(p1, p2, hp1, hp2) {
  _applyHP('spec-hp-fill-p1', 'spec-hp-val-p1', hp1);
  _applyHP('spec-hp-fill-p2', 'spec-hp-val-p2', hp2);
}

function _applyHP(fillId, valId, hp) {
  const fill = document.getElementById(fillId);
  const val = document.getElementById(valId);
  if (!fill || !val) return;

  const safeHp = Math.max(0, Math.min(100, hp));
  fill.style.width = safeHp + '%';
  val.textContent = safeHp + ' HP';

  if (safeHp > 60) fill.style.backgroundColor = 'var(--success)';
  else if (safeHp > 30) fill.style.backgroundColor = 'var(--warning)';
  else fill.style.backgroundColor = 'var(--error)';
}

function addGameActivity(msg, type) {
  const feed = document.getElementById('game-activity');
  if (!feed) return;
  const div = document.createElement('div');
  div.className = `ga-event ${type}`;
  div.textContent = msg;
  feed.prepend(div);
}

// ── Timer Circular Logic ──────────────────────────────────────
const CIRCUMFERENCE = 188; // 2 * pi * 30

function handleTimerExpired() {
  // Called when client-side timer hits 0. Server will auto-advance to next question.
  // Show visual feedback to indicate time ran out.
  if (!state.isSpectator && !state.locked) {
    const fb = document.getElementById('answer-feedback');
    if (fb) {
      fb.classList.remove('hidden', 'correct', 'wrong', 'locked');
      fb.classList.add('wrong');
      fb.textContent = '⏰ Time\'s up! Moving to next question...';
    }
    // Disable all buttons
    ['A', 'B', 'C', 'D'].forEach(k => {
      const b = document.getElementById('choice-' + k);
      if (b) b.disabled = true;
    });
    state.locked = true;
    addGameActivity('Time\'s up!', 'warn');
  }
}

function startTimer() {
  stopTimer();
  const arc = document.getElementById('timer-arc');
  const text = document.getElementById('timer-text');
  let expired = false;
  
  state.timerInterval = setInterval(() => {
    const elapsed = (Date.now() - state.qReceivedAt) / 1000;
    const remaining = Math.max(0, state.timeLimit - elapsed);
    const pct = remaining / state.timeLimit;
    
    if (arc) {
      arc.style.strokeDashoffset = CIRCUMFERENCE * (1 - pct);
      if (pct > 0.5) arc.style.stroke = 'var(--primary)';
      else if (pct > 0.25) arc.style.stroke = 'var(--warning)';
      else arc.style.stroke = 'var(--error)';
    }
    
    if (text) {
      text.textContent = Math.ceil(remaining);
    }

    if (remaining <= 0 && !expired) {
      expired = true;
      stopTimer();
      handleTimerExpired();
    }
  }, 100);
}

function stopTimer() {
  if (state.timerInterval) {
    clearInterval(state.timerInterval);
    state.timerInterval = null;
  }
  const arc = document.getElementById('timer-arc');
  if (arc) {
    arc.style.strokeDashoffset = 0;
    arc.style.stroke = 'var(--primary)';
  }
}

// ── Game Over Screen ───────────────────────────────────────────
function onGameOver(pkt) {
  stopTimer();
  // Save the room ID so the "View Replay" button works even after returning to lobby
  if (state.roomId) state.lastRoomId = state.roomId;
  const { winner, scores, reason } = pkt;
  const isWinner = winner === state.username;
  const isDraw = !winner;

  const trophyEl = document.getElementById('gameover-emoji');
  const titleEl = document.getElementById('gameover-title');
  const resEl = document.getElementById('gameover-result');

  if (isDraw) {
    trophyEl.textContent = '🤝';
    titleEl.textContent = 'BATTLE DRAW';
    resEl.textContent = 'No winner in this duel.';
  } else if (isWinner) {
    trophyEl.textContent = '🏆';
    titleEl.textContent = 'VICTORY!';
    resEl.textContent = reason === 'hp_depleted' ? `You knocked out the opponent!` : `You won by score!`;
    startConfetti();
  } else {
    trophyEl.textContent = '💔';
    titleEl.textContent = 'DEFEAT';
    resEl.textContent = reason === 'hp_depleted' ? `You were knocked out!` : `${winner} won by score!`;
  }

  const scoresList = Object.entries(scores || {}).sort((a, b) => b[1] - a[1]);
  const finalScores = document.getElementById('final-scores');
  if (finalScores) {
    finalScores.innerHTML = scoresList.map(([p, pts]) => `
      <div class="score-row">
        <span>${p === state.username ? '★ ' : ''}${p}</span>
        <span class="pts">${pts} pts</span>
      </div>
    `).join('');
  }

  showScreen('gameover');
  addLog(`Game Over. Winner: ${winner || 'Draw'}`, 'warn');
  
  setTimeout(() => {
    fetchRanking();
    fetchRooms();
  }, 2000);
}

function returnToLobby() {
  state.roomId = '';
  state.qData = null;
  state.answered = false;
  state.locked = false;
  state.isSpectator = false;
  state.players = [];
  stopTimer();
  clearSession();
  showScreen('lobby');
}

// ── Spectate Logic ─────────────────────────────────────────────
function doSpectate() {
  const roomId = document.getElementById('input-spectate-id').value.trim().toUpperCase();
  if (!roomId) return;
  state.roomId = roomId;
  state.isSpectator = true;
  sendWS({ type: 'SPECTATE', username: state.username, room_id: roomId });
  hideInlineForms();
  addLog(`Requesting spectate for room ${roomId}...`, 'info');
}

function onSpectateOk(pkt) {
  document.getElementById('spec-room-id').textContent = pkt.room_id;
  const snap = pkt.game_state || {};
  state.players = snap.players || [];
  
  const p1 = state.players[0] || 'Player 1';
  const p2 = state.players[1] || 'Player 2';
  document.getElementById('spec-vs-display').textContent = `${p1} vs ${p2}`;
  
  document.getElementById('spec-name-p1').textContent = p1;
  document.getElementById('spec-name-p2').textContent = p2;
  
  const avatarP1 = document.getElementById('spec-avatar-p1');
  const avatarP2 = document.getElementById('spec-avatar-p2');
  if (avatarP1) avatarP1.textContent = p1.charAt(0).toUpperCase();
  if (avatarP2) avatarP2.textContent = p2.charAt(0).toUpperCase();

  const scores = snap.scores || {};
  document.getElementById('spec-val-p1').textContent = scores[p1] ?? 0;
  document.getElementById('spec-val-p2').textContent = scores[p2] ?? 0;

  const hps = snap.hp || { [p1]: 100, [p2]: 100 };
  updateHPRenderSpec(p1, p2, hps[p1], hps[p2]);

  document.getElementById('spec-event-feed').innerHTML = '';
  showScreen('spectate');
  addLog(`Spectating room ${pkt.room_id}`, 'success');

  if (snap.current_question) {
    onSpectateQuestion({
      index: snap.question_index,
      total: snap.total_questions,
      question: snap.current_question,
      time_limit: snap.time_remaining || 20
    });
  }
}

function onSpectateFail(pkt) {
  state.isSpectator = false;
  toast('Failed to spectate: ' + (pkt.reason || 'Unknown'), 'error');
  addLog('Spectate failed: ' + pkt.reason, 'error');
}

function stopSpectating() {
  state.isSpectator = false;
  if (state.specTimerInterval) {
    clearInterval(state.specTimerInterval);
    state.specTimerInterval = null;
  }
  showScreen('lobby');
}

function onSpectateQuestion(pkt) {
  state.qIndex = pkt.index ?? 0;
  state.qTotal = pkt.total ?? state.qTotal;
  const q = pkt.question || {};
  state.timeLimit = pkt.time_limit ?? 20;
  state.qReceivedAt = Date.now();

  document.getElementById('spec-category').textContent = q.category || '—';
  document.getElementById('spec-q-text').textContent = q.question || '';
  document.getElementById('spec-q-counter').textContent = `Q ${state.qIndex + 1}/${state.qTotal}`;
  
  const choices = q.choices || {};
  ['A', 'B', 'C', 'D'].forEach(k => {
    const txtEl = document.getElementById('spec-text-' + k);
    if (txtEl) txtEl.textContent = choices[k] || '';
    
    const btn = document.getElementById('spec-' + k);
    if (btn) btn.className = 'choice-btn view-only';
  });

  // Start Spectator Timer Animation
  if (state.specTimerInterval) clearInterval(state.specTimerInterval);
  const arc = document.getElementById('spec-timer-arc');
  const text = document.getElementById('spec-timer-text');
  let specExpired = false;
  
  state.specTimerInterval = setInterval(() => {
    const elapsed = (Date.now() - state.qReceivedAt) / 1000;
    const remaining = Math.max(0, state.timeLimit - elapsed);
    const pct = remaining / state.timeLimit;
    
    if (arc) {
      arc.style.strokeDashoffset = CIRCUMFERENCE * (1 - pct);
      if (pct > 0.5) arc.style.stroke = 'var(--primary)';
      else if (pct > 0.25) arc.style.stroke = 'var(--warning)';
      else arc.style.stroke = 'var(--error)';
    }
    if (text) text.textContent = Math.ceil(remaining);
    
    if (remaining <= 0 && !specExpired) {
      specExpired = true;
      clearInterval(state.specTimerInterval);
      state.specTimerInterval = null;
      // Visual feedback for spectators
      const feed = document.getElementById('spec-event-feed');
      if (feed) {
        const evDiv = document.createElement('div');
        evDiv.className = 'ga-event warn';
        evDiv.textContent = '⏰ Time\'s up! Next question incoming...';
        feed.prepend(evDiv);
      }
    }
  }, 100);

  const feed = document.getElementById('spec-event-feed');
  if (feed) {
    const evDiv = document.createElement('div');
    evDiv.className = 'ga-event sys';
    evDiv.textContent = `Question ${state.qIndex + 1} started.`;
    feed.prepend(evDiv);
  }
}

function onSpectateAnswerResult(pkt) {
  const { username, correct, points } = pkt;
  state.scores = pkt.scores || state.scores;
  state.hp = pkt.hp || state.hp;
  updateScoreDisplay();

  const feed = document.getElementById('spec-event-feed');
  if (feed) {
    const evDiv = document.createElement('div');
    evDiv.className = `ga-event ${correct ? 'correct' : 'wrong'}`;
    evDiv.textContent = `${username} answered: ${correct ? 'Correct' : 'Incorrect'} (+${points})`;
    feed.prepend(evDiv);
  }
}

// ── Reconnect Logic ────────────────────────────────────────────

function onReconnectOk(pkt) {
  state.roomId = pkt.room_id;
  const snap = pkt.game_state || {};
  state.scores = snap.scores || {};
  state.hp = snap.hp || {};
  state.qIndex = snap.question_index ?? 0;
  state.players = snap.players || state.players;
  saveSession();

  toast(`Reconnected successfully to room ${state.roomId}!`, 'success');
  addLog('Reconnected successfully!', 'success');

  document.getElementById('game-room-id').textContent = state.roomId;
  if (state.players.length >= 2) {
    document.getElementById('game-vs-display').textContent = `${state.players[0]} ⚔ ${state.players[1]}`;
    setupScoreBar(state.players[0], state.players[1]);
  }
  
  updateScoreDisplay();
  document.getElementById('waiting-panel').classList.add('hidden');
  document.getElementById('active-game').classList.remove('hidden');
  showScreen('game');
}

function onReconnectFail(pkt) {
  toast('Reconnect failed: ' + (pkt.reason || 'Unknown'), 'error');
  addLog('Reconnect failed: ' + pkt.reason, 'error');
}

// ── Replay Logic ───────────────────────────────────────────────
function doFetchReplay() {
  const roomId = document.getElementById('input-replay-id').value.trim().toUpperCase();
  if (!roomId) { toast('Enter a Room ID first.', 'warn'); return; }
  toast('Loading replay...', 'info', 2000);
  addLog(`Fetching replay for room ${roomId}...`, 'info');
  sendWS({ type: 'GET_REPLAY', room_id: roomId });
  hideInlineForms();
}

function _escHtml(str) {
  // Safely escape text before inserting into innerHTML
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function onReplay(pkt) {
  console.log('[REPLAY] packet received:', pkt);
  const roomId = pkt.room_id;
  const events = pkt.events || [];

  try {
    const roomIdEl = document.getElementById('replay-room-id');
    if (roomIdEl) roomIdEl.textContent = roomId;

    const timeline = document.getElementById('replay-timeline');
    const summary  = document.getElementById('replay-summary');

    if (!events.length) {
      if (timeline) timeline.innerHTML = '<div class="empty-state">No events recorded for this match.</div>';
      if (summary)  summary.innerHTML  = '';
      showScreen('replay');
      return;
    }

    let players = [];
    let finalScores = {};
    let winner = 'Draw';
    let totalQuestions = 0;

    const rows = events.map(ev => {
      // Format timestamp to [YYYY-MM-DD HH:mm:ss]
      const d = new Date((ev.ts || Date.now() / 1000) * 1000);
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mn = String(d.getMinutes()).padStart(2, '0');
      const ss = String(d.getSeconds()).padStart(2, '0');
      const timeStr = `[${yyyy}-${mm}-${dd} ${hh}:${mn}:${ss}]`;

      const etype = String(ev.event).toUpperCase().padEnd(10, ' ');
      let detailText = '';

      if (ev.event === 'GAME_START') {
        players = ev.players || [];
        detailText = `room=${roomId}  players=${players.join(', ')}`;
      } else if (ev.event === 'QUESTION') {
        totalQuestions++;
        detailText = `room=${roomId}  q=${ev.index ?? 0} text="${ev.question_text || ''}"`;
      } else if (ev.event === 'ANSWER') {
        const u = `user='${ev.username}'`.padEnd(25, ' ');
        const r = `room=${roomId}`.padEnd(15, ' ');
        const q = `q=${ev.question_index ?? 0}`.padEnd(5, ' ');
        const c = (ev.correct ? 'CORRECT' : 'WRONG').padEnd(9, ' ');
        const p = `pts=+${ev.points ?? 0}`;
        detailText = `${u}  ${r} ${q} ${c} ${p}`;
      } else if (ev.event === 'TIMEOUT') {
        detailText = `room=${roomId}  q=${ev.question_index ?? 0}  TIMEOUT`;
      } else if (ev.event === 'GAME_OVER') {
        finalScores = ev.scores || {};
        winner = ev.winner || 'Draw';
        detailText = `room=${roomId}  winner=${winner} reason=${ev.reason || 'unknown'}`;
      } else if (ev.event === 'DISCONNECT') {
        detailText = `user='${ev.username}' disconnected`;
      } else if (ev.event === 'RECONNECT') {
        detailText = `user='${ev.username}' reconnected`;
      }

      return `${timeStr} INFO     ${etype} | ${detailText}`;
    });

    const logOutput = `<div style="background:#111; color:#0f0; font-family:monospace; padding:16px; border-radius:8px; overflow-x:auto; white-space:pre; line-height:1.5;">${_escHtml(rows.join('\n'))}</div>`;
    
    if (timeline) timeline.innerHTML = logOutput;

    const vsEl = document.getElementById('replay-vs-display');
    if (vsEl) vsEl.textContent = players.join(' vs ') || 'Replay';

    if (summary) {
      summary.innerHTML = `
        <div style="font-weight:600;font-size:1.1rem;margin-bottom:12px;">📋 Summary</div>
        <div style="font-size:0.9rem;display:flex;flex-direction:column;gap:8px;">
          <div>Room: <strong>${_escHtml(roomId)}</strong></div>
          <div>Questions: <strong>${totalQuestions}</strong></div>
          <div>Winner: <strong style="color:var(--success)">${_escHtml(winner)}</strong></div>
          <div style="margin-top:8px;font-weight:600;">Final Scores:</div>
          ${Object.entries(finalScores).map(([p, pts]) => `
            <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);">
              <span>${_escHtml(p)}</span>
              <span style="font-family:var(--font-mono);font-weight:600;color:var(--primary);">${pts} pts</span>
            </div>
          `).join('')}
        </div>
      `;
    }

    showScreen('replay');
    addLog(`Loaded replay for room ${roomId} (${events.length} events)`, 'success');
    toast('Replay loaded!', 'success', 2000);

  } catch (err) {
    console.error('[REPLAY] render error:', err);
    toast('Failed to render replay: ' + err.message, 'error', 5000);
    addLog('Replay render error: ' + err.message, 'error');
  }
}

function stopReplay() {
  showScreen('lobby');
}

function viewCurrentReplay() {
  const roomId = state.roomId || state.lastRoomId;
  console.log('[REPLAY] viewCurrentReplay — roomId:', roomId, 'lastRoomId:', state.lastRoomId, 'ws:', state.ws?.readyState);
  if (!roomId) {
    toast('No recent room to replay.', 'error');
    return;
  }
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    toast('Not connected to server.', 'error');
    return;
  }
  toast('Loading replay...', 'info', 2000);
  addLog(`Fetching replay for room ${roomId}...`, 'info');
  // Small delay to ensure replay file is fully written server-side
  setTimeout(() => {
    console.log('[REPLAY] sending GET_REPLAY for', roomId);
    sendWS({ type: 'GET_REPLAY', room_id: roomId });
  }, 1200);
}

// ── Ranking Data ───────────────────────────────────────────────
function fetchRanking() {
  sendWS({ type: 'GET_RANKING' });
}

function onRanking(pkt) {
  const entries = pkt.entries || [];
  const container = document.getElementById('rank-list');
  if (!container) return;

  if (!entries.length) {
    container.innerHTML = '<div class="empty-state">No rankings available yet.</div>';
    return;
  }

  container.innerHTML = entries.map(e => {
    const isMe = e.username === state.username;
    const itemStyle = isMe ? 'border-color:var(--primary);background:var(--primary-light);' : '';
    return `
      <div class="rank-item" style="${itemStyle}">
        <span class="rank-pos">${e.rank || '?'}</span>
        <span class="rank-username">${isMe ? '★ ' : ''}${e.username}</span>
        <span class="rank-elo">${e.elo} ELO</span>
        <span class="rank-wl">${e.wins}W / ${e.losses}L</span>
      </div>
    `;
  }).join('');
}

// ── Rooms List ─────────────────────────────────────────────────
function fetchRooms() {
  sendWS({ type: 'LIST_ROOMS' });
}

function onRoomsList(pkt) {
  const rooms = pkt.rooms || [];
  const el = document.getElementById('rooms-list');
  if (!el) return;

  if (!rooms.length) {
    el.innerHTML = '<div class="empty-state">No active rooms found.</div>';
    return;
  }

  el.innerHTML = rooms.map(r => `
    <div class="room-card">
      <div>
        <div class="room-id-label">${r.room_id}</div>
        <div class="room-players">${(r.players || []).join(' vs ') || '—'}</div>
      </div>
      <span class="room-status ${r.status || 'waiting'}">${r.status || 'waiting'}</span>
    </div>
  `).join('');
}

// ── Presence events ────────────────────────────────────────────
function onPlayerDisconnected(pkt) {
  toast(`${pkt.username} disconnected. Waiting for reconnect...`, 'warn', 5000);
  addLog(`${pkt.username} disconnected.`, 'warn');
  const p1 = state.players[0];
  const p2 = state.players[1];
  if (pkt.username === p1) document.getElementById('pp-status-p1').textContent = 'Disconnected';
  if (pkt.username === p2) document.getElementById('pp-status-p2').textContent = 'Disconnected';
}

function onPlayerReconnected(pkt) {
  toast(`${pkt.username} reconnected!`, 'success');
  addLog(`${pkt.username} reconnected.`, 'success');
  const p1 = state.players[0];
  const p2 = state.players[1];
  if (pkt.username === p1) document.getElementById('pp-status-p1').textContent = 'Connected';
  if (pkt.username === p2) document.getElementById('pp-status-p2').textContent = 'Connected';
}

// ── Tab Management ─────────────────────────────────────────────
function switchTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
  
  if (btn) btn.classList.add('active');
  const panel = document.getElementById('tab-' + name);
  if (panel) panel.classList.remove('hidden');

  if (name === 'ranking') fetchRanking();
  if (name === 'rooms') fetchRooms();
}

// ── Packet Router (Dispatcher) ─────────────────────────────────
const handlers = {
  LOGIN_OK: onLoginOk,
  LOGIN_FAIL: onLoginFail,
  MATCHED: onMatched,
  ROOM_JOINED: onRoomJoined,
  SPECTATE_OK: onSpectateOk,
  SPECTATE_FAIL: onSpectateFail,
  START_GAME: onStartGame,
  QUESTION: onQuestion,
  ANSWER_RESULT: onAnswerResult,
  GAME_STATE: onGameState,
  GAME_OVER: onGameOver,
  PONG: onPong,
  RECONNECT_OK: onReconnectOk,
  RECONNECT_FAIL: onReconnectFail,
  RANKING: onRanking,
  REPLAY: onReplay,
  ROOMS_LIST: onRoomsList,
  PLAYER_DISCONNECTED: onPlayerDisconnected,
  PLAYER_RECONNECTED: onPlayerReconnected,
  VOICE_SIGNAL: (pkt) => _handleVoiceSignal(pkt),

  ERROR: onServerError,
  INVALID_PACKET: onServerError,
  SERVER_DISCONNECTED: onServerDisconnected
};

function dispatch(pkt) {
  const fn = handlers[pkt.type];
  if (fn) {
    fn(pkt);
  }
}

function onLoginOk(pkt) {
  state.username = pkt.username;
  const hdrUsername = document.getElementById('hdr-username');
  if (hdrUsername) hdrUsername.textContent = state.username;
  const statEl = document.getElementById('connect-status');
  if (statEl) statEl.classList.add('hidden');
  const errEl = document.getElementById('connect-error');
  if (errEl) errEl.classList.add('hidden');
  const btnConnect = document.getElementById('btn-connect');
  if (btnConnect) btnConnect.disabled = false;
  
  startPing();
  fetchRanking();
  fetchRooms();
  saveSession();

  if (isReconnecting) {
    isReconnecting = false;
    toast('Reconnected to server!', 'success');
    addLog('Reconnected to server.', 'success');
    
    if (state.roomId && !state.isSpectator) {
      sendWS({ type: 'RECONNECT', username: state.username, room_id: state.roomId });
    } else if (state.roomId && state.isSpectator) {
      sendWS({ type: 'SPECTATE', username: state.username, room_id: state.roomId });
    } else {
      showScreen('lobby');
    }
  } else {
    showScreen('lobby');
    addLog(`Logged in successfully as "${state.username}"`, 'success');
    toast(`Welcome to the Arena, ${state.username}!`, 'success');
  }
}

function onLoginFail(pkt) {
  const errEl = document.getElementById('connect-error');
  errEl.textContent = 'Login failed: ' + (pkt.reason || 'Unknown');
  errEl.classList.remove('hidden');
  document.getElementById('connect-status').classList.add('hidden');
  document.getElementById('btn-connect').disabled = false;
  state.ws = null;
}

function onServerError(pkt) {
  const msg = pkt.message || pkt.reason || 'Unknown error occurred';
  toast('Server Error: ' + msg, 'error');
  addLog('Error: ' + msg, 'error');
}

function onServerDisconnected(pkt) {
  toast(pkt.message || 'Server connection terminated', 'error');
  doLogout();
}

// ── Confetti Particle System ───────────────────────────────────
function startConfetti() {
  const canvas = document.getElementById('confetti-canvas');
  if (!canvas) return;
  
  const ctx = canvas.getContext('2d');
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  
  const colors = ['#2563EB', '#38BDF8', '#22C55E', '#F59E0B', '#8B5CF6'];
  const particles = [];

  for (let i = 0; i < 120; i++) {
    particles.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height - canvas.height,
      r: Math.random() * 6 + 4,
      d: Math.random() * canvas.height,
      color: colors[Math.floor(Math.random() * colors.length)],
      tilt: Math.random() * 10 - 5,
      tiltAngleIncremental: Math.random() * 0.07 + 0.02,
      tiltAngle: 0
    });
  }

  let animationFrameId;
  const startTime = Date.now();

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    let active = false;
    particles.forEach(p => {
      p.tiltAngle += p.tiltAngleIncremental;
      p.y += (Math.cos(p.d) + 3 + p.r / 2) / 2;
      p.x += Math.sin(p.tiltAngle);
      p.tilt = Math.sin(p.tiltAngle - p.r / 2) * 4;

      if (p.y < canvas.height) {
        active = true;
      }

      ctx.beginPath();
      ctx.lineWidth = p.r;
      ctx.strokeStyle = p.color;
      ctx.moveTo(p.x + p.tilt + p.r / 2, p.y);
      ctx.lineTo(p.x + p.tilt, p.y + p.tilt + p.r / 2);
      ctx.stroke();
    });

    // Run for 4 seconds
    if (active && Date.now() - startTime < 4000) {
      animationFrameId = requestAnimationFrame(draw);
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      cancelAnimationFrame(animationFrameId);
    }
  }

  draw();
  
  window.addEventListener('resize', () => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  });
}

// ── Keyboard Shortcuts & Event Binding ────────────────────────
document.addEventListener('keydown', (e) => {
  const activeScreen = document.querySelector('.screen.active');
  if (!activeScreen) return;

  if (activeScreen.id === 'screen-connect' && e.key === 'Enter') {
    doConnect();
  }

  if (activeScreen.id === 'screen-game' && !state.answered && !state.locked && state.qData) {
    const key = e.key.toUpperCase();
    if (['A', 'B', 'C', 'D'].includes(key)) {
      submitAnswer(key);
    }
  }
});

// ── Initialize Input Event ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const usernameInput = document.getElementById('input-username');
  if (usernameInput) {
    usernameInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') doConnect();
    });
  }

  // ── Session Restore on Page Load ────────────────────────────
  // If a saved session exists, pre-fill the form and auto-reconnect.
  const session = loadSession();
  if (session && session.username) {
    // Pre-fill fields
    const serverInput = document.getElementById('input-server');
    if (serverInput && session.serverUrl) serverInput.value = session.serverUrl;
    const unInput = document.getElementById('input-username');
    if (unInput) unInput.value = session.username;

    // Restore state that was active before refresh
    state.username    = session.username;
    state.roomId      = session.roomId || '';
    state.isSpectator = session.isSpectator || false;

    // Mark as reconnecting so onLoginOk will trigger RECONNECT/SPECTATE
    isReconnecting = true;

    toast('Restoring session...', 'info', 3000);
    doConnect({ serverUrl: session.serverUrl, username: session.username });
  }
});
