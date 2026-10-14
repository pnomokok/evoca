import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../context/AppContext';
import { apiClient } from '../api/client';
import { Mic, MicOff, Volume2, Sparkles, MessageSquare, Heart, CheckCircle2, XSquare } from 'lucide-react';

export default function DeviceScreen() {
  const { invitationData, showToast } = useApp();
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [currentTurn, setCurrentTurn] = useState(null);
  const [sessionActive, setSessionActive] = useState(true);
  const [loading, setLoading] = useState(false);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // Fetch initial turn from mock
  useEffect(() => {
    async function loadTurn() {
      try {
        const turn = await apiClient.postDeviceTurn(null, "Alexa, what's new?");
        setCurrentTurn(turn);
      } catch (err) {
        console.error(err);
      }
    }
    loadTurn();
  }, []);

  // Speak agent reply aloud via SpeechSynthesis
  const speakReply = (text) => {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    utterance.pitch = 1.0;
    utterance.lang = 'en-US';
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utterance);
  };

  // Start real browser microphone recording or fallback
  const startRecording = async () => {
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
        await submitTurn(audioBlob, "I remember walking by the creek with my brother...");
      };

      mediaRecorder.start();
      setIsRecording(true);
      showToast("Listening... (Speak your story)", "info");
    } catch {
      // Microphone fallback
      setIsRecording(true);
      showToast("Mic access denied or unavailable. Simulating voice...", "info");
      setTimeout(() => {
        stopRecording("I remember walking by the creek with my brother...");
      }, 3000);
    }
  };

  const stopRecording = (fallbackText) => {
    setIsRecording(false);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    } else {
      submitTurn(null, fallbackText || "I was just thinking about our summer garden.");
    }
  };

  const submitTurn = async (audioBlob, text) => {
    setLoading(true);
    try {
      const turn = await apiClient.postDeviceTurn(audioBlob, text);
      setCurrentTurn(turn);
      setSessionActive(true);
      speakReply(turn.reply_text);
      showToast("Agent responded!", "info");
    } catch (err) {
      console.error(err);
      showToast("Failed to process spoken turn", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleEndSession = async () => {
    try {
      await apiClient.postDeviceSessionEnd(currentTurn?.session_id);
      setSessionActive(false);
      showToast("Session closed. Archivist Agent triggered to extract stories.", "info");
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="device-wrapper">
      {/* Echo Show Notification Light Bar (Glows when family invitation is waiting) */}
      {invitationData?.active && <div className="device-ambient-glow" title="Invitation active: Light is glowing" />}

      <div className="device-header">
        <div>
          <div className="device-time">10:00 AM</div>
          <div className="device-date">Wednesday, October 14 · Istanbul</div>
        </div>

        {invitationData?.active && (
          <div className="device-invitation-banner">
            <Sparkles size={16} />
            <span>Invitation: "{invitationData.invitation?.reason}"</span>
          </div>
        )}
      </div>

      <div className="device-content">
        <div className="device-speech-bubble-area">
          {/* Elder Heard Speech Bubble */}
          {currentTurn?.heard_text && (
            <div className="elder-heard-card">
              <div className="elder-label">Fatma (Spoken)</div>
              <div className="elder-text">"{currentTurn.heard_text}"</div>
            </div>
          )}

          {/* Evoca Agent Response Card */}
          {currentTurn?.reply_text && (
            <div className="agent-reply-card">
              <div className="agent-label">
                <Sparkles size={14} />
                Evoca Agent
                {isSpeaking && <span style={{ color: 'var(--accent-gold)', marginLeft: '8px' }}>● Speaking...</span>}
              </div>
              <div className="agent-text">{currentTurn.reply_text}</div>

              {/* Cards row for related reaction & question */}
              {currentTurn.cards && currentTurn.cards.length > 0 && (
                <div className="device-cards-row">
                  {currentTurn.cards.map((card, i) => (
                    <div key={i} className="device-subcard">
                      <div className="subcard-emoji">
                        {card.type === 'reaction' ? (card.emoji === 'laugh' ? '😂' : '❤️') : '❓'}
                      </div>
                      <div>
                        <div className="subcard-title">
                          {card.type === 'reaction'
                            ? `Reaction from ${card.from?.name}`
                            : `Question from ${card.asker?.name}`}
                        </div>
                        <div className="subcard-desc">
                          {card.type === 'reaction' ? `On "${card.story_title}"` : card.text}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Push-to-Talk and Session Action Bar */}
        <div className="device-bottom-action">
          <div className="device-quick-prompts">
            <button
              className="quick-prompt-chip"
              onClick={() => submitTurn(null, "Alexa, what's new?")}
            >
              "Alexa, what's new?"
            </button>
            <button
              className="quick-prompt-chip"
              onClick={() => submitTurn(null, "Elif, what was school like? It was very snowy in Akçaabat...")}
            >
              "School was 4 kilometers away in the snow..."
            </button>
            <button
              className="quick-prompt-chip"
              onClick={() => submitTurn(null, "Alexa, I remembered the big mulberry tree!")}
            >
              "I remembered the mulberry tree!"
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <button
              className={`push-to-talk-btn ${isRecording ? 'recording' : ''}`}
              onMouseDown={startRecording}
              onMouseUp={() => stopRecording()}
              onTouchStart={startRecording}
              onTouchEnd={() => stopRecording()}
              title="Press and hold to talk (Simulates Echo Show push-to-talk)"
            >
              {isRecording ? <MicOff className="ptt-icon" /> : <Mic className="ptt-icon" />}
              <span className="ptt-label">{isRecording ? "Listening" : "Hold to Talk"}</span>
            </button>

            {currentTurn?.reply_text && (
              <button
                className="quick-prompt-chip"
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                onClick={() => speakReply(currentTurn.reply_text)}
              >
                <Volume2 size={16} /> Replay Voice
              </button>
            )}

            {sessionActive && (
              <button
                className="quick-prompt-chip"
                style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: '#fca5a5' }}
                onClick={handleEndSession}
              >
                <XSquare size={16} /> End Session (Archive)
              </button>
            )}
          </div>

          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Echo Show Simulation: Big push-to-talk button, ambient notification lamp, voice playback
          </div>
        </div>
      </div>
    </div>
  );
}
