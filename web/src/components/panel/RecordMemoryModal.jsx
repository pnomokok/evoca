import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import { X, Mic, Square, Lock, Users, AlertCircle } from 'lucide-react';
import Modal from '../Modal';

const MAX_RECORDING_SECONDS = 180; // 3 minutes maximum
const METER_BARS = 5;

const ACCESS_OPTIONS = [
  { key: 'circle', icon: Users, title: 'Family circle', sub: 'Everyone in the family' },
  { key: 'private', icon: Lock, title: 'Only me', sub: 'Only you can listen' }
];

// Mounted only while open (see FamilyPanel), so every opening starts from fresh state.
// Record: a round button; while recording it becomes Stop with a pulsing ring, the timer counts and
// a small level meter shows the microphone hears something. After Stop: play it back, record again or save.
export default function RecordMemoryModal({ onClose }) {
  const { showToast, refreshData } = useApp();
  const [isRecording, setIsRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [access, setAccess] = useState('circle'); // 'circle' | 'private'
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [levels, setLevels] = useState(() => Array(METER_BARS).fill(0));

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timersRef = useRef({ tick: null, limit: null });
  const meterRef = useRef({ context: null, frame: 0 });
  const closedRef = useRef(false);   // the dialog closed (maybe while the mic permission was asked)

  const clearTimers = () => {
    clearInterval(timersRef.current.tick);
    clearTimeout(timersRef.current.limit);
  };

  const stopMeter = () => {
    cancelAnimationFrame(meterRef.current.frame);
    meterRef.current.context?.close().catch(() => {});
    meterRef.current = { context: null, frame: 0 };
    setLevels(Array(METER_BARS).fill(0));
  };

  // The live level: loudness of a few frequency bands of the microphone, about 30 times a second.
  const startMeter = (stream) => {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const context = new AudioContextClass();
    const analyser = context.createAnalyser();
    analyser.fftSize = 64;
    context.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const band = Math.floor(data.length / METER_BARS);
    let last = 0;
    const tick = (t) => {
      if (t - last > 33) {
        last = t;
        analyser.getByteFrequencyData(data);
        setLevels(Array.from({ length: METER_BARS }, (_, i) => {
          let sum = 0;
          for (let j = i * band; j < (i + 1) * band; j++) sum += data[j];
          return Math.min(1, sum / band / 160);
        }));
      }
      meterRef.current.frame = requestAnimationFrame(tick);
    };
    meterRef.current = { context, frame: requestAnimationFrame(tick) };
  };

  const handleStopRecording = () => {
    clearTimers();
    stopMeter();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  // Stop the microphone if the dialog closes mid-recording.
  useEffect(() => {
    const timers = timersRef.current;
    const recorderRef = mediaRecorderRef;
    const meter = meterRef;
    const closed = closedRef;
    return () => {
      closed.current = true;
      clearInterval(timers.tick);
      clearTimeout(timers.limit);
      cancelAnimationFrame(meter.current.frame);
      meter.current.context?.close().catch(() => {});
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
    };
  }, []);

  // The playback URL follows the recording, and is released with it.
  useEffect(() => {
    if (!audioBlob) { setAudioUrl(null); return undefined; }
    const url = URL.createObjectURL(audioBlob);
    setAudioUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [audioBlob]);

  const handleStartRecording = async () => {
    setErrorMessage(null);
    setAudioBlob(null);
    setRecordSeconds(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Closed while the browser asked for the microphone: let it go at once.
      if (closedRef.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        setAudioBlob(blob);
      };

      mediaRecorder.start();
      setIsRecording(true);
      startMeter(stream);
      timersRef.current.tick = setInterval(() => setRecordSeconds(s => Math.min(s + 1, MAX_RECORDING_SECONDS)), 1000);
      timersRef.current.limit = setTimeout(handleStopRecording, MAX_RECORDING_SECONDS * 1000);
    } catch {
      setErrorMessage("The microphone isn't available. Please check the permission.");
    }
  };

  const handleSaveRecording = async () => {
    if (!audioBlob || recordSeconds < 1) {
      setErrorMessage("That recording is too short. Please try again.");
      return;
    }

    setIsProcessing(true);
    setErrorMessage(null);

    try {
      await apiClient.postRecording(audioBlob, access);
      showToast("Thank you! Your memory is being processed and will appear soon.", "info");
      if (refreshData) refreshData();
      onClose();
    } catch (err) {
      console.error(err);
      setErrorMessage("Your memory couldn't be saved. Please try again.");
    } finally {
      setIsProcessing(false);
    }
  };

  const formatTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <Modal onClose={onClose} labelledBy="record-dialog-title" sheetStyle={{ maxWidth: '480px' }}>
      <div className="modal-title-row">
        <div>
          <h2 id="record-dialog-title" className="archival-dialog-title">Record your own memory</h2>
          <p className="archival-dialog-sub">
            Add a memory in your own voice to the family archive.
          </p>
        </div>
        <button type="button" className="close-btn" onClick={onClose} aria-label="Close"><X size={20} /></button>
      </div>

      <fieldset className="record-access">
        <legend className="form-label">Who can listen</legend>
        <div className="record-access-options">
          {ACCESS_OPTIONS.map(({ key, icon: Icon, title, sub }) => (
            <button
              key={key}
              type="button"
              className={`record-access-option ${access === key ? 'selected' : ''}`}
              onClick={() => setAccess(key)}
              aria-pressed={access === key}
              disabled={isRecording || isProcessing}
            >
              <Icon size={16} className="record-access-icon" aria-hidden="true" />
              <span className="record-access-title">{title}</span>
              <span className="record-access-sub">{sub}</span>
            </button>
          ))}
        </div>
      </fieldset>

      {errorMessage && (
        <div className="record-error" role="alert">
          <AlertCircle size={16} />
          <span>{errorMessage}</span>
        </div>
      )}

      <div className="record-stage">
        <div className={`record-timer ${isRecording ? 'live' : ''}`} aria-live="off">{formatTime(recordSeconds)}</div>

        {!audioBlob ? (
          <>
            <button
              type="button"
              className={`record-button ${isRecording ? 'recording' : ''}`}
              onClick={isRecording ? handleStopRecording : handleStartRecording}
              disabled={isProcessing}
              aria-label={isRecording ? 'Stop recording' : 'Start recording'}
              data-autofocus
            >
              <span className="record-ring" aria-hidden="true" />
              {isRecording ? <Square size={24} fill="currentColor" /> : <Mic size={30} />}
            </button>
            <span className="record-button-label" aria-hidden="true">{isRecording ? 'Stop' : 'Record'}</span>
            {isRecording ? (
              <div className="record-meter" role="img" aria-label="The microphone is picking up sound">
                {levels.map((level, i) => (
                  <span key={i} style={{ transform: `scaleY(${0.15 + level * 0.85})` }} />
                ))}
              </div>
            ) : (
              <span className="record-hint">Up to 3 minutes</span>
            )}
          </>
        ) : (
          <>
            {audioUrl && <audio className="record-playback" src={audioUrl} controls aria-label="Your recording" />}
            <div className="record-actions">
              <button type="button" className="editorial-btn secondary" onClick={handleStartRecording} disabled={isProcessing}>
                <Mic size={15} />
                <span>Record again</span>
              </button>
              <button type="button" className="editorial-btn primary" onClick={handleSaveRecording} disabled={isProcessing}>
                {isProcessing ? 'Saving...' : 'Save memory'}
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
