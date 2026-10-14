import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { Play, Pause, PhoneCall, Sparkles, BookOpen, Clock, Heart, MessageCircle, HelpCircle, Shield, ChevronRight } from 'lucide-react';

export default function FeedView({ onOpenAskModal }) {
  const { setSelectedStoryId, setPanelSubTab, showToast, circleData } = useApp();
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
            ? "When winter came, snow would cover the entire hill. We would walk 4 kilometers together to the schoolhouse."
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
    <div className="feed-web-grid">
      {/* Main Stream Column */}
      <div className="feed-stream-col">
        <div className="feed-section-header">
          <div>
            <h2 className="section-title">Family Feed & Highlights</h2>
            <p className="section-subtitle">Real-time answers from Grandma, new stories, and memory milestones</p>
          </div>
          <span className="live-feed-badge">
            <span className="live-dot" /> Live
          </span>
        </div>

        <div className="feed-cards-list">
          {feedItems.map((item, idx) => {
            if (item.type === 'question_answered') {
              const isPlaying = playingItemId === item.question.id;
              return (
                <article key={idx} className="feed-card answer-card">
                  <div className="feed-card-header">
                    <span className="feed-badge badge-answer">
                      <Sparkles size={13} /> Answer Received from Grandma
                    </span>
                    <span className="feed-time">Today, 10:05 AM · Morning Session</span>
                  </div>

                  <div className="question-quote-block">
                    <span className="quote-label">Question Asked:</span>
                    <p className="question-text-quote">"{item.question.text}"</p>
                  </div>

                  <div className="answer-content-box">
                    <h3
                      className="feed-story-title"
                      onClick={() => handleOpenStory(item.answer.story_id)}
                      title="Click to view full memory"
                    >
                      {item.answer.story_title}
                    </h3>

                    {item.answer.ai_summary && (
                      <div className="feed-ai-summary">
                        <span className="ai-tag-inline">AI Summary</span>
                        {item.answer.ai_summary}
                      </div>
                    )}

                    {/* Audio Snippet Player */}
                    <div className="mini-audio-player">
                      <button
                        className="play-toggle-btn"
                        onClick={() => handlePlayToggle(item.question.id, item.answer.story_title)}
                        title="Listen to Grandma's voice snippet"
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
                      <span className="audio-duration-label">0:57</span>
                    </div>

                    {/* Core Feature: Belki onu aramak istersin (Call Grandma Banner) */}
                    <div className="call-grandma-banner">
                      <div className="call-grandma-text">
                        💖 <strong>Grandma just answered your question!</strong> Maybe you would like to call her now?
                      </div>
                      <button
                        className="call-btn"
                        onClick={() => showToast("Calling Grandma Fatma... (+90 532 ...)", "info")}
                      >
                        <PhoneCall size={14} /> Call Her
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
                      <BookOpen size={13} /> New Memory Published
                    </span>
                    <span className="feed-time">Yesterday · 24-hr privacy review completed</span>
                  </div>

                  <h3
                    className="feed-story-title"
                    onClick={() => handleOpenStory(item.story.id)}
                  >
                    {item.story.title}
                  </h3>

                  <div className="feed-ai-summary">
                    <span className="ai-tag-inline">AI Summary</span>
                    {item.story.ai_summary}
                  </div>

                  <div className="feed-story-footer">
                    <div className="story-meta-inline">
                      <Clock size={13} />
                      <span>22s original voice · Childhood in Akçaabat</span>
                    </div>
                    <button
                      className="read-story-btn"
                      onClick={() => handleOpenStory(item.story.id)}
                    >
                      Listen & View Transcript <ChevronRight size={14} />
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
            <span className="elder-avatar-large">👵</span>
            <div>
              <div className="elder-name-title">Fatma Yilmaz</div>
              <div className="elder-role-sub">Center of Circle · Born 1948</div>
            </div>
          </div>
          <div className="elder-chat-reminder">
            <Clock size={14} color="var(--accent-gold)" />
            <span>Daily Conversation: <strong>10:00 AM</strong></span>
          </div>
          <p className="elder-card-desc">
            Fatma talks with Evoca on her Echo Show without touching any screens. Your questions guide her morning reminiscence.
          </p>
          <button
            className="sidebar-action-btn"
            onClick={() => onOpenAskModal && onOpenAskModal(null)}
          >
            + Ask Grandma a Question
          </button>
        </div>

        {/* Sensitive Topic Guard Info */}
        <div className="sidebar-card privacy-guard-card">
          <div className="guard-header">
            <Shield size={16} color="var(--accent-emerald)" />
            <span className="guard-title">Family Privacy & Sensitive Topic Guard</span>
          </div>
          <p className="guard-desc">
            Evoca filters painful topics (e.g. accidents or disputes) before asking questions. Unverified memories wait 24 hours before publishing.
          </p>
        </div>

        {/* Family Circle Members list */}
        <div className="sidebar-card members-card">
          <div className="sidebar-card-title">Family Circle (4 Members)</div>
          <div className="members-mini-list">
            <div className="member-item">
              <span className="m-avatar">👵</span>
              <div className="m-info">
                <span className="m-name">Fatma Yilmaz</span>
                <span className="m-role">Center (Grandmother)</span>
              </div>
            </div>
            <div className="member-item">
              <span className="m-avatar">👩</span>
              <div className="m-info">
                <span className="m-name">Ayşe Yilmaz</span>
                <span className="m-role">Admin (Daughter)</span>
              </div>
            </div>
            <div className="member-item">
              <span className="m-avatar">👧</span>
              <div className="m-info">
                <span className="m-name">Elif Yilmaz</span>
                <span className="m-role">Member (Granddaughter)</span>
              </div>
            </div>
            <div className="member-item">
              <span className="m-avatar">👦</span>
              <div className="m-info">
                <span className="m-name">Can Yilmaz</span>
                <span className="m-role">Member (Grandson)</span>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
