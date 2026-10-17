import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import { X, Mic, MicOff, Radio, Lock, Users, AlertCircle } from 'lucide-react';
import Modal from '../Modal';

const MAX_RECORDING_SECONDS = 180; // 3 minutes maximum

// Mounted only while open (see FamilyPanel), so every opening starts from fresh state.
export default function RecordMemoryModal({ onClose }) {
  const { showToast, refreshData } = useApp();
  const [isRecording, setIsRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [access, setAccess] = useState('circle'); // 'circle' | 'private'
  const [audioBlob, setAudioBlob] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timersRef = useRef({ tick: null, limit: null });

  const clearTimers = () => {
    clearInterval(timersRef.current.tick);
    clearTimeout(timersRef.current.limit);
  };

  const handleStopRecording = () => {
    clearTimers();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  // Stop the microphone if the dialog closes mid-recording.
  useEffect(() => {
    const timers = timersRef.current;
    const recorderRef = mediaRecorderRef;
    return () => {
      clearInterval(timers.tick);
      clearTimeout(timers.limit);
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
    };
  }, []);

  const handleStartRecording = async () => {
    setErrorMessage(null);
    setAudioBlob(null);
    setRecordSeconds(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
    <Modal onClose={onClose} label="Record your own memory" sheetStyle={{ maxWidth: '480px' }}>
        <div className="modal-title-row">
          <div>
            <h2 className="archival-dialog-title">Record your own memory</h2>
            <p className="archival-dialog-sub">
              Add a memory in your own voice to the family archive.
            </p>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </div>

        {/* Access Selector: Circle vs Private (Requirement 23) */}
        <div style={{ marginBottom: '20px', padding: '14px', background: 'var(--bg-secondary)', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
          <label className="form-label" style={{ marginBottom: '8px', display: 'block' }}>
            Who can listen
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <button
              type="button"
              className={`period-select-option ${access === 'circle' ? 'selected' : ''}`}
              onClick={() => setAccess('circle')}
              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 12px' }}
            >
              <Users size={16} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontWeight: 600, fontSize: '13px' }}>Family circle</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Everyone in the family</div>
              </div>
            </button>

            <button
              type="button"
              className={`period-select-option ${access === 'private' ? 'selected' : ''}`}
              onClick={() => setAccess('private')}
              style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 12px' }}
            >
              <Lock size={16} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontWeight: 600, fontSize: '13px' }}>Only me</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Only you can listen</div>
              </div>
            </button>
          </div>
        </div>

        {errorMessage && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444', fontSize: '13px', marginBottom: '16px' }}>
            <AlertCircle size={16} />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Recording Interface */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px', padding: '12px 0 24px' }}>
          <div style={{ fontSize: '36px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: isRecording ? '#ef4444' : 'var(--text-primary)' }}>
            {formatTime(recordSeconds)}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Up to 3 minutes
          </div>

          {!audioBlob ? (
            <button
              type="button"
              className={`push-to-talk-btn ${isRecording ? 'recording' : ''}`}
              style={{ width: '84px', height: '84px' }}
              onClick={isRecording ? handleStopRecording : handleStartRecording}
              disabled={isProcessing}
            >
              {isRecording ? <MicOff size={28} /> : <Mic size={28} />}
              <span className="ptt-label">{isRecording ? "Stop" : "Record"}</span>
            </button>
          ) : (
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <button
                type="button"
                className="editorial-btn secondary"
                onClick={handleStartRecording}
                disabled={isProcessing}
              >
                Record again
              </button>
              <button
                type="button"
                className="editorial-btn primary"
                onClick={handleSaveRecording}
                disabled={isProcessing}
              >
                {isProcessing ? "Saving..." : "Save memory"}
              </button>
            </div>
          )}

          {isRecording && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#ef4444', fontSize: '12px' }}>
              <Radio size={14} className="pulseDot" /> Recording...
            </div>
          )}
        </div>
    </Modal>
  );
}
