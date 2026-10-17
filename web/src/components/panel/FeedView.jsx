import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { Play, Pause, PhoneCall, Sparkles, BookOpen, Clock, Heart, MessageCircle, HelpCircle, Shield, ChevronRight } from 'lucide-react';

export default function FeedView({ onOpenAskModal }) {
  const { setSelectedStoryId, setPanelSubTab, showToast, circleData, currentViewerId } = useApp();
  const [feedItems, setFeedItems] = useState([]);
  const [playingItemId, setPlayingItemId] = useState(null);
  const [disabledAudioMap, setDisabledAudioMap] = useState({}); // { [itemId]: true } if 403

  const audioElementRef = useRef(new Audio());
  const activeBlobMapRef = useRef({});

  useEffect(() => {
    async function loadFeed() {
      try {
        const data = await apiClient.getFeed();
        setFeedItems(data.items || []);
      } catch (err) {
        console.error("Feed load error:", err);
      }
    }
    loadFeed();

    const audio = audioElementRef.current;
    const handleEnded = () => setPlayingItemId(null);
    const handlePause = () => setPlayingItemId(null);
    audio.addEventListener('ended', handleEnded);
    audio.addEventListener('pause', handlePause);

    return () => {
      audio.pause();
      audio.removeEventListener('ended', handleEnded);
      audio.removeEventListener('pause', handlePause);
      Object.values(activeBlobMapRef.current).forEach(url => URL.revokeObjectURL(url));
    };
  }, [currentViewerId]);

  const handlePlayToggle = async (id, audioUrl) => {
    if (!audioUrl || disabledAudioMap[id]) return;

    const audio = audioElementRef.current;
    if (playingItemId === id) {
      audio.pause();
      setPlayingItemId(null);
      return;
    }

    try {
      let blobUrl = activeBlobMapRef.current[audioUrl];
      if (!blobUrl) {
        blobUrl = await apiClient.fetchAudioBlobUrl(audioUrl, currentViewerId);
        activeBlobMapRef.current[audioUrl] = blobUrl;
      }
      if (blobUrl) {
        audio.src = blobUrl;
        await audio.play();
        setPlayingItemId(id);
      }
    } catch (err) {
      console.warn("Audio play error:", err);
      // Requirement 10: If audio cannot be retrieved (403), disable play button without reason
      if (err.status === 403) {
        setDisabledAudioMap(prev => ({ ...prev, [id]: true }));
      }
    }
  };

  const handleOpenStory = (storyId) => {
    if (!storyId) return;
    setSelectedStoryId(storyId);
    setPanelSubTab('story');
  };

  const centerPerson = circleData?.members?.find(m => m.role === 'center');
  const centerName = centerPerson?.name || 'Fatma Hanım';

  return (
    <div className="feed-web-grid">
      {/* Main Stream Column */}
      <div className="feed-stream-col">
        <div className="feed-section-header">
          <div>
            <h2 className="section-title">Aile Akışı & Son Paylaşımlar</h2>
            <p className="section-subtitle">Evoca sabah sohbetlerinden gelen yanıtlar ve yeni yayınlanan anılar</p>
          </div>
          <span className="live-feed-badge">
            <span className="live-dot" /> Canlı
          </span>
        </div>

        <div className="feed-cards-list">
          {feedItems.length === 0 && (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
              Henüz paylaşılmış bir anı veya soru cevabı bulunmuyor.
            </div>
          )}

          {feedItems.map((item, idx) => {
            if (item.type === 'question_answered') {
              const isPlaying = playingItemId === item.question?.id;
              const hasAudio = !!item.answer?.audio_url;
              const isAudioDisabled = disabledAudioMap[item.question?.id];

              return (
                <article key={idx} className="feed-card answer-card">
                  <div className="feed-card-header">
                    <span className="feed-badge badge-answer">
                      <Sparkles size={13} /> {centerName}'dan Yanıt Geldi
                    </span>
                    <span className="feed-time">Sabah Oturumu</span>
                  </div>

                  <div className="question-quote-block">
                    <span className="quote-label">Sorulan Soru:</span>
                    <p className="question-text-quote">"{item.question?.text}"</p>
                  </div>

                  <div className="answer-content-box">
                    <h3
                      className="feed-story-title"
                      onClick={() => handleOpenStory(item.answer?.story_id)}
                      title="Hikâyeyi aç"
                    >
                      {item.answer?.story_title}
                    </h3>

                    {item.answer?.ai_summary && (
                      <div className="feed-ai-summary">
                        <span className="ai-tag-inline">Arşiv Özeti</span>
                        {item.answer.ai_summary}
                      </div>
                    )}

                    {/* Audio Snippet Player - Only if audio_url is not null (Requirement 10) */}
                    {hasAudio && (
                      <div className="mini-audio-player">
                        <button
                          className="play-toggle-btn"
                          onClick={() => handlePlayToggle(item.question?.id, item.answer.audio_url)}
                          disabled={isAudioDisabled}
                          title={isAudioDisabled ? "" : (isPlaying ? "Duraklat" : "Ses kaydını dinle")}
                          style={{
                            opacity: isAudioDisabled ? 0.35 : 1,
                            cursor: isAudioDisabled ? 'not-allowed' : 'pointer'
                          }}
                        >
                          {isPlaying ? <Pause size={18} /> : <Play size={18} style={{ marginLeft: '2px' }} />}
                        </button>
                        <div className="mini-waveform-bars">
                          {[5, 10, 16, 22, 12, 18, 24, 14, 8, 16, 22, 10, 15, 20, 8].map((h, i) => (
                            <div
                              key={i}
                              className={`wave-bar ${isPlaying ? 'playing' : ''}`}
                              style={{ height: `${h}px`, animationDelay: `${i * 0.05}s` }}
                            />
                          ))}
                        </div>
                        <span className="audio-duration-label">
                          {item.answer.duration_ms ? `${Math.round(item.answer.duration_ms / 1000)}s` : 'Ses'}
                        </span>
                      </div>
                    )}

                    {/* Call Grandma Banner */}
                    <div className="call-grandma-banner">
                      <div className="call-grandma-text">
                        💖 <strong>{centerName} sorunuzu yanıtladı!</strong> Belki onu şimdi aramak istersiniz?
                      </div>
                      <button
                        type="button"
                        className="call-btn"
                        onClick={() => showToast(`${centerName} aranıyor...`, "info")}
                      >
                        <PhoneCall size={14} /> Ara
                      </button>
                    </div>
                  </div>
                </article>
              );
            }

            if (item.type === 'story_published') {
              return (
                <article key={idx} className="feed-card story-card">
                  <div className="feed-card-header">
                    <span className="feed-badge badge-story">
                      <BookOpen size={13} /> Yeni Anı Yayınlandı
                    </span>
                    <span className="feed-time">Aile Çemberi Arşivi</span>
                  </div>

                  <h3
                    className="feed-story-title"
                    onClick={() => handleOpenStory(item.story?.id)}
                  >
                    {item.story?.title}
                  </h3>

                  <div className="feed-ai-summary">
                    <span className="ai-tag-inline">Arşiv Özeti</span>
                    {item.story?.ai_summary}
                  </div>

                  <div className="feed-story-footer">
                    <div className="story-meta-inline">
                      <Clock size={13} />
                      <span>{item.story?.teller?.name || centerName} tarafından anlatıldı</span>
                    </div>
                    <button
                      type="button"
                      className="read-story-btn"
                      onClick={() => handleOpenStory(item.story?.id)}
                    >
                      Dinle & İncele <ChevronRight size={14} />
                    </button>
                  </div>
                </article>
              );
            }

            return null;
          })}
        </div>
      </div>

      {/* Sidebar Column (Desktop Web) */}
      <aside className="feed-sidebar-col">
        {/* Elder Focus Card */}
        <div className="sidebar-card elder-status-card">
          <div className="elder-status-top">
            <div 
              style={{ 
                width: '48px', 
                height: '48px', 
                borderRadius: '50%', 
                background: 'var(--accent-terracotta)', 
                color: '#fff', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                fontWeight: 600,
                fontSize: '18px'
              }}
            >
              {centerName.charAt(0)}
            </div>
            <div>
              <div className="elder-name-title">{centerName}</div>
              <div className="elder-role-sub">Merkez Kişi · {centerPerson?.birth_year ? `Doğum ${centerPerson.birth_year}` : 'Aile Büyüğü'}</div>
            </div>
          </div>
          <div className="elder-chat-reminder">
            <Clock size={14} color="var(--accent-gold)" />
            <span>Günlük Sohbet: <strong>{circleData?.circle?.chat_time || '10:00'}</strong></span>
          </div>
          <p className="elder-card-desc">
            {centerName}, Echo Show cihazında ekrana dokunmadan Evoca ile sesli sohbet eder. Bıraktığınız sorular onun sabah hatıralarına ışık tutar.
          </p>
          <button
            type="button"
            className="sidebar-action-btn"
            onClick={() => onOpenAskModal && onOpenAskModal(null)}
          >
            + Soru Gönder
          </button>
        </div>

        {/* Privacy Guard Info */}
        <div className="sidebar-card privacy-guard-card">
          <div className="guard-header">
            <Shield size={16} color="var(--accent-emerald)" />
            <span className="guard-title">Hassas Konu & Gizlilik Koruması</span>
          </div>
          <p className="guard-desc">
            Evoca, ailenin hassas bulduğu konuları korur. Kişiye özel gizlenen veya henüz yayınlanmamış kayıtlar hiçbir üyeye sızdırılmaz.
          </p>
        </div>

        {/* Members mini list */}
        <div className="sidebar-card members-card">
          <div className="sidebar-card-title">
            Aile Çemberi ({circleData?.members?.length || 0} Üye)
          </div>
          <div className="members-mini-list">
            {(circleData?.members || []).map((m) => (
              <div key={m.id} className="member-item">
                <span className="m-avatar">
                  {m.role === 'center' ? '👵' : m.role === 'admin' ? '👩' : '👤'}
                </span>
                <div className="m-info">
                  <span className="m-name">{m.name}</span>
                  <span className="m-role">{m.relation_to_center || m.role}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
