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
  Plus
} from 'lucide-react';

export default function StoryView() {
  const { selectedStoryId, setSelectedStoryId, setPanelSubTab, showToast } = useApp();
  const [story, setStory] = useState(null);
  const [playlist, setPlaylist] = useState(null);
  const [showPlaylist, setShowPlaylist] = useState(true);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);

  // Audio simulation state
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentMs, setCurrentMs] = useState(0);
  const intervalRef = useRef(null);

  useEffect(() => {
    async function loadStory() {
      try {
        const idToLoad = selectedStoryId || 'story_mulberry';
        const [storyData, playlistData] = await Promise.all([
          apiClient.getStory(idToLoad),
          apiClient.getStoryPlaylist(idToLoad)
        ]);
        setStory(storyData);
        setPlaylist(playlistData);
        setCurrentMs(0);
        setIsPlaying(false);
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
      } catch (err) {
        console.error('Failed to load story:', err);
      }
    }
    loadStory();
  }, [selectedStoryId]);

  const durationMs = story?.duration_ms || 22000;

  // Audio Playback simulation with real-time word highlighting
  useEffect(() => {
    if (isPlaying) {
      intervalRef.current = setInterval(() => {
        setCurrentMs(prev => {
          if (prev >= durationMs) {
            setIsPlaying(false);
            return 0;
          }
          return prev + 100;
        });
      }, 100 / playbackSpeed);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [isPlaying, durationMs, playbackSpeed]);

  const togglePlay = () => {
    if (isPlaying) {
      setIsPlaying(false);
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    } else {
      setIsPlaying(true);
      if ('speechSynthesis' in window && story?.transcript?.[0]?.text) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(story.transcript[0].text);
        utterance.rate = playbackSpeed * 0.92;
        utterance.lang = 'en-US';
        utterance.onend = () => setIsPlaying(false);
        window.speechSynthesis.speak(utterance);
      }
    }
  };

  const handleWordClick = (startMs) => {
    setCurrentMs(startMs);
    setIsPlaying(true);
    showToast(`Jumped to ${(startMs / 1000).toFixed(1)}s`, 'info');
  };

  const handleToggleReaction = async (emojiKey) => {
    if (!story?.reactions) return;
    const isMine = story.reactions.mine?.includes(emojiKey);
    const action = isMine ? 'remove' : 'add';
    try {
      const res = await apiClient.postStoryReaction(story.id, emojiKey, action);
      setStory(prev => ({
        ...prev,
        reactions: {
          counts: res.counts,
          mine: res.mine
        }
      }));
      showToast(action === 'add' ? `Left reaction! It will be shared with Grandma.` : "Reaction removed", "info");
    } catch (err) {
      console.error(err);
    }
  };

  const handleShareStory = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(window.location.href);
      showToast("Story archive link copied to clipboard!", "info");
    } else {
      showToast("Story shared with Family Circle!", "info");
    }
  };

  if (!story) {
    return (
      <div className="story-loading-state">
        <div className="loading-spinner" />
        <p>Opening family heirloom memory...</p>
      </div>
    );
  }

  const segment = story.transcript?.[0];
  const words = segment?.words || [];

  return (
    <div className="story-archive-page">
      {/* 1. Top Breadcrumb & Return Bar */}
      <nav className="story-breadcrumb-nav" aria-label="Story navigation">
        <div className="breadcrumb-left">
          <button 
            type="button" 
            className="btn-story-back"
            onClick={() => setPanelSubTab('lifeline')}
          >
            <ArrowLeft size={16} />
            <span>Return to Life Chapters</span>
          </button>
          <span className="breadcrumb-separator">/</span>
          <span className="breadcrumb-active-period">
            {story.period_label || story.period || 'Family Archive'}
          </span>
        </div>

        <div className="breadcrumb-right">
          <span className="story-access-tag">
            <ShieldCheck size={14} />
            <span>Family Circle Private</span>
          </span>
          <button 
            type="button" 
            className="btn-story-share"
            onClick={handleShareStory}
            title="Share this memory with family"
          >
            <Share2 size={14} />
            <span>Share Memory</span>
          </button>
        </div>
      </nav>

      {/* 2. Story Title Header Banner */}
      <header className="story-hero-header">
        <div className="story-header-eyebrow">
          <span>ORAL FAMILY ARCHIVE</span>
          <span className="eyebrow-sep">·</span>
          <span>{story.period_label || 'Childhood Chapter'}</span>
          {story.year && <span className="eyebrow-sep">·</span>}
          {story.year && <span>CIRCA {story.year}</span>}
        </div>

        <h1 className="story-main-heading">{story.title}</h1>

        <div className="story-byline-meta-row">
          <div className="teller-info-badge">
            <img 
              src="/grandma_fatma.jpg" 
              alt={story.teller?.name || 'Grandma Fatma'}
              className="teller-avatar-circle"
              onError={(e) => {
                e.target.onerror = null;
                e.target.src = "/family_hero.jpg";
              }}
            />
            <div className="teller-text">
              <span className="teller-name">{story.teller?.name || 'Grandma Fatma'}</span>
              <span className="teller-role">Central Storyteller · Original Recording</span>
            </div>
          </div>

          <div className="story-meta-pills-cluster">
            {story.place && (
              <span className="meta-info-pill">
                <MapPin size={13} />
                <span>{story.place}</span>
              </span>
            )}
            <span className="meta-info-pill verified-pill">
              <Check size={13} />
              <span>Verified Family Record</span>
            </span>
          </div>
        </div>
      </header>

      {/* 3. Main Two-Column Editorial Grid */}
      <div className="story-two-column-showcase">
        {/* Left Column: Heirloom Photo, Bespoke Player, Interactive Timed Transcript */}
        <div className="story-listen-column">
          {/* Heirloom Archival Photograph */}
          {story.photo_url && (
            <div className="story-heirloom-frame">
              <div className="heirloom-matting">
                <img 
                  src={story.photo_url} 
                  alt={story.title} 
                  className="heirloom-image"
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = "/mulberry_memory.jpg";
                  }}
                />
              </div>
              <div className="heirloom-caption-bar">
                <span className="caption-text-handwriting">
                  {story.photo_caption || `${story.place || 'Akçaabat'}, circa ${story.year || 1956}`}
                </span>
              </div>
            </div>
          )}

          {/* Bespoke Archival Audio Player */}
          <section className="bespoke-audio-station" aria-label="Story audio player">
            <div className="station-top-bar">
              <div className="station-left">
                <button 
                  type="button" 
                  className={`station-play-btn ${isPlaying ? 'playing' : ''}`}
                  onClick={togglePlay}
                  aria-label={isPlaying ? "Pause audio recording" : "Play audio recording"}
                >
                  {isPlaying ? <Pause size={22} /> : <Play size={22} style={{ marginLeft: '3px' }} />}
                </button>

                <div className="station-track-info">
                  <div className="station-track-title">Grandma Fatma's Morning Voice</div>
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
                  onClick={() => setPlaybackSpeed(s => s === 1.0 ? 0.85 : s === 0.85 ? 1.15 : 1.0)}
                  title="Toggle playback speed"
                >
                  {playbackSpeed}x
                </button>

                <button 
                  type="button" 
                  className="station-restart-btn"
                  onClick={() => {
                    setCurrentMs(0);
                    setIsPlaying(false);
                    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
                  }}
                  title="Restart from beginning"
                >
                  <RotateCcw size={14} />
                  <span>Restart</span>
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
                const rect = e.currentTarget.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const pct = Math.max(0, Math.min(1, clickX / rect.width));
                setCurrentMs(Math.round(pct * durationMs));
              }}
            >
              <div 
                className="station-scrubber-fill"
                style={{ width: `${(currentMs / durationMs) * 100}%` }}
              >
                <div className="station-scrubber-pin" />
              </div>
            </div>
          </section>

          {/* Timed Speech-to-Text Interactive Transcript */}
          <section className="story-transcript-parchment" aria-label="Interactive transcript">
            <div className="transcript-parchment-header">
              <div className="parchment-title-group">
                <span className="parchment-tag">ORAL ARCHIVE TRANSCRIPT</span>
                <h3 className="parchment-title">Verbatim Morning Conversation</h3>
              </div>
              <span className="parchment-interactive-hint">
                💡 Click any word to jump audio
              </span>
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
                      title={`Jump to ${(item.start_ms / 1000).toFixed(1)}s`}
                    >
                      {item.w}{' '}
                    </span>
                  );
                })
              ) : (
                <p className="fallback-transcript-text">
                  {story.transcript?.[0]?.text || story.excerpt || story.ai_summary}
                </p>
              )}
            </div>
          </section>
        </div>

        {/* Right Column: AI Curator, Family Reactions, Connected Playlist, Retellings */}
        <aside className="story-side-showcase" aria-label="Story context and connections">
          {/* 1. AI Structured Summary Card */}
          <div className="side-archival-card curator-card">
            <div className="side-card-header">
              <div className="side-card-icon-gold">
                <Sparkles size={16} />
              </div>
              <h4 className="side-card-heading">Curator's Memory Synthesis</h4>
            </div>
            <p className="curator-summary-text">{story.ai_summary}</p>
            <div className="curator-tags-cluster">
              <span className="curator-tag">Heritage Memory</span>
              <span className="curator-tag">Oral Tradition</span>
              <span className="curator-tag">Akçaabat Living Archive</span>
            </div>
          </div>

          {/* 2. Family Heartbeats & Reactions */}
          <div className="side-archival-card reactions-card">
            <div className="side-card-header">
              <div className="side-card-icon-terracotta">
                <Heart size={16} />
              </div>
              <h4 className="side-card-heading">Family Reactions</h4>
            </div>
            <p className="reactions-instruction">
              Reactions are lovingly read aloud to Grandma during her morning coffee chat with Evoca.
            </p>

            <div className="reaction-emojis-grid">
              {[
                { key: 'heart', emoji: '❤️', label: 'Loved' },
                { key: 'laugh', emoji: '😂', label: 'Smiled' },
                { key: 'sad', emoji: '😢', label: 'Touched' },
                { key: 'pray', emoji: '🙏', label: 'Grateful' }
              ].map(r => {
                const count = story.reactions?.counts?.[r.key] || 0;
                const hasReacted = story.reactions?.mine?.includes(r.key);
                return (
                  <button
                    key={r.key}
                    type="button"
                    className={`reaction-heartbeat-btn ${hasReacted ? 'has-reacted' : ''}`}
                    onClick={() => handleToggleReaction(r.key)}
                    title={`React with ${r.label}`}
                  >
                    <span className="reaction-emoji">{r.emoji}</span>
                    <span className="reaction-label">{r.label}</span>
                    <span className="reaction-count">{count}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 3. "Baştan Dinle" Sequential Playlist */}
          <div className="side-archival-card playlist-card">
            <div className="side-card-header with-toggle">
              <div className="header-left">
                <div className="side-card-icon-sage">
                  <Headphones size={16} />
                </div>
                <h4 className="side-card-heading">Baştan Dinle · Connected Line</h4>
              </div>
              <button 
                type="button" 
                className="btn-toggle-playlist"
                onClick={() => setShowPlaylist(!showPlaylist)}
              >
                {showPlaylist ? "Collapse" : "Expand"}
              </button>
            </div>

            <p className="playlist-subtext">
              Plays connected family memories in chronological order, like an intimate family radio.
            </p>

            {showPlaylist && playlist && (
              <div className="playlist-episodes-list">
                {playlist.items.map((item, idx) => {
                  const isCurrent = item.story_id === story.id;
                  return (
                    <div 
                      key={idx} 
                      className={`playlist-episode-row ${isCurrent ? 'episode-current' : ''}`}
                      onClick={() => {
                        if (item.story_id && item.story_id !== story.id) {
                          setSelectedStoryId(item.story_id);
                        }
                      }}
                    >
                      <span className="episode-index">{String(idx + 1).padStart(2, '0')}</span>
                      <div className="episode-details">
                        <span className="episode-title">{item.title}</span>
                        <span className="episode-dur">{Math.round(item.end_ms / 1000)}s audio</span>
                      </div>
                      {isCurrent ? (
                        <span className="episode-badge">Now Playing</span>
                      ) : (
                        <ChevronRight size={14} className="episode-arrow" />
                      )}
                    </div>
                  );
                })}

                {playlist.skipped_count > 0 && (
                  <div className="playlist-tier-note">
                    🔒 {playlist.skipped_count} private recording skipped for your viewer tier.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 4. Family Retellings & Perspectives */}
          {story.retellings && story.retellings.length > 0 && (
            <div className="side-archival-card retellings-card">
              <div className="side-card-header">
                <div className="side-card-icon-purple">
                  <MessageSquare size={16} />
                </div>
                <h4 className="side-card-heading">Family Echoes & Retellings</h4>
              </div>

              <div className="retellings-stack">
                {story.retellings.map(ret => (
                  <div key={ret.id} className="retelling-bubble">
                    <h5 className="retelling-title">“{ret.title}”</h5>
                    <div className="retelling-byline">
                      Told by <strong>{ret.teller?.name}</strong> ({ret.teller?.relation_to_center})
                    </div>
                    <p className="retelling-note">{ret.relation_note}</p>
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
