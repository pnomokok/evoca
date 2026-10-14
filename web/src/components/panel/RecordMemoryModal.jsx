import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { X, Mic, MicOff, Check, Radio } from 'lucide-react';

export default function RecordMemoryModal({ isOpen, onClose }) {
  const { showToast } = useApp();
  const [isRecording, setIsRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (isRecording) {
      intervalRef.current = setInterval(() => {
        setRecordSeconds(s => s + 1);
      }, 1000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [isRecording]);

  if (!isOpen) return null;

  const handleToggleRecord = () => {
    if (isRecording) {
      setIsRecording(false);
      handleSaveRecording();
    } else {
      setRecordSeconds(0);
      setIsRecording(true);
      showToast("Recording audio memory...", "info");
    }
  };

  const handleSaveRecording = async () => {
    setIsProcessing(true);
    try {
      await apiClient.postRecording(null);
      showToast("Memory saved! AI will transcribe & connect to family lifeline.", "info");
      onClose();
    } catch (err) {
      console.error(err);
      showToast("Failed to save recording", "error");
    } finally {
      setIsProcessing(false);
      setRecordSeconds(0);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title-row">
          <div className="modal-title">Record Your Own Memory</div>
          <button className="close-btn" onClick={onClose}><X size={20} /></button>
        </div>

        <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
          Record your perspective of a shared family memory. Evoca will transcribe it, determine subjects, and link it with Grandma's archive.
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px', padding: '24px 0' }}>
          <div style={{ fontSize: '32px', fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: isRecording ? '#ef4444' : '#fff' }}>
            0:{recordSeconds < 10 ? `0${recordSeconds}` : recordSeconds}
          </div>

          <button
            className={`push-to-talk-btn ${isRecording ? 'recording' : ''}`}
            style={{ width: '90px', height: '90px' }}
            onClick={handleToggleRecord}
            disabled={isProcessing}
          >
            {isRecording ? <MicOff size={32} /> : <Mic size={32} />}
            <span className="ptt-label">{isRecording ? "Stop" : "Record"}</span>
          </button>

          {isRecording && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#f87171', fontSize: '12px' }}>
              <Radio size={14} className="pulseDot" /> Recording live voice...
            </div>
          )}

          {isProcessing && (
            <div style={{ fontSize: '13px', color: 'var(--accent-gold)' }}>
              Uploading to Archivist Agent...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
