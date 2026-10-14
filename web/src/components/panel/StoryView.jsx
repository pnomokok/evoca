import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { Play, Pause, RotateCcw, ListMusic, MapPin, Sparkles, ArrowLeft, Heart, MessageSquare, Share2, ShieldCheck, Check, Headphones } from 'lucide-react';

export default function StoryView() {
  const { selectedStoryId, setPanelSubTab, showToast } = useApp();
  const [story, setStory] = useState(null);
  const [playlist, setPlaylist] = useState(null);
  const [showPlaylist, setShowPlaylist] = useState(true);

  // Audio simulation state
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentMs, setCurrentMs] = useState(0);
  const durationMs = 14200; // total active speech duration in milliseconds
  const intervalRef = useRef(null);

  useEffect(() => {
    async function loadStory() {
      try {
        const [storyData, playlistData] = await Promise.all([
          apiClient.getStory(selectedStoryId),
          apiClient.getStoryPlaylist(selectedStoryId)
        ]);
        setStory(storyData);
        setPlaylist(playlistData);
      } catch (err) {
        console.error(err);
      }
    }
    loadStory();
  }, [selectedStoryId]);

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
      }, 100);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [isPlaying]);

  const togglePlay = () => {
    if (isPlaying) {
      setIsPlaying(false);
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    } else {
      setIsPlaying(true);
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(story.transcript[0].text);
        utterance.rate = 0.95;
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

  const handleToggleReaction = async (emoji) => {
    const isMine = story.reactions.mine.includes(emoji);
    const action = isMine ? 'remove' : 'add';
    try {
      const res = await apiClient.postStoryReaction(story.id, emoji, action);
      setStory(prev => ({
        ...prev,
        reactions: {
          counts: res.counts,
          mine: res.mine
        }
      }));
      showToast(action === 'add' ? `Left ${emoji} reaction!` : "Reaction removed", "info");
    } catch (err) {
      console.error(err);
    }
  };

  if (!story) {
    return <div className="loading-state">Loading memory details...</div>;
  }

  const segment = story.transcript?.[0];
  const words = segment?.words || [];

  return (
    <div className="story-web-layout">
      {/* Left Column: Player & Interactive Transcript */}
      <div className="story-main-column">
        {/* Navigation Breadcrumb */}
        <div className="story-back-nav" onClick={() => setPanelSubTab('lifeline')}>
          <ArrowLeft size={16} /> Back to Lifeline Timeline
        </div>

        <div className="story-header-area">
          <h1 className="story-full-title">{story.title}</h1>
          <div className="story-metadata-pills">
            <span className="meta-pill location-pill">
              <MapPin size={12} style={{ display: 'inline', marginRight: '4px' }} />
              {story.place}
            </span>
            <span className="meta-pill period-pill">Childhood Chapter</span>
            <span className="meta-pill access-pill">
              <ShieldCheck size={12} style={{ display: 'inline', marginRight: '4px' }} />
              Shared with Family Circle
            </span>
          </div>
        </div>

        {/* Big Audio Player Panel */}
        <div className="story-audio-panel">
          <div className="audio-controls-row">
            <div className="audio-left-meta">
              <button className="play-toggle-btn" onClick={togglePlay}>
                {isPlaying ? <Pause size={20} /> : <Play size={20} style={{ marginLeft: '2px' }} />}
              </button>
              <div>
                <div className="audio-teller-name">
                  {story.teller.name} (Original Voice Recording)
                </div>
                <div className="audio-time-counter">
                  {(currentMs / 1000).toFixed(1)}s / {(durationMs / 1000).toFixed(1)}s
                </div>
              </div>
            </div>

            <button
              className="audio-restart-btn"
              onClick={() => { setCurrentMs(0); setIsPlaying(false); }}
            >
              <RotateCcw size={14} /> Restart Audio
            </button>
          </div>

          {/* Interactive Scrubber Track */}
          <div
            className="audio-scrubber-track"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              const clickX = e.clientX - rect.left;
              const pct = Math.max(0, Math.min(1, clickX / rect.width));
              setCurrentMs(Math.round(pct * durationMs));
            }}
          >
            <div
              className="audio-scrubber-progress"
              style={{ width: `${(currentMs / durationMs) * 100}%` }}
            >
              <div className="audio-scrubber-handle" />
            </div>
          </div>
        </div>

        {/* Word-Timed Interactive Clickable Transcript */}
        <div className="transcript-card">
          <div className="transcript-header">
            <span>Timed Speech-to-Text Transcript</span>
            <span className="transcript-hint">
              💡 Click any word to jump audio
            </span>
          </div>

          <div className="transcript-body">
            {words.map((item, idx) => {
              const isActive = currentMs >= item.start_ms && currentMs <= item.end_ms;
              return (
                <span
                  key={idx}
                  className={`transcript-word ${isActive ? 'active' : ''}`}
                  onClick={() => handleWordClick(item.start_ms)}
                  title={`Jump to ${item.start_ms}ms`}
                >
                  {item.w}{' '}
                </span>
              );
            })}
          </div>
        </div>
      </div>

      {/* Right Column: AI Summary, Reactions, Playlist & Retellings */}
      <aside className="story-side-column">
        {/* AI Summary Card */}
        <div className="story-side-card ai-summary-card">
          <div className="side-card-title">
            <Sparkles size={16} color="var(--accent-gold)" />
            <span>AI Structured Summary</span>
          </div>
          <p className="side-summary-text">{story.ai_summary}</p>
        </div>

        {/* Emoji Reactions Bar */}
        <div className="story-side-card reactions-card">
          <div className="side-card-title">
            <Heart size={16} color="var(--accent-rose)" />
            <span>Family Reactions</span>
          </div>
          <p className="reactions-subtext">
            Reactions are spoken aloud to Grandma during her morning conversation!
          </p>
          <div className="reactions-bar">
            {[
              { key: 'heart', emoji: '❤️' },
              { key: 'laugh', emoji: '😂' },
              { key: 'sad', emoji: '😢' },
              { key: 'pray', emoji: '🙏' }
            ].map(r => {
              const count = story.reactions.counts[r.key] || 0;
              const hasReacted = story.reactions.mine.includes(r.key);
              return (
                <button
                  key={r.key}
                  className={`reaction-btn ${hasReacted ? 'reacted' : ''}`}
                  onClick={() => handleToggleReaction(r.key)}
                >
                  <span>{r.emoji}</span>
                  <span>{count}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* "Listen from Start" (Baştan Dinle) Sequential Playlist */}
        <div className="story-side-card playlist-card">
          <div className="playlist-card-top">
            <div className="side-card-title">
              <Headphones size={16} color="var(--accent-cyan)" />
              <span>Baştan Dinle (Sequential Storyline)</span>
            </div>
            <button
              className="toggle-playlist-btn"
              onClick={() => setShowPlaylist(!showPlaylist)}
            >
              {showPlaylist ? "Collapse" : "Expand"}
            </button>
          </div>

          <p className="playlist-desc">
            Plays connected stories chronologically like an intimate family podcast.
          </p>

          {showPlaylist && playlist && (
            <div className="playlist-items-list">
              {playlist.items.map((item, idx) => (
                <div key={idx} className="playlist-item-row">
                  <span className="p-num">{idx + 1}.</span>
                  <span className="p-title">{item.title}</span>
                  <span className="p-dur">{Math.round(item.end_ms / 1000)}s</span>
                </div>
              ))}
              {playlist.skipped_count > 0 && (
                <div className="playlist-privacy-skip">
                  🔒 {playlist.skipped_count} private recording skipped for your access tier.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Retellings by Family Members */}
        {story.retellings && story.retellings.length > 0 && (
          <div className="story-side-card retellings-card">
            <div className="side-card-title">
              <MessageSquare size={16} color="var(--accent-purple)" />
              <span>Family Retellings & Perspectives</span>
            </div>
            {story.retellings.map(ret => (
              <div key={ret.id} className="retelling-item">
                <div className="ret-title">"{ret.title}"</div>
                <div className="ret-author">
                  Told by {ret.teller.name} ({ret.teller.relation_to_center})
                </div>
                <div className="ret-note">{ret.relation_note}</div>
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
