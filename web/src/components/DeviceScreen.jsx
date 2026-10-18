import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../context/useApp';
import { useAudioElement } from '../utils/useAudioElement';
import { apiClient } from '../api/client';
import { Mic, MicOff, Volume2, Sparkles, XSquare, MessageCircle, Square } from 'lucide-react';

const REACTION_EMOJI = { heart: '❤️', laugh: '😂', sad: '😢', pray: '🙏' };
const CLOCK_REFRESH_MS = 60000;

function shorten(value, max = 90) {
  if (value == null) return '';
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

// "stt 812 ms · llm and tools 2140 + 95 ms · tts 410 ms · total 3480 ms"
function latencyLine(latency) {
  if (!latency) return '';
  const ms = (v) => `${v ?? 0} ms`;
  return `stt ${ms(latency.stt_ms)} · llm and tools ${latency.llm_ms ?? 0} + ${ms(latency.tools_ms)} · tts ${ms(latency.tts_ms)} · total ${ms(latency.total_ms)}`;
}

function DeviceCard({ card }) {
  return (
    <div className="device-subcard">
      <div className="subcard-emoji" aria-hidden="true">
        {card.type === 'reaction' ? (REACTION_EMOJI[card.emoji] || '💛')
          : card.type === 'playlist' ? '🎧' : '❓'}
      </div>
      <div>
        <div className="subcard-title">
          {card.type === 'reaction' && `${card.from?.name || 'Someone in your family'} reacted`}
          {card.type === 'question' && `${card.asker?.name || 'Someone in your family'} asked`}
          {card.type === 'playlist' && 'Playing your stories'}
        </div>
        <div className="subcard-desc">
          {card.type === 'reaction' && `to "${card.story_title || 'your story'}"`}
          {card.type === 'question' && card.text}
          {card.type === 'playlist' && (card.items || []).map(i => i.title)
            .filter((t, idx, all) => all.indexOf(t) === idx).join(', ')}
        </div>
      </div>
    </div>
  );
}

export default function DeviceScreen() {
  const { invitationData, setInvitationData, centerPersonId, viewerReady, showToast, circleData, peopleList, dataVersion, resetVersion } = useApp();
  // 'idle': light only, nothing started · 'starting' · 'active': a session is open · 'ended'
  const [phase, setPhase] = useState('idle');
  const [isRecording, setIsRecording] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  // Every turn of this conversation: what was heard, what Evoca said, cards, trace and latency.
  const [turns, setTurns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [deviceError, setDeviceError] = useState(null);
  const getPlayer = useAudioElement();

  // The open session lives in a ref so a double tap (or StrictMode) can never start two,
  // and so unload/unmount handlers can still read it.
  const sessionRef = useRef({ id: null, centerId: null, starting: false });
  const playbackRef = useRef({ token: 0, resolve: null });
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const conversationEndRef = useRef(null);

  const centerName =
    circleData?.members?.find(m => m.id === centerPersonId)?.name ||
    peopleList?.find(p => p.id === centerPersonId)?.name ||
    '';
  const firstName = centerName.split(' ')[0];
  const lastTurn = turns[turns.length - 1] || null;

  // The light and the clock: GET /api/device/invitation now, then every minute.
  // Its "now" is the demo-aware server time, so the device clock follows the demo clock.
  useEffect(() => {
    if (!viewerReady || !centerPersonId) return;
    let cancelled = false;
    const refresh = () => apiClient.getDeviceInvitation(centerPersonId)
      .then(inv => { if (!cancelled) setInvitationData(inv); })
      .catch(err => console.warn('Could not refresh the invitation light:', err));
    refresh();
    const timer = setInterval(refresh, CLOCK_REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [viewerReady, centerPersonId, setInvitationData, dataVersion]);

  // A demo reset has already ended any live session and changed every id: forget it here
  // without calling /session/end, and start again from the light.
  const seenResetRef = useRef(resetVersion);
  useEffect(() => {
    if (seenResetRef.current === resetVersion) return;
    seenResetRef.current = resetVersion;
    sessionRef.current.id = null;
    playbackRef.current.token += 1;
    getPlayer().pause();
    if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop();
    setIsRecording(false);
    setIsPlayingAudio(false);
    setTurns([]);
    setDeviceError(null);
    setPhase('idle');
  }, [resetVersion, getPlayer]);

  // End the session when the page goes away or the elder leaves this screen (best effort).
  useEffect(() => {
    const session = sessionRef.current;
    const playback = playbackRef.current;
    const endOpenSession = () => {
      if (!session.id) return;
      apiClient.endDeviceSessionOnUnload(session.id, session.centerId);
      session.id = null;
    };
    window.addEventListener('pagehide', endOpenSession);
    return () => {
      window.removeEventListener('pagehide', endOpenSession);
      endOpenSession();
      playback.token += 1;
      getPlayer().pause();
    };
  }, [getPlayer]);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView?.({ block: 'nearest' });
  }, [turns.length]);

  const addTurn = (turn) => setTurns(prev => [...prev, { ...turn, key: `${prev.length}-${Date.now()}` }]);

  const stopAudio = () => {
    playbackRef.current.token += 1;
    getPlayer().pause();
    playbackRef.current.resolve?.();
    setIsPlayingAudio(false);
  };

  // Play the reply first, then any playlist items in order (each fetched with X-Person-Id = center).
  // The microphone stays off until it is done or Stop is pressed.
  const playTurnAudio = async (turn) => {
    const urls = [
      turn?.reply_audio_url,
      ...(turn?.cards || [])
        .filter(c => c.type === 'playlist')
        .flatMap(c => (c.items || []).map(i => i.url))
    ].filter(Boolean);
    if (urls.length === 0) return;

    stopAudio();
    const token = playbackRef.current.token;
    setIsPlayingAudio(true);
    for (const url of urls) {
      if (token !== playbackRef.current.token) return;
      let blobUrl = null;
      try {
        blobUrl = await apiClient.fetchBlobUrl(url, centerPersonId);
      } catch (err) {
        console.warn('Could not fetch reply audio:', err);
      }
      if (!blobUrl || token !== playbackRef.current.token) continue;
      await new Promise(resolve => {
        playbackRef.current.resolve = resolve;
        getPlayer().onended = resolve;
        getPlayer().onerror = resolve;
        getPlayer().src = blobUrl;
        getPlayer().play().catch(resolve);
      });
      URL.revokeObjectURL(blobUrl);
    }
    if (token === playbackRef.current.token) setIsPlayingAudio(false);
  };

  // "Alexa, what's new?" — the only place a session is started.
  const handleTalk = async () => {
    const session = sessionRef.current;
    if (session.starting || session.id) return;
    session.starting = true;
    setPhase('starting');
    setDeviceError(null);
    setTurns([]);
    try {
      const turn = await apiClient.postDeviceSessionStart(centerPersonId);
      session.centerId = centerPersonId;
      addTurn(turn);
      if (turn.session_open === false) {
        setPhase('ended');
      } else {
        session.id = turn.session_id;
        setPhase('active');
      }
      playTurnAudio(turn);
    } catch (err) {
      console.error('Device session start failed:', err);
      setDeviceError("Evoca couldn't start just now. Please tap Talk again.");
      setPhase('idle');
    } finally {
      session.starting = false;
    }
  };

  const refreshLight = async () => {
    try {
      setInvitationData(await apiClient.getDeviceInvitation(centerPersonId));
    } catch (err) {
      console.warn('Could not refresh the invitation light:', err);
    }
  };

  // "Goodbye": POST /api/device/session/end {"session_id": ...}
  const handleGoodbye = async () => {
    const session = sessionRef.current;
    const sessionId = session.id;
    if (!sessionId) return;
    session.id = null;
    stopAudio();
    setPhase('ended');
    try {
      await apiClient.postDeviceSessionEnd(sessionId, centerPersonId);
      showToast("Goodbye! Today's memories are being saved.", "info");
      refreshLight();
    } catch (err) {
      console.error(err);
      showToast("Couldn't close the conversation properly.", "error");
    }
  };

  // Submit a spoken turn (POST /api/device/turn multipart: audio + session_id, no text field)
  const submitTurn = async (audioBlob) => {
    const session = sessionRef.current;
    if (!audioBlob || audioBlob.size === 0 || !session.id) return;
    setBusy(true);
    try {
      const turn = await apiClient.postDeviceTurn(audioBlob, session.id, centerPersonId);
      addTurn(turn);
      if (turn.session_open === false) {
        session.id = null;
        setPhase('ended');
        refreshLight();
      } else if (turn.session_id) {
        session.id = turn.session_id;
      }
      playTurnAudio(turn);
    } catch (err) {
      console.error(err);
      showToast("Sorry, I didn't catch that. Please try again.", "error");
    } finally {
      setBusy(false);
    }
  };

  const startRecording = async () => {
    if (phase !== 'active' || busy || isRecording || isPlayingAudio) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        await submitTurn(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch {
      showToast("The microphone isn't available. Please check the permission.", "error");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  // Clock and date from the server's demo-aware "now", in the family's time zone.
  const nowIso = invitationData?.now;
  const now = nowIso ? new Date(nowIso) : null;
  const timeZone = circleData?.circle?.timezone || undefined;
  const timeLabel = now ? now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone }) : '--:--';
  const dateLabel = now ? now.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone }) : '';
  const traceCount = turns.reduce((n, t) => n + (t.trace?.length || 0), 0);

  return (
    <div className="device-wrapper">
      {/* Notification light: glows while a family invitation is waiting */}
      {invitationData?.active && (
        <div className="device-ambient-glow" title="Your family has something for you" aria-hidden="true" />
      )}

      <div className="device-header">
        <div>
          <div className="device-time" data-testid="device-time" data-now={nowIso || ''}>{timeLabel}</div>
          <div className="device-date">{dateLabel ? `${dateLabel} · ` : ''}Living room</div>
        </div>

        {invitationData?.active && (
          <div className="device-invitation-banner" role="status">
            <Sparkles size={16} />
            <span>{invitationData.invitation?.reason || 'Your family has something for you.'}</span>
          </div>
        )}
      </div>

      <div className="device-content">
        <div className="device-speech-bubble-area" aria-live="polite">
          {deviceError && (
            <div className="elder-heard-card" role="alert" style={{ borderColor: 'rgba(239, 68, 68, 0.4)' }}>
              <div className="elder-text">{deviceError}</div>
            </div>
          )}

          {/* The conversation so far: per turn, what the device heard and what Evoca said */}
          {turns.map((turn) => (
            <div key={turn.key} className="device-turn" data-testid="device-turn">
              {turn.heard_text && (
                <div className="elder-heard-card">
                  <div className="elder-label">{firstName || 'You'} said</div>
                  <div className="elder-text">"{turn.heard_text}"</div>
                </div>
              )}

              {turn.reply_text && (
                <div className="agent-reply-card">
                  <div className="agent-label">
                    <Sparkles size={14} />
                    Evoca
                    {turn === lastTurn && isPlayingAudio && (
                      <span style={{ color: 'var(--accent-gold)', marginLeft: '8px' }}>
                        ● Speaking...
                      </span>
                    )}
                  </div>
                  <div className="agent-text">{turn.reply_text}</div>

                  {turn.cards && turn.cards.length > 0 && (
                    <div className="device-cards-row">
                      {turn.cards.map((card, i) => <DeviceCard key={i} card={card} />)}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {phase === 'ended' && !lastTurn?.reply_text && (
            <div className="agent-reply-card">
              <div className="agent-text">Goodbye{firstName ? `, ${firstName}` : ''}! Talk to you soon.</div>
            </div>
          )}

          {(phase === 'starting' || busy) && (
            <div style={{ textAlign: 'center', padding: '16px', color: 'var(--accent-gold)' }} role="status">
              One moment...
            </div>
          )}
          <div ref={conversationEndRef} />
        </div>

        <div className="device-bottom-action">
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap', justifyContent: 'center' }}>
            {phase === 'active' ? (
              <>
                <button
                  type="button"
                  className={`push-to-talk-btn ${isRecording ? 'recording' : ''}`}
                  onPointerDown={startRecording}
                  onPointerUp={stopRecording}
                  onPointerLeave={() => isRecording && stopRecording()}
                  disabled={busy || isPlayingAudio}
                  aria-label="Hold to speak"
                >
                  {isRecording || isPlayingAudio ? <MicOff className="ptt-icon" /> : <Mic className="ptt-icon" />}
                  <span className="ptt-label">
                    {isRecording ? 'Listening...' : isPlayingAudio ? 'Mic off while playing' : 'Hold to speak'}
                  </span>
                </button>

                {isPlayingAudio ? (
                  <button
                    type="button"
                    className="quick-prompt-chip"
                    style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                    onClick={stopAudio}
                  >
                    <Square size={16} /> Stop
                  </button>
                ) : lastTurn?.reply_audio_url && (
                  <button
                    type="button"
                    className="quick-prompt-chip"
                    style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                    onClick={() => playTurnAudio(lastTurn)}
                  >
                    <Volume2 size={16} /> Hear it again
                  </button>
                )}

                <button
                  type="button"
                  className="quick-prompt-chip"
                  style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: '#fca5a5' }}
                  onClick={handleGoodbye}
                >
                  <XSquare size={16} /> Goodbye
                </button>
              </>
            ) : (
              <button
                type="button"
                className="push-to-talk-btn"
                style={{ width: '200px', height: '200px' }}
                onClick={handleTalk}
                disabled={phase === 'starting' || !viewerReady || !centerPersonId}
                aria-label="Talk: Alexa, what's new?"
              >
                <MessageCircle className="ptt-icon" />
                <span className="ptt-label" style={{ fontSize: '22px', fontWeight: 700 }}>Talk</span>
                <span className="ptt-label">"Alexa, what's new?"</span>
              </button>
            )}
          </div>

          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Living room device{firstName ? ` · ${firstName}` : ''} · tap Talk to begin
          </div>

          {/* For the demo: what happened behind each turn (tools, timings) */}
          {turns.length > 0 && (
            <details className="device-trace-panel" data-testid="trace-panel" style={{ width: '100%', maxWidth: '760px', fontSize: '12px', color: 'var(--text-muted)' }}>
              <summary style={{ cursor: 'pointer' }}>Behind the scenes · {traceCount} tool {traceCount === 1 ? 'call' : 'calls'}</summary>
              {turns.map((turn, idx) => (
                <div key={turn.key} style={{ marginTop: '10px' }}>
                  <div><strong>Turn {idx + 1}</strong>{turn.latency && <span data-testid="latency-line"> · {latencyLine(turn.latency)}</span>}</div>
                  {(turn.trace || []).length === 0 ? (
                    <div>No tool calls.</div>
                  ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr><th align="left">Tool</th><th align="left">Input</th><th align="left">Result</th><th align="right">ms</th></tr>
                      </thead>
                      <tbody>
                        {turn.trace.map((t, i) => (
                          <tr key={i} data-testid="trace-row">
                            <td>{t.is_error ? `${t.tool} (error)` : t.tool}</td>
                            <td style={{ wordBreak: 'break-word' }}>{shorten(t.input, 60)}</td>
                            <td style={{ wordBreak: 'break-word' }}>{shorten(t.result_preview, 80)}</td>
                            <td align="right">{t.ms}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
