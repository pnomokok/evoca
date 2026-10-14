import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { Play, Pause, RotateCcw, ListMusic, MapPin, Sparkles, ArrowLeft, Heart, MessageSquare, Share2, ShieldCheck, Check } from 'lucide-react';

export default function StoryView() {
  const { selectedStoryId, setPanelSubTab, showToast } = useApp();
  const [story, setStory] = useState(null);
  const [playlist, setPlaylist] = useState(null);
  const [showPlaylist, setShowPlaylist] = useState(false);

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
    return <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px' }}>Loading memory...</div>;
  }

  const segment = story.transcript?.[0];
  const words = segment?.words || [];

  return (
    <div className="story-detail-container">
      {/* Back button */}
      <div className="story-back-nav" onClick={() => setPanelSubTab('lifeline')}>
        <ArrowLeft size={16} /> Back to Lifeline
      </div>

      <h1 className="story-full-title">{story.title}</h1>

      <div className="story-metadata-pills">
        <span className="meta-pill" style={{ color: 'var(--accent-gold)' }}>
          <MapPin size={11} style={{ display: 'inline', marginRight: '3px' }} />
          {story.place}
        </span>
        <span className="meta-pill">Childhood</span>
        <span className="meta-pill" style={{ color: 'var(--accent-emerald)' }}>
          <ShieldCheck size={11} style={{ display: 'inline', marginRight: '3px' }} />
          Shared with Family Circle
        </span>
      </div>

      {/* AI Structured Summary */}
      <div className="feed-ai-summary">
        <span className="ai-tag-inline">
          <Sparkles size={11} style={{ display: 'inline', marginRight: '3px' }} />
          AI Summary
        </span>
        {story.ai_summary}
      </div>

      {/* Audio Player Panel */}
      <div className="story-audio-panel">
        <div className="audio-controls-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button className="play-toggle-btn" onClick={togglePlay}>
              {isPlaying ? <Pause size={18} /> : <Play size={18} style={{ marginLeft: '2px' }} />}
            </button>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#fff' }}>
                {story.teller.name} (Original Audio)
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                {(currentMs / 1000).toFixed(1)}s / {(durationMs / 1000).toFixed(1)}s
              </div>
            </div>
          </div>

          <button
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '12px'
            }}
            onClick={() => { setCurrentMs(0); setIsPlaying(false); }}
          >
            <RotateCcw size={14} /> Restart
          </button>
        </div>

        {/* Scrubber Progress Bar */}
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

      {/* Interactive Word-Timed Clickable Transcript */}
      <div className="transcript-card">
        <div className="transcript-header">
          <span>Clickable Transcript</span>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'none' }}>
            Click any word to jump audio
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

      {/* Emoji Reactions Bar */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }}>
          Reactions (Delivered verbally to Grandma during morning invitation)
        </div>
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

      {/* "Listen from Start" (Baştan Dinle) Playlist */}
      <div className="listen-start-banner">
        <div>
          <div style={{ fontSize: '13px', fontWeight: 700, color: '#fff' }}>
            🎧 Listen Connected Storyline
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
            Sequential audio playlist in chronological order
          </div>
        </div>
        <button
          style={{
            background: 'var(--accent-cyan)',
            color: '#000',
            border: 'none',
            padding: '6px 14px',
            borderRadius: 'var(--radius-full)',
            fontSize: '12px',
            fontWeight: 700,
            cursor: 'pointer'
          }}
          onClick={() => setShowPlaylist(!showPlaylist)}
        >
          {showPlaylist ? "Hide Playlist" : "Baştan Dinle"}
        </button>
      </div>

      {showPlaylist && playlist && (
        <div style={{ background: 'rgba(0, 0, 0, 0.4)', borderRadius: 'var(--radius-md)', padding: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {playlist.items.map((item, idx) => (
            <div key={idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '13px' }}>
              <span>{idx + 1}. {item.title}</span>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{Math.round(item.end_ms / 1000)}s</span>
            </div>
          ))}
          {playlist.skipped_count > 0 && (
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic', borderTop: '1px solid var(--border-subtle)', paddingTop: '6px' }}>
              🔒 {playlist.skipped_count} private memory smoothly skipped for your privacy access level.
            </div>
          )}
        </div>
      )}

      {/* Retellings & Connected Memories */}
      {story.retellings && story.retellings.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px' }}>
          <div style={{ fontSize: '13px', fontWeight: 700, color: '#fff' }}>
            Retellings by Family
          </div>
          {story.retellings.map(ret => (
            <div key={ret.id} className="feed-card" style={{ padding: '12px' }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--accent-gold)' }}>
                "{ret.title}"
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                Told by {ret.teller.name} ({ret.teller.relation_to_center})
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {ret.relation_note}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
