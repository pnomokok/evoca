import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../context/useApp';
import { useAudioElement } from '../utils/useAudioElement';
import { apiClient } from '../api/client';
import { announceChange, listenForTour, sendTour } from '../utils/stageChannel';
import { SAMPLE_ANSWERS, isSuggestedQuestion, usePaneTourTargets } from '../utils/tour';
import { playChime, primeChime } from '../utils/chime';
import Avatar from './Avatar';
import { Mic, Volume2, Square, Lock, Sparkles } from 'lucide-react';
import '../styles/device.css';

const REACTION_EMOJI = { heart: '❤️', laugh: '😂', sad: '😢', pray: '🙏' };
const CLOCK_REFRESH_MS = 60000;
const PRIVACY_MOMENT_MS = 4500;

function shorten(value, max = 90) {
  if (value == null) return '';
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

const seconds = (ms) => `${((ms ?? 0) / 1000).toFixed(1)} s`;

// A turn whose tool trace shows the companion agreed to keep something private.
function keptPrivate(turn) {
  return (turn?.trace || []).some(t => t.tool === 'keep_private' && !t.is_error);
}

// A caption gets smaller as the sentence gets longer, so it always fits the screen.
function captionSize(text) {
  const n = text?.length || 0;
  if (n > 260) return 'xs';
  if (n > 170) return 'sm';
  return 'md';
}

// A question without an asker (follow-up or gap) is Evoca's own; it never names a family member.
function DeviceCard({ card, members }) {
  // The server sends an asker with empty fields for Evoca's own question.
  const from = card.type === 'reaction' ? card.from : card.type === 'question' ? card.asker : null;
  const person = from?.id || from?.name ? from : null;
  const member = person && (members.find(m => m.id === person.id) || person);
  const first = person?.name?.split(' ')[0] || 'Someone in your family';
  const ownQuestion = card.type === 'question' && !person;
  return (
    <span className="device-chip">
      {member ? <Avatar person={member} size={26} />
        : ownQuestion ? <Sparkles size={18} aria-hidden="true" />
          : <span aria-hidden="true">🎧</span>}
      {card.type === 'reaction' && <span>{REACTION_EMOJI[card.emoji] || '💛'} {first} reacted</span>}
      {card.type === 'question' && <span>{ownQuestion ? "Evoca's question" : `${first} asked`}</span>}
      {card.type === 'playlist' && <span>Playing your stories</span>}
    </span>
  );
}

// The trace and latency of each turn, in the technical style: for the judges, outside the device.
function TracePanel({ turns }) {
  const last = turns[turns.length - 1];
  const earlier = turns.slice(0, -1);
  const rows = (turn) => (turn.trace || []).length === 0
    ? <div className="trace-empty">No tool calls.</div>
    : turn.trace.map((t, i) => (
      <div key={i} className={`trace-row ${t.is_error ? 'error' : ''}`} data-testid="trace-row" title={shorten(t.result_preview, 300)}>
        <span aria-hidden="true">{t.is_error ? '✗' : '✓'}</span>
        <span className="trace-tool">
          {t.tool}{t.prefetched ? ' · prefetched' : ''}{t.is_error ? ' · error' : ''}
          <span className="trace-input">{shorten(t.input, 70)}</span>
        </span>
        <span className="trace-ms">{t.ms} ms</span>
      </div>
    ));
  const latency = (turn) => turn.latency && (
    <div className="trace-latency" data-testid="latency-line">
      <span>STT {seconds(turn.latency.stt_ms)}</span>
      <span>LLM + tools {seconds((turn.latency.llm_ms ?? 0) + (turn.latency.tools_ms ?? 0))}</span>
      <span>TTS {seconds(turn.latency.tts_ms)}</span>
      <span>Total {seconds(turn.latency.total_ms)}</span>
    </div>
  );

  return (
    <section className={`trace-panel ${last ? '' : 'empty'}`} data-testid="trace-panel" aria-label="What Evoca did" data-tour="trace">
      <div className="trace-head">
        <span>What Evoca did · MCP tools</span>
        <span>{last ? `turn ${turns.length}` : 'no tool calls yet'}</span>
      </div>
      {last && <>{rows(last)}{latency(last)}</>}
      {earlier.length > 0 && (
        <details className="trace-earlier">
          <summary>Earlier turns ({earlier.length})</summary>
          {earlier.map((turn, idx) => (
            <div key={turn.key} className="trace-turn">
              <div className="trace-turn-title">Turn {idx + 1}</div>
              {rows(turn)}
              {latency(turn)}
            </div>
          ))}
        </details>
      )}
    </section>
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
  // "This stays between us": shown for a few seconds after a turn that kept something private.
  const [privacyMoment, setPrivacyMoment] = useState(false);
  // The guided tour's sample answers: the next clip to send, and whether one is playing.
  const [sampleIndex, setSampleIndex] = useState(0);
  const [sampling, setSampling] = useState(false);
  // Photos of stories the center person can see, for the idle screen.
  const [photoItems, setPhotoItems] = useState([]);
  const [photo, setPhoto] = useState({ path: null, src: null });
  const [photoTick, setPhotoTick] = useState(0);
  const getPlayer = useAudioElement();
  // The guided tour's answer step (step 4) is showing on this stage: only then the sample answers.
  const tourAnswerStep = usePaneTourTargets().includes('answer');

  // The open session lives in a ref so a double tap (or StrictMode) can never start two,
  // and so unload/unmount handlers can still read it.
  const sessionRef = useRef({ id: null, centerId: null, starting: false });
  const playbackRef = useRef({ token: 0, resolve: null });
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const privacyTimerRef = useRef(null);

  const members = circleData?.members || [];
  const centerName =
    members.find(m => m.id === centerPersonId)?.name ||
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
    const timer = setInterval(() => { refresh(); setPhotoTick(t => t + 1); }, CLOCK_REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [viewerReady, centerPersonId, setInvitationData, dataVersion]);

  // Story photos the device can see: the center's lifeline, asked as the center person.
  useEffect(() => {
    if (!viewerReady || !centerPersonId) return;
    let cancelled = false;
    apiClient.getLifeline(centerPersonId, centerPersonId)
      .then(life => {
        if (cancelled) return;
        const seen = new Set();
        const items = (life?.periods || [])
          .flatMap(p => p.stories || [])
          .filter(s => s?.photo_url && !seen.has(s.photo_url) && seen.add(s.photo_url))
          // The device shows the story's title, never the uploader's caption (written about her, not to her).
          .map(s => ({ path: s.photo_url, caption: s.title || '' }));
        setPhotoItems(items);
      })
      .catch(() => { if (!cancelled) setPhotoItems([]); });
    return () => { cancelled = true; };
  }, [viewerReady, centerPersonId, dataVersion]);

  // One photo at a time, a different one each minute; fetched as the center person.
  const photoItem = photoItems.length ? photoItems[photoTick % photoItems.length] : null;
  const photoPath = photoItem?.path || null;
  useEffect(() => {
    if (!photoPath) return;
    let cancelled = false;
    let blobUrl = null;
    apiClient.fetchBlobUrl(photoPath, centerPersonId)
      .then(src => {
        if (cancelled) { URL.revokeObjectURL(src); return; }
        blobUrl = src;
        setPhoto({ path: photoPath, src });
      })
      .catch(() => { if (!cancelled) setPhoto({ path: photoPath, src: null }); });
    return () => {
      cancelled = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [photoPath, centerPersonId]);
  const photoSrc = photoPath && photo.path === photoPath ? photo.src : null;

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
    setSampling(false);
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

  useEffect(() => () => clearTimeout(privacyTimerRef.current), []);

  // The guided tour asks before it resets the demo: is a conversation running here?
  useEffect(() => listenForTour(m => {
    if (m.kind === 'ask-session') {
      const open = Boolean(sessionRef.current.id || sessionRef.current.starting);
      sendTour({ kind: 'event', name: open ? 'session_open' : 'session_closed' });
    }
  }), []);

  const addTurn = (turn) => {
    setTurns(prev => [...prev, { ...turn, key: `${prev.length}-${Date.now()}` }]);
    // For the guided tour: a family member's question was just raised (no text or id is sent).
    if ((turn.cards || []).some(c => c.type === 'question' && (c.asker?.id || c.asker?.name))) {
      sendTour({ kind: 'event', name: 'question_asked' });
    }
    if (keptPrivate(turn)) {
      setPrivacyMoment(true);
      clearTimeout(privacyTimerRef.current);
      privacyTimerRef.current = setTimeout(() => setPrivacyMoment(false), PRIVACY_MOMENT_MS);
    }
  };

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

  const refreshLight = async () => {
    try {
      setInvitationData(await apiClient.getDeviceInvitation(centerPersonId));
    } catch (err) {
      console.warn('Could not refresh the invitation light:', err);
    }
  };

  // The session is over (Goodbye, or the companion closed it): the archivist starts on the server.
  const sessionClosed = () => {
    refreshLight();
    announceChange('session_end');
  };

  // "Alexa, what's new?" — the only place a session is started.
  const handleTalk = async () => {
    const session = sessionRef.current;
    if (session.starting || session.id) return;
    primeChime();
    session.starting = true;
    setPhase('starting');
    setDeviceError(null);
    setTurns([]);
    setSampleIndex(0);
    try {
      const turn = await apiClient.postDeviceSessionStart(centerPersonId);
      session.centerId = centerPersonId;
      addTurn(turn);
      if (turn.session_open === false) {
        setPhase('ended');
        sessionClosed();
      } else {
        session.id = turn.session_id;
        setPhase('active');
      }
      sendTour({ kind: 'event', name: 'session_start' });
      playTurnAudio(turn).then(() => sendTour({ kind: 'event', name: 'opening_played' }));
    } catch (err) {
      console.error('Device session start failed:', err);
      setDeviceError("Evoca couldn't start just now. Please tap Talk again.");
      setPhase('idle');
    } finally {
      session.starting = false;
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
      sessionClosed();
    } catch (err) {
      console.error(err);
      showToast("Couldn't close the conversation properly.", "error");
    }
  };

  // Submit a spoken turn (POST /api/device/turn multipart: audio + session_id, no text field).
  // beforeReply: a sample answer still playing; the reply waits for it.
  const submitTurn = async (audioBlob, beforeReply = null) => {
    const session = sessionRef.current;
    if (!audioBlob || audioBlob.size === 0 || !session.id) {
      setBusy(false);
      return;
    }
    setBusy(true);
    sendTour({ kind: 'event', name: 'turn_sent' });
    try {
      const turn = await apiClient.postDeviceTurn(audioBlob, session.id, centerPersonId);
      if (beforeReply) await beforeReply;
      addTurn(turn);
      if (turn.session_open === false) {
        session.id = null;
        setPhase('ended');
        sessionClosed();
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
    primeChime();
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

  // The guided tour's "Use a sample answer": the next clip plays aloud and the same audio goes to
  // POST /api/device/turn as a recording would, so speech-to-text and the companion run for real.
  const playSample = async () => {
    const url = SAMPLE_ANSWERS[sampleIndex];
    if (!url || phase !== 'active' || busy || isRecording || isPlayingAudio || sampling) return;
    primeChime();
    setSampling(true);
    let blob;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`sample answer: ${res.status}`);
      blob = await res.blob();
    } catch (err) {
      console.warn(err);
      setSampling(false);
      showToast("The sample answer isn't available.", 'error');
      return;
    }
    setSampleIndex(i => i + 1);
    const heard = new Promise(resolve => {
      const src = URL.createObjectURL(blob);
      let finished = false;
      const done = () => {
        if (finished) return;
        finished = true;
        getPlayer().onpause = null;
        URL.revokeObjectURL(src);
        setSampling(false);
        resolve();
      };
      const player = getPlayer();
      // A pause (a demo reset stops the player) ends it too, so the reply never waits forever.
      player.onended = done;
      player.onpause = done;
      player.onerror = done;
      player.src = src;
      player.play().catch(done);
    });
    await submitTurn(blob, heard);
  };

  // Recording stops: a soft chime, and the screen shows it is thinking until the reply arrives.
  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setBusy(true);
      playChime();
    }
    setIsRecording(false);
  };

  // Clock and date from the server's demo-aware "now", in the family's time zone.
  const nowIso = invitationData?.now;
  const now = nowIso ? new Date(nowIso) : null;
  const timeZone = circleData?.circle?.timezone || undefined;
  const timeLabel = now ? now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone }) : '--:--';
  const dateLabel = now ? now.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone }) : '';

  // One state on the screen at a time.
  const invitationOn = Boolean(invitationData?.active);
  const screenState =
    (isRecording || sampling) ? 'listening'
      : (phase === 'starting' || busy) ? 'thinking'
        : (isPlayingAudio || (phase === 'active' && lastTurn?.reply_text)) ? 'speaking'
          : invitationOn ? 'invitation' : 'idle';

  // The invitation's reason names at most one first name; show that person's initials.
  const reason = invitationData?.invitation?.reason || 'Your family has something for you.';
  const reasonPerson = members.find(m => {
    const first = m.name?.split(' ')[0];
    return m.id !== centerPersonId && first && new RegExp(`(^|\\W)${first}(\\W|$)`).test(reason);
  });

  const caption = lastTurn?.reply_text || '';
  const showPhoto = Boolean(photoSrc) && screenState === 'idle';
  const showTrace = turns.length > 0 || Boolean(apiClient.embed);

  // The sample answers belong to the tour's question: offered only on the tour's answer step, and only
  // when that question was asked in this session; otherwise a note there says why.
  const tourQuestionAsked = turns.some(t => (t.cards || []).some(c => c.type === 'question' && isSuggestedQuestion(c.text)));
  const canSample = tourQuestionAsked && sampleIndex < SAMPLE_ANSWERS.length;
  const showSample = tourAnswerStep && canSample && !busy && !isRecording && !isPlayingAudio && !sampling;
  const showSampleNote = tourAnswerStep && !tourQuestionAsked && !isRecording && !sampling
    && turns.some(t => (t.cards || []).some(c => c.type === 'question'));
  // The tour rings Goodbye too once the next sample is the goodbye, or after two spoken answers.
  const ringGoodbye = canSample ? sampleIndex >= SAMPLE_ANSWERS.length - 1 : turns.length > 2;

  return (
    <div className={`device-stack ${apiClient.embed ? 'embedded' : ''}`}>
      <div className="device-object">
        <div className={`device-screen state-${screenState} ${privacyMoment ? 'privacy' : ''}`} data-state={screenState}>
          {showPhoto && <img className="device-photo" src={photoSrc} alt="" />}
          <div className="device-light" aria-hidden="true" />

          <div className="device-main" aria-live="polite">
            {(screenState === 'idle' || screenState === 'invitation') && (
              <div className="device-clock-block">
                {screenState === 'invitation' && (
                  <div className="device-invitation" role="status">
                    {reasonPerson && <Avatar person={reasonPerson} size={56} ring />}
                    <p className="device-reason">{reason}</p>
                  </div>
                )}
                <div className="device-time" data-testid="device-time" data-now={nowIso || ''}>{timeLabel}</div>
                <div className="device-date">{dateLabel}</div>
                {showPhoto && photoItem?.caption && <p className="device-photo-caption">{photoItem.caption}</p>}
                {deviceError && <p className="device-error" role="alert">{deviceError}</p>}
              </div>
            )}

            {screenState === 'listening' && (
              <p className="device-status-line">I'm listening{firstName ? `, ${firstName}` : ''}.</p>
            )}

            {screenState === 'thinking' && (
              <div className="device-thinking" role="status" aria-label="Thinking">
                <i /><i /><i />
              </div>
            )}

            {screenState === 'speaking' && (
              <div className="device-caption-block" data-testid="device-turn">
                <p className={`device-caption size-${captionSize(caption)} ${isPlayingAudio ? 'live' : ''}`}>{caption}</p>
                {lastTurn?.cards?.length > 0 && (
                  <div className="device-chips">
                    {lastTurn.cards.map((card, i) => <DeviceCard key={i} card={card} members={members} />)}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="device-controls">
            {phase === 'active' ? (
              <>
                <div className="device-side">
                  {isPlayingAudio ? (
                    <button type="button" className="device-quiet-btn" onClick={stopAudio}>
                      <Square size={16} /> Stop
                    </button>
                  ) : lastTurn?.reply_audio_url && !busy && !isRecording && (
                    <button type="button" className="device-quiet-btn" onClick={() => playTurnAudio(lastTurn)}>
                      <Volume2 size={16} /> Hear it again
                    </button>
                  )}
                </div>
                <button
                  type="button"
                  className={`device-talk ${isRecording ? 'recording' : ''}`}
                  onPointerDown={startRecording}
                  onPointerUp={stopRecording}
                  onPointerLeave={() => isRecording && stopRecording()}
                  disabled={busy || isPlayingAudio || sampling}
                  aria-label={isRecording ? 'Listening, let go to finish' : 'Hold to speak'}
                  data-tour={canSample ? undefined : 'answer'}
                >
                  <span className="device-ring" aria-hidden="true" />
                  <Mic size={30} />
                  <span className="device-talk-label">{isRecording ? 'Listening' : 'Hold'}</span>
                </button>
                {showSample && (
                  <button type="button" className="device-quiet-btn sample" onClick={playSample} data-tour="answer">
                    Use a sample answer
                  </button>
                )}
                {showSampleNote && (
                  <p className="device-sample-note">Sample answers fit the suggested question. Answer with your voice.</p>
                )}
                <div className="device-side right">
                  {!isRecording && !sampling && (
                    <button type="button" className="device-quiet-btn" onClick={handleGoodbye} data-tour={ringGoodbye ? 'answer' : undefined}>
                      Goodbye
                    </button>
                  )}
                </div>
              </>
            ) : (
              <button
                type="button"
                className="device-talk"
                onClick={handleTalk}
                disabled={phase === 'starting' || !viewerReady || !centerPersonId}
                aria-label="Talk: Alexa, what's new?"
                data-tour={phase === 'starting' ? undefined : 'talk'}
              >
                <span className="device-ring" aria-hidden="true" />
                <span className="device-talk-label big">Talk</span>
              </button>
            )}
          </div>

          {privacyMoment && (
            <div className="device-privacy" role="status" data-testid="privacy-moment">
              <Lock size={44} />
              <p>This stays between us.</p>
            </div>
          )}
        </div>
      </div>

      {showTrace && <TracePanel turns={turns} />}
    </div>
  );
}
