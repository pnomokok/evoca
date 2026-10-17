import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { X, Mic, MicOff, Check, Radio, Lock, Users, AlertCircle } from 'lucide-react';

const MAX_RECORDING_SECONDS = 180; // 3 minutes maximum

export default function RecordMemoryModal({ isOpen, onClose }) {
  const { showToast, refreshData } = useApp();
  const [isRecording, setIsRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [access, setAccess] = useState('circle'); // 'circle' | 'private'
  const [audioBlob, setAudioBlob] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerRef = useRef(null);

  useEffect(() => {
    if (isRecording) {
      timerRef.current = setInterval(() => {
        setRecordSeconds(s => {
          if (s + 1 >= MAX_RECORDING_SECONDS) {
            handleStopRecording();
            return MAX_RECORDING_SECONDS;
          }
          return s + 1;
        });
      }, 1000);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [isRecording]);

  useEffect(() => {
    if (!isOpen) {
      setIsRecording(false);
      setRecordSeconds(0);
      setAudioBlob(null);
      setErrorMessage(null);
      setIsProcessing(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

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
      showToast("Kayıt başladı...", "info");
    } catch {
      setErrorMessage("Mikrofon erişimi sağlanamadı. Lütfen mikrofon izinlerini kontrol edin.");
    }
  };

  const handleStopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  const handleSaveRecording = async () => {
    if (!audioBlob || recordSeconds < 1) {
      setErrorMessage("Kayıt çok kısa veya boş.");
      return;
    }
    if (recordSeconds > MAX_RECORDING_SECONDS) {
      setErrorMessage("Kayıt en fazla 3 dakika olabilir.");
      return;
    }

    setIsProcessing(true);
    setErrorMessage(null);

    try {
      await apiClient.postRecording(audioBlob, access);
      showToast("Anın işleniyor. Kısa süre sonra akışa ve hayat çizgisine düşecektir.", "info");
      if (refreshData) refreshData();
      onClose();
    } catch (err) {
      console.error(err);
      setErrorMessage(err.message || "Anı kaydedilemedi.");
      showToast(err.message || "Anı kaydedilemedi", "error");
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
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-sheet archival-dialog" style={{ maxWidth: '480px' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-title-row">
          <div>
            <h2 className="archival-dialog-title">Kendi Anını Kaydet</h2>
            <p className="archival-dialog-sub">
              Aile hafızasına kendi bakış açınla bir sesli anı ekle.
            </p>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Kapat"><X size={20} /></button>
        </div>

        {/* Access Selector: Circle vs Private (Requirement 23) */}
        <div style={{ marginBottom: '20px', padding: '14px', background: 'var(--bg-secondary)', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
          <label className="form-label" style={{ marginBottom: '8px', display: 'block' }}>
            Erişim Gizliliği
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
                <div style={{ fontWeight: 600, fontSize: '13px' }}>Aile Çemberi</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Tüm aile dinleyebilir</div>
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
                <div style={{ fontWeight: 600, fontSize: '13px' }}>Sadece Ben</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Yalnızca sen dinleyebilirsin</div>
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
            En fazla 3 dakika (180s)
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
              <span className="ptt-label">{isRecording ? "Durdur" : "Kaydet"}</span>
            </button>
          ) : (
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <button
                type="button"
                className="editorial-btn secondary"
                onClick={handleStartRecording}
                disabled={isProcessing}
              >
                Yeniden Kaydet
              </button>
              <button
                type="button"
                className="editorial-btn primary"
                onClick={handleSaveRecording}
                disabled={isProcessing}
              >
                {isProcessing ? "İşleniyor..." : "Anıyı Gönder"}
              </button>
            </div>
          )}

          {isRecording && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#ef4444', fontSize: '12px' }}>
              <Radio size={14} className="pulseDot" /> Ses kaydediliyor...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
