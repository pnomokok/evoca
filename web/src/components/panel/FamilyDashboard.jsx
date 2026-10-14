import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { Play, Pause, PhoneCall, Sparkles, Clock, MessageSquarePlus, Mic, ChevronRight, Heart, AlertCircle, ArrowUpRight } from 'lucide-react';

export default function FamilyDashboard({ onOpenAskModal, onOpenRecordModal }) {
  const { setSelectedStoryId, setPanelSubTab, showToast, circleData, currentViewerId } = useApp();
  const [featuredStory, setFeaturedStory] = useState(null);
  const [feedItems, setFeedItems] = useState([]);
  const [lifeline, setLifeline] = useState(null);
  const [playingId, setPlayingId] = useState(null);

  const me = circleData?.me || { name: 'Elif Yilmaz', role: 'member', relation_to_center: 'granddaughter' };
  const circle = circleData?.circle || { name: 'The Yilmaz Family', chat_time: '10:00' };

  useEffect(() => {
    async function loadData() {
      try {
        const [feat, feed, life] = await Promise.all([
          apiClient.getFeaturedStory(),
          apiClient.getFeed(),
          apiClient.getLifeline('person_fatma')
        ]);
        setFeaturedStory(feat);
        setFeedItems(feed.items || []);
        setLifeline(life);
      } catch (err) {
        console.error("Error loading dashboard data", err);
      }
    }
    loadData();
  }, []);

  const handlePlayAudio = (id, textSample, title) => {
    if (playingId === id) {
      setPlayingId(null);
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    } else {
      setPlayingId(id);
      showToast(`Playing story audio: ${title}`, 'info');

      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(textSample);
        utterance.rate = 0.93;
        utterance.lang = 'en-US';
        utterance.onend = () => setPlayingId(null);
        utterance.onerror = () => setPlayingId(null);
        window.speechSynthesis.speak(utterance);
      }
    }
  };

  const handleOpenStory = (storyId) => {
    setSelectedStoryId(storyId);
    setPanelSubTab('story');
  };

  return (
    <div className="album-dashboard">
      {/* 1. Welcome Editorial Hero Section */}
      <section className="album-hero" aria-labelledby="hero-heading">
        <div className="hero-text-side">
          <div className="hero-greeting">
            <span className="greeting-lead">Family Chronicle · {circle.name}</span>
            <span className="greeting-viewer">Welcome back, {me.name.split(' ')[0]}</span>
          </div>

          <h1 id="hero-heading" className="hero-headline">
            Every family carries a thousand untold stories.
          </h1>

          <p className="hero-supporting">
            Discover the voices, moments, and memories that make your family yours. Preserved simply through natural daily conversation with Grandma Fatma.
          </p>

          <div className="hero-cta-group">
            <button
              className="editorial-btn primary"
              onClick={() => handlePlayAudio(
                'hero_preview',
                "We packed two wooden trunks with olive oil tins, dried figs, and my mother's curtains. The salt air felt like a brand new life.",
                "The Summer We Moved to the Coast"
              )}
            >
              {playingId === 'hero_preview' ? <Pause size={17} /> : <Play size={17} style={{ marginLeft: '2px' }} />}
              <span>{playingId === 'hero_preview' ? 'Pause story' : 'Listen to her story'}</span>
            </button>

            <button
              className="editorial-btn secondary"
              onClick={() => onOpenAskModal && onOpenAskModal(null)}
            >
              <MessageSquarePlus size={16} />
              <span>Ask Grandma a question</span>
            </button>
          </div>
        </div>

        {/* Hero Archival Photograph */}
        <div className="hero-photo-side">
          <figure className="photo-matte-frame hero-frame">
            <img
              src="/family_hero.jpg"
              alt="Archival family photograph of the Yilmaz family gathered in Akçaabat"
              className="archival-photo"
            />
            <figcaption className="photo-caption">
              <span>Akçaabat, summer 1974</span>
              <span className="caption-dot">·</span>
              <span>Three generations on the veranda</span>
            </figcaption>
          </figure>
        </div>
      </section>

      {/* Decorative Editorial Divider */}
      <div className="editorial-divider">
        <span className="divider-line" />
        <span className="divider-ornament">❦</span>
        <span className="divider-line" />
      </div>

      {/* 2. Featured Memory Section */}
      {featuredStory && (
        <section className="featured-story-section" aria-labelledby="featured-story-heading">
          <div className="section-header-editorial">
            <span className="section-eyebrow">Featured Family Memory</span>
            <h2 id="featured-story-heading" className="section-title-serif">
              {featuredStory.title}
            </h2>
            <div className="story-byline">
              <span>Told by <strong>{featuredStory.storyteller}</strong></span>
              <span className="byline-sep">/</span>
              <span>{featuredStory.period_label}</span>
              <span className="byline-sep">/</span>
              <span>{featuredStory.place} ({featuredStory.year})</span>
            </div>
          </div>

          <div className="featured-story-layout">
            <figure className="photo-matte-frame featured-frame">
              <img
                src={featuredStory.photo_url || "/coast_memory.jpg"}
                alt={featuredStory.title}
                className="archival-photo"
              />
              <figcaption className="photo-caption">
                <span>Original archival photo · Akçaabat coast</span>
              </figcaption>
            </figure>

            <div className="featured-story-narrative">
              <blockquote className="editorial-blockquote">
                "{featuredStory.excerpt}"
              </blockquote>

              {featuredStory.ai_summary && (
                <div className="ai-summary-note">
                  <span className="ai-label-pill">AI-Generated Summary</span>
                  <p>{featuredStory.ai_summary}</p>
                </div>
              )}

              {/* Bespoke Warm Audio Player */}
              <div className="editorial-player">
                <button
                  className="player-play-btn"
                  onClick={() => handlePlayAudio(
                    featuredStory.id,
                    featuredStory.excerpt,
                    featuredStory.title
                  )}
                  aria-label={playingId === featuredStory.id ? "Pause story" : "Play story"}
                >
                  {playingId === featuredStory.id ? <Pause size={18} /> : <Play size={18} style={{ marginLeft: '2px' }} />}
                </button>

                <div className="player-track-info">
                  <div className="player-label-row">
                    <span className="player-title">{featuredStory.title}</span>
                    <span className="player-time">1:04</span>
                  </div>
                  <div className="player-scrubber-bg">
                    <div className={`player-scrubber-fill ${playingId === featuredStory.id ? 'active' : ''}`} />
                  </div>
                </div>

                <button
                  className="open-story-link"
                  onClick={() => handleOpenStory(featuredStory.id)}
                >
                  <span>Read full memory</span>
                  <ArrowUpRight size={15} />
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 3. Recent Memories Section */}
      <section className="recent-memories-section" aria-labelledby="recent-heading">
        <div className="section-header-editorial">
          <span className="section-eyebrow">Archive Entries</span>
          <h2 id="recent-heading" className="section-title-serif">Recent Family Stories</h2>
          <p className="section-desc">
            Transcribed and preserved from Grandma's morning conversations with Evoca.
          </p>
        </div>

        <div className="editorial-stories-grid">
          {/* Story Card 1: The Mulberry Tree */}
          <article className="story-editorial-card">
            <figure className="photo-matte-frame card-frame">
              <img
                src="/mulberry_memory.jpg"
                alt="Two sisters under the mulberry tree"
                className="archival-photo"
              />
              <figcaption className="photo-caption">
                <span>The village garden, 1956</span>
              </figcaption>
            </figure>

            <div className="story-card-body">
              <div className="card-period-tag">Childhood Chapter</div>
              <h3
                className="card-story-title"
                onClick={() => handleOpenStory('story_mulberry')}
              >
                The Mulberry Tree
              </h3>
              <p className="card-storyteller">Told by Grandma Fatma</p>

              <p className="card-excerpt">
                "When I was a little girl in the village, we had a big mulberry tree in the garden. Every summer we would climb it and eat until our hands turned purple."
              </p>

              <div className="card-action-bar">
                <button
                  className="mini-audio-btn"
                  onClick={() => handlePlayAudio(
                    'story_mulberry',
                    "When I was a little girl in the village, we had a big mulberry tree in the garden. Every summer we would climb it and eat until our hands turned purple.",
                    "The Mulberry Tree"
                  )}
                >
                  {playingId === 'story_mulberry' ? <Pause size={15} /> : <Play size={15} />}
                  <span>{playingId === 'story_mulberry' ? 'Pause (0:22)' : 'Listen (0:22)'}</span>
                </button>

                <button
                  className="read-more-text"
                  onClick={() => handleOpenStory('story_mulberry')}
                >
                  Read & view transcript →
                </button>
              </div>
            </div>
          </article>

          {/* Story Card 2: Walking to School in the Snow */}
          <article className="story-editorial-card">
            <figure className="photo-matte-frame card-frame">
              <img
                src="/school_winter.jpg"
                alt="Children walking through village snow to school"
                className="archival-photo"
              />
              <figcaption className="photo-caption">
                <span>Winter trail to schoolhouse, 1958</span>
              </figcaption>
            </figure>

            <div className="story-card-body">
              <div className="card-period-tag">Childhood Chapter</div>
              <h3
                className="card-story-title"
                onClick={() => handleOpenStory('story_school')}
              >
                Walking to School in the Snow
              </h3>
              <p className="card-storyteller">Told by Grandma Fatma</p>

              <p className="card-excerpt">
                "Four kilometers through knee-deep snow. Mother would slip two hot baked potatoes straight from the wood stove into our coat pockets so our fingers wouldn't freeze on the walk."
              </p>

              <div className="card-action-bar">
                <button
                  className="mini-audio-btn"
                  onClick={() => handlePlayAudio(
                    'story_school',
                    "Four kilometers in knee-deep snow. Mother would slip two hot baked potatoes straight from the wood stove into our coat pockets.",
                    "Walking to School in the Snow"
                  )}
                >
                  {playingId === 'story_school' ? <Pause size={15} /> : <Play size={15} />}
                  <span>{playingId === 'story_school' ? 'Pause (0:57)' : 'Listen (0:57)'}</span>
                </button>

                <button
                  className="read-more-text"
                  onClick={() => handleOpenStory('story_school')}
                >
                  Read & view transcript →
                </button>
              </div>
            </div>
          </article>
        </div>
      </section>

      {/* Decorative Editorial Divider */}
      <div className="editorial-divider">
        <span className="divider-line" />
        <span className="divider-ornament">❦</span>
        <span className="divider-line" />
      </div>

      {/* 4. Stories Waiting to Be Told Section */}
      <section className="stories-waiting-section" aria-labelledby="waiting-heading">
        <div className="section-header-editorial">
          <span className="section-eyebrow">Unexplored Chapters</span>
          <h2 id="waiting-heading" className="section-title-serif">Stories waiting to be told</h2>
          <p className="section-desc">
            Every chapter holds memories worth discovering. Gently ask a question to invite Grandma to share hers.
          </p>
        </div>

        <div className="waiting-chapters-grid">
          {[
            {
              period: "childhood",
              title: "Childhood",
              years: "1948 – 1960",
              status: "has_stories",
              count: "2 memories recorded",
              prompt: "What games did you invent with your brothers?"
            },
            {
              period: "youth",
              title: "Youth",
              years: "1961 – 1967",
              status: "waiting",
              count: "Unrecorded chapter",
              prompt: "What did you dream of becoming when you were sixteen?"
            },
            {
              period: "marriage_early_years",
              title: "Early Adulthood",
              years: "1968 – 1974",
              status: "has_stories",
              count: "1 memory recorded",
              prompt: "How did you and Grandpa first meet?"
            },
            {
              period: "raising_children",
              title: "Raising a Family",
              years: "1975 – 1990",
              status: "waiting",
              count: "Unrecorded chapter",
              prompt: "What family tradition do you remember most when the children were small?"
            },
            {
              period: "midlife",
              title: "Midlife",
              years: "1991 – 2008",
              status: "waiting",
              count: "Unrecorded chapter",
              prompt: "What was the biggest journey you ever took together?"
            },
            {
              period: "retirement",
              title: "Retirement",
              years: "2009 – Present",
              status: "waiting",
              count: "Unrecorded chapter",
              prompt: "What brings you the quietest joy in your garden these days?"
            }
          ].map((ch) => (
            <div
              key={ch.period}
              className={`chapter-card ${ch.status}`}
              onClick={() => onOpenAskModal && onOpenAskModal(ch.period, ch.prompt)}
              title={ch.status === 'waiting' ? "Click to ask Grandma this question" : "Explore chapter"}
            >
              <div className="chapter-top">
                <span className="chapter-name">{ch.title}</span>
                <span className="chapter-years">{ch.years}</span>
              </div>

              <div className="chapter-status-row">
                <span className={`status-pill ${ch.status}`}>
                  {ch.status === 'has_stories' ? '● Recorded' : '○ Waiting'}
                </span>
                <span className="chapter-count">{ch.count}</span>
              </div>

              {ch.status === 'waiting' ? (
                <div className="chapter-invitation">
                  <span className="invitation-label">Gentle prompt:</span>
                  <p className="invitation-question">"{ch.prompt}"</p>
                  <span className="ask-prompt-link">
                    + Ask this question
                  </span>
                </div>
              ) : (
                <div className="chapter-invitation recorded">
                  <p className="invitation-question">Stories preserved about the village garden and school.</p>
                  <span className="ask-prompt-link">
                    + Ask another question
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Decorative Editorial Divider */}
      <div className="editorial-divider">
        <span className="divider-line" />
        <span className="divider-ornament">❦</span>
        <span className="divider-line" />
      </div>

      {/* 5. Recent Family Activity Section */}
      <section className="family-activity-section" aria-labelledby="activity-heading">
        <div className="section-header-editorial">
          <span className="section-eyebrow">Intimate Connections</span>
          <h2 id="activity-heading" className="section-title-serif">Recent Family Circle Activity</h2>
          <p className="section-desc">
            Direct connections between family questions and Grandma's answers.
          </p>
        </div>

        <div className="activity-cards-list">
          {feedItems.map((item, idx) => {
            if (item.type === 'question_answered') {
              return (
                <div key={idx} className="activity-item-card answer">
                  <div className="activity-badge-row">
                    <span className="activity-pill sage">Answer Received</span>
                    <span className="activity-timestamp">Today at 10:05 AM</span>
                  </div>

                  <div className="activity-question-quote">
                    <span className="q-label">Granddaughter Elif asked:</span>
                    <p className="q-text">"{item.question.text}"</p>
                  </div>

                  <div className="activity-answer-details">
                    <div className="answer-title-row">
                      <span className="a-title" onClick={() => handleOpenStory(item.answer.story_id)}>
                        {item.answer.story_title}
                      </span>
                      <span className="a-duration">0:57 audio</span>
                    </div>

                    <p className="a-excerpt">"{item.answer.excerpt || item.answer.ai_summary}"</p>

                    {/* Core Emotional Connection: Call Grandma */}
                    <div className="call-grandma-intimate-box">
                      <div className="call-intimate-text">
                        <strong>Grandma just answered your question!</strong>
                        <span>Her voice is warm and she was thinking of you this morning.</span>
                      </div>
                      <button
                        className="call-grandma-action-btn"
                        onClick={() => showToast("Calling Grandma Fatma... (+90 532 ...)", "info")}
                      >
                        <PhoneCall size={14} />
                        <span>Call Grandma</span>
                      </button>
                    </div>
                  </div>
                </div>
              );
            }

            if (item.type === 'story_published') {
              return (
                <div key={idx} className="activity-item-card publish">
                  <div className="activity-badge-row">
                    <span className="activity-pill beige">Memory Preserved</span>
                    <span className="activity-timestamp">Yesterday at 4:00 PM</span>
                  </div>

                  <div className="activity-story-snippet">
                    <h4
                      className="activity-story-name"
                      onClick={() => handleOpenStory(item.story.id)}
                    >
                      {item.story.title}
                    </h4>
                    <p className="activity-story-excerpt">{item.story.ai_summary}</p>
                    <button
                      className="inline-listen-link"
                      onClick={() => handleOpenStory(item.story.id)}
                    >
                      Listen to recording (22s) →
                    </button>
                  </div>
                </div>
              );
            }

            return null;
          })}
        </div>
      </section>

      {/* Floating or Footer Contribution Bar */}
      <footer className="dashboard-editorial-footer">
        <div className="footer-callout">
          <div className="footer-callout-text">
            <h3>Every voice belongs in the archive.</h3>
            <p>Contribute your own memory or leave a question for Grandma's next conversation.</p>
          </div>
          <div className="footer-callout-actions">
            <button
              className="editorial-btn secondary"
              onClick={() => onOpenRecordModal && onOpenRecordModal()}
            >
              <Mic size={16} />
              <span>Record your own memory</span>
            </button>
            <button
              className="editorial-btn primary"
              onClick={() => onOpenAskModal && onOpenAskModal(null)}
            >
              <MessageSquarePlus size={16} />
              <span>Ask a question</span>
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
