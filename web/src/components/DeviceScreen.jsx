import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../context/AppContext';
import { apiClient } from '../api/client';
import { Mic, MicOff, Volume2, Sparkles, MessageSquare, Heart, CheckCircle2, XSquare, Play, RefreshCw } from 'lucide-react';

export default function DeviceScreen() {
  const { invitationData, centerPersonId, showToast, circleData } = useApp();
  const [isRecording, setIsRecording] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [currentTurn, setCurrentTurn] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [sessionActive, setSessionActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [deviceError, setDeviceError] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioPlayerRef = useRef(null);

  const centerName = circleData?.members?.find(m => m.id === centerPersonId)?.name || 'Fatma';

  // Play audio reply using blob URL with X-Person-Id = center
  const playAudioReply = async (audioUrl) => {
    if (!audioUrl) return;
    try {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
      }
      const blobUrl = await apiClient.fetchAudioBlobUrl(audioUrl, centerPersonId);
      if (blobUrl) {
        const audio = new Audio(blobUrl);
        audioPlayerRef.current = audio;
        audio.onplay = () => setIsPlayingAudio(true);
        audio.onended = () => setIsPlayingAudio(false);
        audio.onerror = () => setIsPlayingAudio(false);
        await audio.play();
      }
    } catch (err) {
      console.warn("Could not play reply audio:", err);
      // If 403 or unavailable, silent as per requirements
    }
  };

  // Start new device session (POST /api/device/session/start with X-Person-Id = center)
  const startSession = async () => {
    setLoading(true);
    setDeviceError(null);
    try {
      const turn = await apiClient.postDeviceSessionStart(centerPersonId);
      setCurrentTurn(turn);
      setSessionId(turn.session_id);
      setSessionActive(turn.session_open !== false);
      if (turn.reply_audio_url) {
        playAudioReply(turn.reply_audio_url);
      }
    } catch (err) {
      console.error("Device session start failed:", err);
      setDeviceError(err.message || "Cihaz oturumu başlatılamadı.");
      showToast(err.message || "Cihaz oturumu başlatılamadı.", "error");
    } finally {
      setLoading(false);
    }
  };

  // Automatically start device session on mount
  useEffect(() => {
    startSession();
    return () => {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
      }
    };
  }, [centerPersonId]);

  // Start real microphone recording
  const startRecording = async () => {
    if (!sessionActive && !sessionId) {
      await startSession();
    }
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
      showToast("Dinleniyor... (Konuşmanızı yapın)", "info");
    } catch {
      setIsRecording(true);
      showToast("Mikrofon erişimi alınamadı. Lütfen mikrofon iznini kontrol edin.", "error");
      setTimeout(() => {
        setIsRecording(false);
      }, 2000);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  // Submit spoken turn (POST /api/device/turn multipart: audio + session_id, no text field)
  const submitTurn = async (audioBlob) => {
    if (!audioBlob || audioBlob.size === 0) return;
    setLoading(true);
    try {
      const turn = await apiClient.postDeviceTurn(audioBlob, sessionId, centerPersonId);
      setCurrentTurn(turn);
      if (turn.session_id) setSessionId(turn.session_id);
      if (turn.session_open === false) {
        setSessionActive(false);
        showToast("Oturum tamamlandı.", "info");
      } else {
        setSessionActive(true);
      }

      if (turn.reply_audio_url) {
        playAudioReply(turn.reply_audio_url);
      }
    } catch (err) {
      console.error(err);
      showToast(err.message || "Konuşma iletilemedi", "error");
    } finally {
      setLoading(false);
    }
  };

  // End session (POST /api/device/session/end {"session_id": ...})
  const handleEndSession = async () => {
    if (!sessionId) return;
    try {
      await apiClient.postDeviceSessionEnd(sessionId, centerPersonId);
      setSessionActive(false);
      showToast("Oturum sonlandırıldı. Anılar arşivleniyor.", "info");
    } catch (err) {
      console.error(err);
      showToast(err.message || "Oturum sonlandırılamadı", "error");
    }
  };

  return (
    <div className="device-wrapper">
      {/* Echo Show Notification Light Bar (Glows when family invitation is waiting) */}
      {invitationData?.active && (
        <div className="device-ambient-glow" title="Aile daveti aktif: Işık yanıyor" />
      )}

      <div className="device-header">
        <div>
          <div className="device-time">10:00</div>
          <div className="device-date">Çarşamba · İstanbul · Living Room Echo</div>
        </div>

        {invitationData?.active && (
          <div className="device-invitation-banner">
            <Sparkles size={16} />
            <span>Davet: "{invitationData.invitation?.reason || 'Ailenizden yeni bir soru var'}"</span>
          </div>
        )}
      </div>

      <div className="device-content">
        <div className="device-speech-bubble-area">
          {deviceError && (
            <div className="elder-heard-card" style={{ borderColor: 'rgba(239, 68, 68, 0.4)' }}>
              <div className="elder-label" style={{ color: '#fca5a5' }}>Cihaz Bildirimi</div>
              <div className="elder-text">{deviceError}</div>
              <button
                type="button"
                className="quick-prompt-chip"
                style={{ marginTop: '12px' }}
                onClick={startSession}
              >
                <RefreshCw size={14} /> Yeniden Başlat
              </button>
            </div>
          )}

          {/* Center Person Heard Speech Bubble */}
          {currentTurn?.heard_text && (
            <div className="elder-heard-card">
              <div className="elder-label">{centerName} (Duyulan Sözler)</div>
              <div className="elder-text">"{currentTurn.heard_text}"</div>
            </div>
          )}

          {/* Evoca Agent Response Card */}
          {currentTurn?.reply_text && (
            <div className="agent-reply-card">
              <div className="agent-label">
                <Sparkles size={14} />
                Evoca Asistan
                {isPlayingAudio && (
                  <span style={{ color: 'var(--accent-gold)', marginLeft: '8px' }}>
                    ● Seslendiriliyor...
                  </span>
                )}
              </div>
              <div className="agent-text">{currentTurn.reply_text}</div>

              {/* Cards row for related reaction & question */}
              {currentTurn.cards && currentTurn.cards.length > 0 && (
                <div className="device-cards-row">
                  {currentTurn.cards.map((card, i) => (
                    <div key={i} className="device-subcard">
                      <div className="subcard-emoji">
                        {card.type === 'reaction' ? (
                          card.emoji === 'laugh' ? '😂' : card.emoji === 'heart' ? '❤️' : card.emoji === 'sad' ? '😢' : '🙏'
                        ) : '❓'}
                      </div>
                      <div>
                        <div className="subcard-title">
                          {card.type === 'reaction'
                            ? `${card.from?.name || 'Aile üyesi'} tepki bıraktı`
                            : `${card.asker?.name || 'Aile üyesi'} sordu`}
                        </div>
                        <div className="subcard-desc">
                          {card.type === 'reaction' ? `"${card.story_title || 'Hikâye'}" üzerine` : card.text}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {loading && (
            <div style={{ textAlign: 'center', padding: '16px', color: 'var(--accent-gold)' }}>
              Ses işleniyor ve yanıt hazırlanıyor...
            </div>
          )}
        </div>

        {/* Push-to-Talk and Session Action Bar */}
        <div className="device-bottom-action">
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
            <button
              className={`push-to-talk-btn ${isRecording ? 'recording' : ''}`}
              onMouseDown={startRecording}
              onMouseUp={stopRecording}
              onTouchStart={startRecording}
              onTouchEnd={stopRecording}
              disabled={loading}
              title="Basılı tutarak konuşun (Echo Show simülasyonu)"
            >
              {isRecording ? <MicOff className="ptt-icon" /> : <Mic className="ptt-icon" />}
              <span className="ptt-label">{isRecording ? "Dinliyor..." : "Basılı Tut ve Konuş"}</span>
            </button>

            {currentTurn?.reply_audio_url && (
              <button
                type="button"
                className="quick-prompt-chip"
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                onClick={() => playAudioReply(currentTurn.reply_audio_url)}
              >
                <Volume2 size={16} /> Yanıtı Dinle
              </button>
            )}

            {sessionActive && (
              <button
                type="button"
                className="quick-prompt-chip"
                style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: '#fca5a5' }}
                onClick={handleEndSession}
              >
                <XSquare size={16} /> Oturumu Bitir (Arşivle)
              </button>
            )}
          </div>

          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Echo Show Simülasyonu: {centerName} (center) kimliğiyle çalışır · Sadece gerçek ses gönderilir
          </div>
        </div>
      </div>
    </div>
  );
}
