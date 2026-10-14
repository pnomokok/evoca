import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { Play, Pause, PhoneCall, Sparkles, BookOpen, Clock, Heart, MessageCircle } from 'lucide-react';

export default function FeedView() {
  const { setSelectedStoryId, setPanelSubTab, showToast } = useApp();
  const [feedItems, setFeedItems] = useState([]);
  const [playingItemId, setPlayingItemId] = useState(null);

  useEffect(() => {
    async function loadFeed() {
      try {
        const data = await apiClient.getFeed();
        setFeedItems(data.items || []);
      } catch (err) {
        console.error(err);
      }
    }
    loadFeed();
  }, []);

  const handlePlayToggle = (id, title) => {
    if (playingItemId === id) {
      setPlayingItemId(null);
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    } else {
      setPlayingItemId(id);
      showToast(`Playing audio preview: ${title}`, 'info');

      // Synthesize audio preview sample
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(
          id === 'question_school'
            ? "When winter came, snow would cover the entire hill. We would walk 4 kilometers together."
            : "When I was a little girl in the village, we had a big mulberry tree in the garden."
        );
        utterance.rate = 0.95;
        utterance.onend = () => setPlayingItemId(null);
        window.speechSynthesis.speak(utterance);
      }
    }
  };

  const handleOpenStory = (storyId) => {
    setSelectedStoryId(storyId);
    setPanelSubTab('story');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ fontSize: '18px', fontWeight: 800 }}>Family Activity</h2>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Latest updates</span>
      </div>

      {feedItems.map((item, idx) => {
        if (item.type === 'question_answered') {
          const isPlaying = playingItemId === item.question.id;
          return (
            <div key={idx} className="feed-card">
              <div className="feed-card-header">
                <span className="feed-badge badge-answer">
                  <Sparkles size={12} /> Answer Received
                </span>
                <span className="feed-time">Today, 10:05 AM</span>
              </div>

              <div className="question-text-quote">
                "{item.question.text}"
              </div>

              <div
                className="feed-story-title"
                onClick={() => handleOpenStory(item.answer.story_id)}
              >
                {item.answer.story_title}
              </div>

              {item.answer.ai_summary && (
                <div className="feed-ai-summary">
                  <span className="ai-tag-inline">AI Summary</span>
                  {item.answer.ai_summary}
                </div>
              )}

              {/* Mini Audio Snippet Player */}
              <div className="mini-audio-player">
                <button
                  className="play-toggle-btn"
                  onClick={() => handlePlayToggle(item.question.id, item.answer.story_title)}
                  title="Play audio snippet of grandmother's answer"
                >
                  {isPlaying ? <Pause size={18} /> : <Play size={18} style={{ marginLeft: '2px' }} />}
                </button>
                <div className="mini-waveform-bars">
                  {[4, 8, 14, 18, 10, 16, 22, 12, 6, 14, 20, 8, 12, 18, 6].map((h, i) => (
                    <div
                      key={i}
                      className={`wave-bar ${isPlaying ? 'playing' : ''}`}
                      style={{ height: `${h}px`, animationDelay: `${i * 0.05}s` }}
                    />
                  ))}
                </div>
                <span className="audio-duration-label">0:57</span>
              </div>

              {/* Core Feature: Belki onu aramak istersin (Call Grandma Banner) */}
              <div className="call-grandma-banner">
                <div className="call-grandma-text">
                  💖 Maybe you would like to call her now?
                </div>
                <button
                  className="call-btn"
                  onClick={() => showToast("Calling Grandma Fatma... (+90 532 ...)", "info")}
                >
                  <PhoneCall size={13} /> Call
                </button>
              </div>
            </div>
          );
        }

        if (item.type === 'story_published') {
          return (
            <div key={idx} className="feed-card">
              <div className="feed-card-header">
                <span className="feed-badge badge-story">
                  <BookOpen size={12} /> New Memory Published
                </span>
                <span className="feed-time">Yesterday</span>
              </div>

              <div
                className="feed-story-title"
                onClick={() => handleOpenStory(item.story.id)}
              >
                {item.story.title}
              </div>

              <div className="feed-ai-summary">
                <span className="ai-tag-inline">AI Summary</span>
                {item.story.ai_summary}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={12} /> 22s audio · Akçaabat
                </span>
                <button
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--accent-gold)',
                    color: 'var(--accent-gold)',
                    padding: '4px 12px',
                    borderRadius: 'var(--radius-full)',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                  onClick={() => handleOpenStory(item.story.id)}
                >
                  Listen Story →
                </button>
              </div>
            </div>
          );
        }

        return null;
      })}
    </div>
  );
}
