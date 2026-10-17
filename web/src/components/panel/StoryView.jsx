import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { 
  Play, 
  Pause, 
  RotateCcw, 
  MapPin, 
  Sparkles, 
  ArrowLeft, 
  Heart, 
  MessageSquare, 
  Share2, 
  ShieldCheck, 
  Check, 
  Headphones,
  Calendar,
  Volume2,
  Clock,
  ChevronRight,
  Plus,
  EyeOff,
  Lock,
  Users,
  AlertTriangle,
  X,
  Trash2,
  Edit3
} from 'lucide-react';

const PERIOD_LABELS = {
  childhood: 'Çocukluk (1948 – 1960)',
  youth: 'Gençlik (1961 – 1967)',
  marriage_early_years: 'İlk Evlilik Yılları (1968 – 1974)',
  raising_children: 'Aile Kurma (1975 – 1990)',
  midlife: 'Orta Yaş (1991 – 2008)',
  retirement: 'Emeklilik (2009 – Günümüz)'
};

export default function StoryView() {
  const { 
    selectedStoryId, 
    setSelectedStoryId, 
    setPanelSubTab, 
    currentViewerId, 
    showToast,
    refreshData 
  } = useApp();

  const [story, setStory] = useState(null);
  const [playlist, setPlaylist] = useState(null);
  const [showPlaylist, setShowPlaylist] = useState(true);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState(null);

  // Real Audio state
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentMs, setCurrentMs] = useState(0);
  const [durationMs, setDurationMs] = useState(0);
  const [audioBlobUrl, setAudioBlobUrl] = useState(null);
  const [audioDisabled, setAudioDisabled] = useState(false);
  const [activePlaylistIndex, setActivePlaylistIndex] = useState(0);
  const [isPlayingPlaylist, setIsPlayingPlaylist] = useState(false);

  // Modals
  const [showHideConfirm, setShowHideConfirm] = useState(false);
  const [isHiding, setIsHiding] = useState(false);
  const [showPeriodEditor, setShowPeriodEditor] = useState(false);
  const [selectedPeriod, setSelectedPeriod] = useState('');

  const audioElementRef = useRef(new Audio());

  // Load story and playlist
  useEffect(() => {
    let isCancelled = false;

    async function loadStoryData() {
      if (!selectedStoryId) return;
      setLoading(true);
      setErrorMessage(null);
      setIsPlaying(false);
      setCurrentMs(0);
      setAudioDisabled(false);
      if (audioBlobUrl) {
        URL.revokeObjectURL(audioBlobUrl);
        setAudioBlobUrl(null);
      }
      if (audioElementRef.current) {
        audioElementRef.current.pause();
      }

      try {
        const [storyData, playlistData] = await Promise.all([
          apiClient.getStory(selectedStoryId),
          apiClient.getStoryPlaylist(selectedStoryId).catch(() => null)
        ]);

        if (isCancelled) return;
        setStory(storyData);
        setPlaylist(playlistData);
        setDurationMs(storyData?.duration_ms || 30000);

        // Fetch audio blob with X-Person-Id header
        const audioSrc = storyData?.audio?.[0]?.url;
        if (audioSrc) {
          try {
            const blobUrl = await apiClient.fetchAudioBlobUrl(audioSrc, currentViewerId);
            if (!isCancelled) {
              setAudioBlobUrl(blobUrl);
              setAudioDisabled(false);
            }
          } catch (audioErr) {
            // Requirement 10: If audio cannot be retrieved (403), disable play button without reason
            console.warn("Audio fetch restricted or failed:", audioErr);
            if (!isCancelled) {
              setAudioDisabled(true);
            }
          }
        } else {
          setAudioDisabled(true);
        }
      } catch (err) {
        console.error('Failed to load story:', err);
        if (!isCancelled) {
          setErrorMessage(err.message || 'Bu hikâye bulunamadı');
        }
      } finally {
        if (!isCancelled) setLoading(false);
      }
    }

    loadStoryData();

    return () => {
      isCancelled = true;
      if (audioElementRef.current) {
        audioElementRef.current.pause();
      }
    };
  }, [selectedStoryId, currentViewerId]);

  // Bind real HTML5 Audio events
  useEffect(() => {
    const audio = audioElementRef.current;
    if (!audio) return;

    if (audioBlobUrl) {
      audio.src = audioBlobUrl;
      audio.playbackRate = playbackSpeed;
    }

    const handleTimeUpdate = () => {
      setCurrentMs(Math.round(audio.currentTime * 1000));
    };

    const handleEnded = () => {
      setIsPlaying(false);
      setCurrentMs(0);
      // If playlist is active, advance to next item
      if (isPlayingPlaylist && playlist?.items && activePlaylistIndex + 1 < playlist.items.length) {
        playPlaylistItem(activePlaylistIndex + 1);
      } else {
        setIsPlayingPlaylist(false);
      }
    };

    const handlePause = () => setIsPlaying(false);
    const handlePlay = () => setIsPlaying(true);

    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('ended', handleEnded);
    audio.addEventListener('pause', handlePause);
    audio.addEventListener('play', handlePlay);

    return () => {
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('ended', handleEnded);
      audio.removeEventListener('pause', handlePause);
      audio.removeEventListener('play', handlePlay);
    };
  }, [audioBlobUrl, isPlayingPlaylist, playlist, activePlaylistIndex]);

  // Play / Pause toggle
  const togglePlay = () => {
    if (audioDisabled || !audioBlobUrl) return;
    const audio = audioElementRef.current;
    if (isPlaying) {
      audio.pause();
    } else {
      audio.playbackRate = playbackSpeed;
      audio.play().catch(e => console.warn("Audio play prevented:", e));
    }
  };

  const handleWordClick = (startMs) => {
    if (audioDisabled || !audioBlobUrl) return;
    const audio = audioElementRef.current;
    audio.currentTime = startMs / 1000;
    audio.play().catch(e => console.warn(e));
  };

  const handleSpeedChange = () => {
    const nextSpeed = playbackSpeed === 1.0 ? 0.85 : playbackSpeed === 0.85 ? 1.15 : 1.0;
    setPlaybackSpeed(nextSpeed);
    if (audioElementRef.current) {
      audioElementRef.current.playbackRate = nextSpeed;
    }
  };

  const handleRestart = () => {
    const audio = audioElementRef.current;
    if (audio) {
      audio.currentTime = 0;
      setCurrentMs(0);
      if (isPlaying) {
        audio.play().catch(e => console.warn(e));
      }
    }
  };

  // Playlist item playback
  const playPlaylistItem = async (index) => {
    if (!playlist?.items?.[index]) return;
    const item = playlist.items[index];
    setActivePlaylistIndex(index);
    setIsPlayingPlaylist(true);

    try {
      const blobUrl = await apiClient.fetchAudioBlobUrl(item.url, currentViewerId);
      if (blobUrl) {
        setAudioBlobUrl(blobUrl);
        const audio = audioElementRef.current;
        audio.src = blobUrl;
        audio.currentTime = 0;
        await audio.play();
        showToast(`Çalınıyor: ${item.title}`, 'info');
      }
    } catch (err) {
      console.warn("Could not play playlist item:", err);
      showToast("Bu kayıt çalınamadı", "error");
    }
  };

  // Reactions: present and mine, NO counts!
  const handleToggleReaction = async (emojiKey) => {
    if (!story) return;
    const currentMine = story.reactions?.mine || [];
    const isMine = currentMine.includes(emojiKey);
    const action = isMine ? 'remove' : 'add';

    try {
      const res = await apiClient.postStoryReaction(story.id, emojiKey, action);
      setStory(prev => ({
        ...prev,
        reactions: {
          present: res.present || [],
          mine: res.mine || []
        }
      }));
      showToast(action === 'add' ? 'Tepki eklendi' : 'Tepki kaldırıldı', 'info');
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Tepki kaydedilemedi', 'error');
    }
  };

  // Change Access: "circle" | "private"
  const handleChangeAccess = async (newAccess) => {
    try {
      await apiClient.patchStory(story.id, { access: newAccess });
      setStory(prev => ({
        ...prev,
        access: { ...prev.access, type: newAccess }
      }));
      showToast(newAccess === 'private' ? 'Erişim: Sadece ben yapıldı' : 'Erişim: Aile çemberi yapıldı', 'info');
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Erişim değiştirilemedi', 'error');
    }
  };

  // Hide Story: PATCH {"hidden": true} -> returns to feed
  const handleConfirmHide = async () => {
    setIsHiding(true);
    try {
      await apiClient.patchStory(story.id, { hidden: true });
      showToast('Hikâye gizlendi', 'info');
      setShowHideConfirm(false);
      setPanelSubTab('feed');
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Hikâye gizlenemedi', 'error');
    } finally {
      setIsHiding(false);
    }
  };

  // Delete wrong link: DELETE /api/links/{link_id}
  const handleDeleteLink = async (linkId) => {
    try {
      await apiClient.deleteLink(linkId);
      setStory(prev => ({
        ...prev,
        linked_stories: (prev.linked_stories || []).filter(l => l.link_id !== linkId)
      }));
      showToast('Yanlış bağlantı kaldırıldı', 'info');
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Bağlantı kaldırılamadı', 'error');
    }
  };

  // Correct period: PATCH /api/stories/{id}/subjects/{person_id}
  const handleSavePeriod = async () => {
    const subject = story.subjects?.[0];
    if (!subject || !selectedPeriod) return;

    try {
      await apiClient.patchStorySubject(story.id, subject.person_id, selectedPeriod);
      setStory(prev => ({
        ...prev,
        subjects: (prev.subjects || []).map(s => 
          s.person_id === subject.person_id
            ? { ...s, period: selectedPeriod, period_source: 'family', estimated: false }
            : s
        )
      }));
      setShowPeriodEditor(false);
      showToast('Dönem güncellendi', 'info');
      if (refreshData) refreshData();
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Dönem güncellenemedi', 'error');
    }
  };

  const handleShareStory = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(window.location.href);
      showToast("Hikâye arşivi bağlantısı panoya kopyalandı!", "info");
    } else {
      showToast("Bağlantı kopyalandı", "info");
    }
  };

  if (loading) {
    return (
      <div className="story-loading-state">
        <div className="loading-spinner" />
        <p>Aile yadigarı anı açılıyor...</p>
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div className="story-loading-state" style={{ padding: '60px 20px', textAlign: 'center' }}>
        <AlertTriangle size={36} color="var(--accent-terracotta)" style={{ marginBottom: '16px' }} />
        <h2 style={{ fontSize: '20px', marginBottom: '8px' }}>{errorMessage}</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: '24px' }}>
          Aradığınız kayıt görüntülenemiyor veya erişim yetkiniz bulunmuyor.
        </p>
        <button 
          className="editorial-btn primary"
          onClick={() => setPanelSubTab('feed')}
        >
          <ArrowLeft size={16} /> Aile Akışına Dön
        </button>
      </div>
    );
  }

  if (!story) return null;

  const segment = story.transcript?.[0];
  const words = segment?.words || [];
  const primarySubject = story.subjects?.[0];
  const isEstimated = primarySubject?.estimated || primarySubject?.period_source === 'ai';
  const periodKey = primarySubject?.period || story.period;
  const periodDisplay = PERIOD_LABELS[periodKey] || periodKey || 'Aile Arşivi';

  return (
    <div className="story-archive-page">
      {/* 1. Top Breadcrumb & Return Bar */}
      <nav className="story-breadcrumb-nav" aria-label="Story navigation">
        <div className="breadcrumb-left">
          <button 
            type="button" 
            className="btn-story-back"
            onClick={() => setPanelSubTab('feed')}
          >
            <ArrowLeft size={16} />
            <span>Akışa Dön</span>
          </button>
          <span className="breadcrumb-separator">/</span>
          <span className="breadcrumb-active-period">
            {periodDisplay}
          </span>
          {isEstimated && (
            <span className="meta-info-pill" style={{ marginLeft: '8px', fontSize: '11px', background: 'rgba(217, 119, 6, 0.15)', color: '#d97706', borderColor: 'rgba(217, 119, 6, 0.3)' }}>
              tahmini
            </span>
          )}
        </div>

        <div className="breadcrumb-right">
          {/* Access status & change access option (if can_change_access) */}
          {story.can_change_access ? (
            <div className="access-select-wrapper" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label htmlFor="story-access-select" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Erişim:
              </label>
              <select
                id="story-access-select"
                className="archival-select"
                value={story.access?.type || 'circle'}
                onChange={(e) => handleChangeAccess(e.target.value)}
                style={{ fontSize: '12px', padding: '4px 10px' }}
              >
                <option value="circle">Aile Çemberi</option>
                <option value="private">Sadece Ben</option>
              </select>
            </div>
          ) : (
            <span className="story-access-tag">
              {story.access?.type === 'private' ? <Lock size={14} /> : <Users size={14} />}
              <span>{story.access?.type === 'private' ? 'Sadece Ben' : 'Aile Çemberi'}</span>
            </span>
          )}

          {/* Hide button if can_hide is true */}
          {story.can_hide && (
            <button
              type="button"
              className="editorial-btn secondary"
              style={{ padding: '6px 12px', fontSize: '12px', borderColor: 'rgba(239, 68, 68, 0.4)', color: '#ef4444' }}
              onClick={() => setShowHideConfirm(true)}
              title="Bu hikâyeyi gizle"
            >
              <EyeOff size={14} />
              <span>Gizle</span>
            </button>
          )}

          <button 
            type="button" 
            className="btn-story-share"
            onClick={handleShareStory}
            title="Hikâye bağlantısını kopyala"
          >
            <Share2 size={14} />
            <span>Paylaş</span>
          </button>
        </div>
      </nav>

      {/* Confirmation Modal for Hiding Story */}
      {showHideConfirm && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-sheet archival-dialog" style={{ maxWidth: '440px' }}>
            <div className="modal-title-row">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444' }}>
                <AlertTriangle size={20} />
                <h3 className="archival-dialog-title" style={{ margin: 0 }}>Hikâyeyi Gizle</h3>
              </div>
              <button className="close-btn" onClick={() => setShowHideConfirm(false)}>
                <X size={18} />
              </button>
            </div>
            <p style={{ fontSize: '14px', lineHeight: '1.6', margin: '16px 0', color: 'var(--text-secondary)' }}>
              Bu hikâyeyi gizlemek istediğinize emin misiniz? <strong>Bu işlem geri alınamaz.</strong> Gizlendikten sonra anlatan dışındaki herkes için bu kayıt artık bulunamayacaktır.
            </p>
            <div className="dialog-action-bar">
              <button 
                type="button" 
                className="editorial-btn secondary" 
                onClick={() => setShowHideConfirm(false)}
                disabled={isHiding}
              >
                Vazgeç
              </button>
              <button 
                type="button" 
                className="editorial-btn primary" 
                style={{ backgroundColor: '#dc2626', borderColor: '#b91c1c', color: '#fff' }}
                onClick={handleConfirmHide}
                disabled={isHiding}
              >
                {isHiding ? "Gizleniyor..." : "Evet, Gizle"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Period Correction Modal */}
      {showPeriodEditor && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-sheet archival-dialog" style={{ maxWidth: '440px' }}>
            <div className="modal-title-row">
              <h3 className="archival-dialog-title">Hayat Dönemini Düzelt</h3>
              <button className="close-btn" onClick={() => setShowPeriodEditor(false)}>
                <X size={18} />
              </button>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '14px' }}>
              Bu anının ait olduğu doğru hayat dönemini seçin:
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '20px' }}>
              {Object.entries(PERIOD_LABELS).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  className={`period-select-option ${selectedPeriod === k ? 'selected' : ''}`}
                  onClick={() => setSelectedPeriod(k)}
                  style={{ textAlign: 'left', padding: '10px 14px', borderRadius: '8px' }}
                >
                  <span className="opt-label">{label}</span>
                </button>
              ))}
            </div>
            <div className="dialog-action-bar">
              <button type="button" className="editorial-btn secondary" onClick={() => setShowPeriodEditor(false)}>
                İptal
              </button>
              <button type="button" className="editorial-btn primary" onClick={handleSavePeriod} disabled={!selectedPeriod}>
                Kaydet
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 2. Story Title Header Banner */}
      <header className="story-hero-header">
        <div className="story-header-eyebrow">
          <span>AİLE SÖZLÜ TARİHİ</span>
          <span className="eyebrow-sep">·</span>
          <span>{periodDisplay}</span>
          {isEstimated && (
            <>
              <span className="eyebrow-sep">·</span>
              <span style={{ color: '#d97706' }}>tahmini</span>
            </>
          )}
          {story.place && <span className="eyebrow-sep">·</span>}
          {story.place && <span>{story.place}</span>}
        </div>

        <h1 className="story-main-heading">{story.title}</h1>

        {/* Private Part Notice (teller only) */}
        {story.has_private_part && (
          <div 
            style={{ 
              display: 'inline-flex', 
              alignItems: 'center', 
              gap: '6px', 
              margin: '8px 0 16px', 
              padding: '6px 12px', 
              background: 'rgba(120, 53, 15, 0.15)', 
              border: '1px solid rgba(180, 83, 9, 0.3)', 
              borderRadius: '6px', 
              fontSize: '13px', 
              color: '#b45309' 
            }}
          >
            <Lock size={14} />
            <span>Bu hikâyenin bir kısmı gizli.</span>
          </div>
        )}

        <div className="story-byline-meta-row">
          <div className="teller-info-badge">
            <div className="teller-avatar-circle" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--accent-terracotta)', color: '#fff', fontWeight: 600 }}>
              {story.teller?.name?.charAt(0) || 'F'}
            </div>
            <div className="teller-text">
              <span className="teller-name">{story.teller?.name || 'Fatma Yilmaz'}</span>
              <span className="teller-role">Anlatan · Orijinal Kayıt</span>
            </div>
          </div>

          <div className="story-meta-pills-cluster">
            {primarySubject && (
              <button
                type="button"
                className="meta-info-pill"
                onClick={() => {
                  setSelectedPeriod(primarySubject.period);
                  setShowPeriodEditor(true);
                }}
                title="Dönemi düzelt"
                style={{ cursor: 'pointer' }}
              >
                <Edit3 size={12} />
                <span>{periodDisplay} {isEstimated ? '(tahmini)' : ''}</span>
              </button>
            )}
            <span className="meta-info-pill verified-pill">
              <Check size={13} />
              <span>Evoca Aile Kaydı</span>
            </span>
          </div>
        </div>
      </header>

      {/* 3. Main Two-Column Showcase Grid */}
      <div className="story-two-column-showcase">
        {/* Left Column: Audio Station and Timed Transcript */}
        <div className="story-listen-column">
          {/* Audio Player Station */}
          <section className="bespoke-audio-station" aria-label="Story audio player">
            <div className="station-top-bar">
              <div className="station-left">
                <button 
                  type="button" 
                  className={`station-play-btn ${isPlaying ? 'playing' : ''}`}
                  onClick={togglePlay}
                  disabled={audioDisabled}
                  aria-label={audioDisabled ? "Ses kullanılamıyor" : isPlaying ? "Duraklat" : "Oynat"}
                  title={audioDisabled ? "Ses kullanılamıyor" : isPlaying ? "Duraklat" : "Oynat"}
                  style={{ opacity: audioDisabled ? 0.45 : 1, cursor: audioDisabled ? 'not-allowed' : 'pointer' }}
                >
                  {isPlaying ? <Pause size={22} /> : <Play size={22} style={{ marginLeft: '3px' }} />}
                </button>

                <div className="station-track-info">
                  <div className="station-track-title">{story.teller?.name || 'Fatma Hanım'}'ın Ses Kaydı</div>
                  <div className="station-time-readout">
                    <span className="time-current">{(currentMs / 1000).toFixed(1)}s</span>
                    <span className="time-sep">/</span>
                    <span className="time-total">{(durationMs / 1000).toFixed(1)}s</span>
                  </div>
                </div>
              </div>

              <div className="station-controls-right">
                <button 
                  type="button" 
                  className="station-speed-btn"
                  onClick={handleSpeedChange}
                  disabled={audioDisabled}
                  title="Oynatma hızı"
                >
                  {playbackSpeed}x
                </button>

                <button 
                  type="button" 
                  className="station-restart-btn"
                  onClick={handleRestart}
                  disabled={audioDisabled}
                  title="Başa sar"
                >
                  <RotateCcw size={14} />
                  <span>Başa sar</span>
                </button>
              </div>
            </div>

            {/* Interactive Scrubber Waveform Bar */}
            <div 
              className="station-scrubber-track"
              role="slider"
              aria-label="Audio scrubber"
              aria-valuemin="0"
              aria-valuemax={durationMs}
              aria-valuenow={currentMs}
              onClick={(e) => {
                if (audioDisabled || !audioBlobUrl) return;
                const rect = e.currentTarget.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const pct = Math.max(0, Math.min(1, clickX / rect.width));
                const targetMs = Math.round(pct * durationMs);
                setCurrentMs(targetMs);
                if (audioElementRef.current) {
                  audioElementRef.current.currentTime = targetMs / 1000;
                }
              }}
              style={{ opacity: audioDisabled ? 0.4 : 1, cursor: audioDisabled ? 'not-allowed' : 'pointer' }}
            >
              <div 
                className="station-scrubber-fill"
                style={{ width: `${Math.min(100, (currentMs / (durationMs || 1)) * 100)}%` }}
              >
                <div className="station-scrubber-pin" />
              </div>
            </div>
          </section>

          {/* Timed Speech-to-Text Interactive Transcript */}
          <section className="story-transcript-parchment" aria-label="Interactive transcript">
            <div className="transcript-parchment-header">
              <div className="parchment-title-group">
                <span className="parchment-tag">SÖZLÜ ARŞİV TRANSKRİPTİ</span>
                <h3 className="parchment-title">Birebir Sabah Konuşması</h3>
              </div>
              {!audioDisabled && (
                <span className="parchment-interactive-hint">
                  💡 Kelimelere tıklayarak sese atlayabilirsiniz
                </span>
              )}
            </div>

            <div className="transcript-spoken-content">
              {words.length > 0 ? (
                words.map((item, idx) => {
                  const isActive = currentMs >= item.start_ms && currentMs <= item.end_ms;
                  return (
                    <span
                      key={idx}
                      className={`spoken-word ${isActive ? 'word-active' : ''}`}
                      onClick={() => handleWordClick(item.start_ms)}
                      title={`Atla: ${(item.start_ms / 1000).toFixed(1)}s`}
                      style={{ cursor: audioDisabled ? 'default' : 'pointer' }}
                    >
                      {item.w}{' '}
                    </span>
                  );
                })
              ) : (
                <p className="fallback-transcript-text">
                  {story.transcript?.[0]?.text || story.ai_summary || "Transkript henüz oluşturulmadı."}
                </p>
              )}
            </div>
          </section>
        </div>

        {/* Right Column: AI Curator, Reactions (NO counts), Playlist, Linked Stories */}
        <aside className="story-side-showcase" aria-label="Story context and connections">
          {/* AI Structured Summary Card */}
          <div className="side-archival-card curator-card">
            <div className="side-card-header">
              <div className="side-card-icon-gold">
                <Sparkles size={16} />
              </div>
              <h4 className="side-card-heading">Arşiv Özeti</h4>
            </div>
            <p className="curator-summary-text">{story.ai_summary}</p>
            <div className="curator-tags-cluster">
              <span className="curator-tag">Sözlü Bellek</span>
              <span className="curator-tag">{periodDisplay}</span>
            </div>
          </div>

          {/* Family Reactions Card (Requirement 15: NO COUNTS ANYWHERE) */}
          <div className="side-archival-card reactions-card">
            <div className="side-card-header">
              <div className="side-card-icon-terracotta">
                <Heart size={16} />
              </div>
              <h4 className="side-card-heading">Aile Tepkileri</h4>
            </div>
            <p className="reactions-instruction">
              Bıraktığınız tepkiler, Fatma Hanım'a sabah kahvesi sohbetinde Evoca tarafından okunur.
            </p>

            <div className="reaction-emojis-grid">
              {[
                { key: 'heart', emoji: '❤️', label: 'Sevdim' },
                { key: 'laugh', emoji: '😂', label: 'Gülümsedim' },
                { key: 'sad', emoji: '😢', label: 'Duygulandım' },
                { key: 'pray', emoji: '🙏', label: 'Minnettarım' }
              ].map(r => {
                const isPresent = story.reactions?.present?.includes(r.key);
                const isMine = story.reactions?.mine?.includes(r.key);

                return (
                  <button
                    key={r.key}
                    type="button"
                    className={`reaction-heartbeat-btn ${isMine ? 'has-reacted' : ''} ${isPresent ? 'is-present' : ''}`}
                    onClick={() => handleToggleReaction(r.key)}
                    title={isMine ? 'Tepkimi kaldır' : `${r.label} tepkisi bırak`}
                    style={{
                      borderWidth: isMine ? '2px' : '1px',
                      borderColor: isMine ? 'var(--accent-terracotta)' : isPresent ? 'rgba(217, 119, 6, 0.4)' : undefined,
                      backgroundColor: isMine ? 'rgba(194, 65, 12, 0.12)' : isPresent ? 'rgba(217, 119, 6, 0.05)' : undefined
                    }}
                  >
                    <span className="reaction-emoji">{r.emoji}</span>
                    <span className="reaction-label">{r.label}</span>
                    {/* NO counts anywhere as per requirement 15 */}
                  </button>
                );
              })}
            </div>
          </div>

          {/* "Baştan Dinle" Playlist (Requirement 21: Play sequentially, NO skipped_count) */}
          {playlist?.items && playlist.items.length > 0 && (
            <div className="side-archival-card playlist-card">
              <div className="side-card-header with-toggle">
                <div className="header-left">
                  <div className="side-card-icon-sage">
                    <Headphones size={16} />
                  </div>
                  <h4 className="side-card-heading">Baştan Dinle · Bağlantılı Kayıtlar</h4>
                </div>
                <button 
                  type="button" 
                  className="btn-toggle-playlist"
                  onClick={() => setShowPlaylist(!showPlaylist)}
                >
                  {showPlaylist ? "Daralt" : "Genişlet"}
                </button>
              </div>

              <p className="playlist-subtext">
                Bağlantılı aile anılarını sırayla dinleyin.
              </p>

              {showPlaylist && (
                <div className="playlist-episodes-list">
                  {playlist.items.map((item, idx) => {
                    const isCurrent = (isPlayingPlaylist && activePlaylistIndex === idx) || (!isPlayingPlaylist && item.story_id === story.id);
                    return (
                      <div 
                        key={idx} 
                        className={`playlist-episode-row ${isCurrent ? 'episode-current' : ''}`}
                        onClick={() => {
                          if (item.story_id && item.story_id !== story.id) {
                            setSelectedStoryId(item.story_id);
                          } else {
                            playPlaylistItem(idx);
                          }
                        }}
                        style={{ cursor: 'pointer' }}
                      >
                        <span className="episode-index">{String(idx + 1).padStart(2, '0')}</span>
                        <div className="episode-details">
                          <span className="episode-title">{item.title}</span>
                          <span className="episode-dur">{Math.round((item.end_ms - item.start_ms) / 1000)}s ses</span>
                        </div>
                        {isCurrent ? (
                          <span className="episode-badge">Oynatılıyor</span>
                        ) : (
                          <ChevronRight size={14} className="episode-arrow" />
                        )}
                      </div>
                    );
                  })}
                  {/* Notice: No skipped_count as per requirement 21 */}
                </div>
              )}
            </div>
          )}

          {/* Linked Stories (Requirement 20: Yanlış bağlantı DELETE /api/links/{id}) */}
          {story.linked_stories && story.linked_stories.length > 0 && (
            <div className="side-archival-card" style={{ padding: '16px', background: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <div className="side-card-header" style={{ marginBottom: '12px' }}>
                <h4 className="side-card-heading" style={{ fontSize: '14px', fontWeight: 600 }}>Bağlantılı Hikâyeler</h4>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {story.linked_stories.map((l) => (
                  <div 
                    key={l.link_id} 
                    style={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center', 
                      padding: '8px 12px', 
                      background: 'var(--bg-primary)', 
                      borderRadius: '8px', 
                      border: '1px solid var(--border-color)',
                      fontSize: '13px'
                    }}
                  >
                    <div>
                      <div 
                        style={{ fontWeight: 500, cursor: 'pointer', color: 'var(--text-primary)' }}
                        onClick={() => l.story?.id && setSelectedStoryId(l.story.id)}
                      >
                        {l.story?.title || 'Bağlantılı Hikâye'}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        {l.reason === 'same_place' ? 'Aynı Yer' : l.reason === 'same_event' ? 'Aynı Olay' : 'İlişkili'}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="editorial-btn secondary"
                      style={{ fontSize: '11px', padding: '4px 8px', borderColor: 'rgba(239, 68, 68, 0.3)', color: '#ef4444' }}
                      onClick={() => handleDeleteLink(l.link_id)}
                      title="Bu bağlantıyı kaldır"
                    >
                      Yanlış bağlantı
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Retellings (Requirement 20) */}
          {story.retellings && story.retellings.length > 0 && (
            <div className="side-archival-card retellings-card">
              <div className="side-card-header">
                <div className="side-card-icon-purple">
                  <MessageSquare size={16} />
                </div>
                <h4 className="side-card-heading">Aile Yankıları & Yeniden Anlatımlar</h4>
              </div>

              <div className="retellings-stack">
                {story.retellings.map(ret => (
                  <div key={ret.id} className="retelling-bubble">
                    <h5 
                      className="retelling-title" 
                      style={{ cursor: 'pointer' }}
                      onClick={() => setSelectedStoryId(ret.id)}
                    >
                      “{ret.title}”
                    </h5>
                    <div className="retelling-byline">
                      Anlatan: <strong>{ret.teller?.name}</strong> {ret.teller?.relation_to_center ? `(${ret.teller.relation_to_center})` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
