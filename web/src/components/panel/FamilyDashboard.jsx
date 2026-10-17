import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { Play, Pause, PhoneCall, Sparkles, Clock, MessageSquarePlus, Mic, ChevronRight, ChevronLeft, Heart, AlertCircle, ArrowUpRight, ArrowRight } from 'lucide-react';
import FamilyTreeCard from './FamilyTreeCard';
import FamilyTreeModal from './FamilyTreeModal';

const SIX_RECENT_STORIES = [
  {
    id: "story_mulberry",
    title: "The Mulberry Tree",
    period: "Childhood Chapter",
    year: "1956",
    photo: "/mulberry_memory.jpg",
    caption: "The village garden, 1956",
    teller: "Grandma Fatma",
    duration: "0:22",
    excerpt: "When I was a little girl in the village, we had a big mulberry tree in the garden. Every summer we would climb it and eat until our hands turned purple."
  },
  {
    id: "story_school",
    title: "Walking to School in the Snow",
    period: "Childhood Chapter",
    year: "1958",
    photo: "/school_winter.jpg",
    caption: "Winter trail to schoolhouse, 1958",
    teller: "Grandma Fatma",
    duration: "0:57",
    excerpt: "Four kilometers through knee-deep snow. Mother would slip two hot baked potatoes straight from the wood stove into our coat pockets so our fingers wouldn't freeze on the walk."
  },
  {
    id: "story_coast",
    title: "The Summer We Moved to the Coast",
    period: "Early Adulthood",
    year: "1968",
    photo: "/coast_memory.jpg",
    caption: "Akçaabat coastal cottage, 1968",
    teller: "Grandma Fatma",
    duration: "1:04",
    excerpt: "We packed two wooden trunks with olive oil tins, dried figs, and my mother's hand-embroidered curtains. The air smelled of salt and wild pine as the truck rounded the coastal bend."
  },
  {
    id: "story_bazaar",
    title: "The Friday Tea Bazaar",
    period: "Early Adulthood",
    year: "1963",
    photo: "/bazaar_memory.jpg",
    caption: "Akçaabat port market, 1963",
    teller: "Grandma Fatma",
    duration: "0:45",
    excerpt: "Every Friday after morning mist lifted, we brought bags of wild mint and mountain tea down to the harbor. The scales clinked and tea aromas drifted across the boats."
  },
  {
    id: "story_olive",
    title: "Autumn Olive Harvest",
    period: "Family Traditions",
    year: "1965",
    photo: "/olive_memory.jpg",
    caption: "Hillside olive orchard, 1965",
    teller: "Grandma Fatma",
    duration: "0:38",
    excerpt: "We laid coarse burlap blankets under the oldest trees on the terraced hill. All the children collected fallen olives into wicker baskets, laughing until the evening sun set over the sea."
  },
  {
    id: "story_gathering",
    title: "Three Generations on the Veranda",
    period: "Family Gathering",
    year: "1974",
    photo: "/family_hero.jpg",
    caption: "Veranda tea gathering, 1974",
    teller: "Grandma Fatma",
    duration: "1:12",
    excerpt: "When the summer breezes arrived, the entire family gathered on the stone terrace. We brewed fresh tea in the samovar and told old village tales under the grape arbor until midnight."
  }
];

export default function FamilyDashboard({ onOpenAskModal, onOpenRecordModal }) {
  const { setSelectedStoryId, setPanelSubTab, showToast, circleData, currentViewerId, centerPersonId, switchViewer } = useApp();
  const [featuredStory, setFeaturedStory] = useState(null);
  const [feedItems, setFeedItems] = useState([]);
  const [lifeline, setLifeline] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const [isTreeModalOpen, setIsTreeModalOpen] = useState(false);
  const [storiesPageIndex, setStoriesPageIndex] = useState(0);

  const STORIES_PER_PAGE = 3;
  const totalStoryPages = Math.ceil(SIX_RECENT_STORIES.length / STORIES_PER_PAGE);
  const visibleStories = SIX_RECENT_STORIES.slice(
    storiesPageIndex * STORIES_PER_PAGE,
    (storiesPageIndex + 1) * STORIES_PER_PAGE
  );

  const handlePrevStories = () => {
    setStoriesPageIndex(prev => (prev === 0 ? totalStoryPages - 1 : prev - 1));
  };

  const handleNextStories = () => {
    setStoriesPageIndex(prev => (prev + 1) % totalStoryPages);
  };

  const me = circleData?.me || { name: 'Elif Yilmaz', role: 'member', relation_to_center: 'granddaughter' };
  const circle = circleData?.circle || { name: 'The Yilmaz Family', chat_time: '10:00' };

  useEffect(() => {
    async function loadData() {
      try {
        const [feat, feed, life] = await Promise.all([
          apiClient.getFeaturedStory(),
          apiClient.getFeed(),
          centerPersonId ? apiClient.getLifeline(centerPersonId).catch(() => null) : Promise.resolve(null)
        ]);
        setFeaturedStory(feat);
        setFeedItems(feed?.items || []);
        setLifeline(life);
      } catch (err) {
        console.error("Error loading dashboard data", err);
      }
    }
    loadData();
  }, [centerPersonId, currentViewerId]);

  // Compute actual deduplicated story count from all existing data sources
  const uniqueStoryIds = new Set(SIX_RECENT_STORIES.map(s => s.id));
  if (lifeline?.periods) {
    lifeline.periods.forEach(p => {
      (p.stories || []).forEach(s => {
        if (s?.id) uniqueStoryIds.add(s.id);
      });
    });
  }
  if (feedItems) {
    feedItems.forEach(item => {
      if (item?.story?.id) uniqueStoryIds.add(item.story.id);
      if (item?.answer?.story_id) uniqueStoryIds.add(item.answer.story_id);
    });
  }
  if (featuredStory?.id) {
    uniqueStoryIds.add(featuredStory.id);
  }
  const storyCount = uniqueStoryIds.size;

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
      {/* 1. New Two-Column Top Hero Layout */}
      <div className="hero-two-column-wrapper">
        {/* Left Card: Welcome & Featured Family Memory (~68% desktop width) */}
        <section className="hero-left-card welcome-memory-card" aria-labelledby="hero-heading">
          <div className="welcome-card-top">
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
          </div>

          {/* Featured Archival Memory Preview inside Left Card */}
          <div className="hero-featured-memory-spread">
            <figure className="photo-matte-frame hero-card-photo-frame">
              <img
                src={featuredStory?.photo_url || "/family_hero.jpg"}
                alt="Archival family photograph gathered on the veranda"
                className="archival-photo"
              />
              <figcaption className="photo-caption">
                <span>{featuredStory?.place || "Akçaabat, summer 1974"}</span>
                <span className="caption-dot">·</span>
                <span>{featuredStory?.year ? `Three generations (${featuredStory.year})` : "Three generations on the veranda"}</span>
              </figcaption>
            </figure>

            <div className="hero-memory-quote-block">
              <span className="quote-mark">“</span>
              <blockquote className="hero-quote-text">
                {featuredStory?.excerpt || "We packed two wooden trunks with olive oil tins, dried figs, and my mother's hand-embroidered curtains. The air smelled of salt and wild pine as the truck rounded the coastal bend."}
              </blockquote>

              <div className="hero-memory-meta">
                <span className="hero-memory-title">{featuredStory?.title || "The Summer We Moved to the Coast"}</span>
                <span className="hero-memory-teller">Told by {featuredStory?.storyteller || "Grandma Fatma"}</span>
              </div>
            </div>
          </div>

          {/* Primary Actions Group */}
          <div className="hero-cta-group">
            <button
              type="button"
              className="editorial-btn primary"
              onClick={() => handlePlayAudio(
                'hero_preview',
                featuredStory?.excerpt || "We packed two wooden trunks with olive oil tins, dried figs, and my mother's curtains. The salt air felt like a brand new life.",
                featuredStory?.title || "The Summer We Moved to the Coast"
              )}
            >
              {playingId === 'hero_preview' ? <Pause size={17} /> : <Play size={17} style={{ marginLeft: '2px' }} />}
              <span>{playingId === 'hero_preview' ? 'Pause story' : 'Listen to her story'}</span>
            </button>

            <button
              type="button"
              className="editorial-btn secondary"
              onClick={() => onOpenAskModal && onOpenAskModal(null)}
            >
              <MessageSquarePlus size={16} />
              <span>Ask Grandma a question</span>
            </button>

            {featuredStory && (
              <button
                type="button"
                className="hero-read-more-link"
                onClick={() => handleOpenStory(featuredStory.id)}
              >
                <span>Read full memory</span>
                <ArrowRight size={14} />
              </button>
            )}
          </div>
        </section>

        {/* Right Card: Family Tree Preview (~32% desktop width) */}
        <FamilyTreeCard
          circleData={circleData}
          currentViewerId={currentViewerId}
          onSwitchViewer={switchViewer}
          storyCount={storyCount}
          onOpenRecordModal={onOpenRecordModal}
          onOpenTreeModal={() => setIsTreeModalOpen(true)}
          onNavigateLifeline={() => setPanelSubTab('lifeline')}
        />
      </div>

      {/* Family Tree Lineage Modal */}
      <FamilyTreeModal
        isOpen={isTreeModalOpen}
        onClose={() => setIsTreeModalOpen(false)}
        circleData={circleData}
        currentViewerId={currentViewerId}
        onSwitchViewer={switchViewer}
        onNavigateLifeline={() => setPanelSubTab('lifeline')}
        storyCount={storyCount}
      />

      {/* Decorative Editorial Divider */}
      <div className="editorial-divider">
        <span className="divider-line" />
        <span className="divider-ornament">❦</span>
        <span className="divider-line" />
      </div>

      {/* 2. Recent Family Stories Section (3 Cards Per Page with Arrow Navigation, max 6 stories) */}
      <section className="recent-memories-section" aria-labelledby="recent-heading">
        <div className="section-header-editorial-with-nav">
          <div className="section-header-left">
            <span className="section-eyebrow">Archive Entries</span>
            <h2 id="recent-heading" className="section-title-serif">Recent Family Stories</h2>
            <p className="section-desc">
              Transcribed and preserved from Grandma's morning conversations with Evoca.
            </p>
          </div>

          {/* Navigation Controls: Page Indicator, Dots, and Arrow Buttons */}
          <div className="stories-pagination-controls" aria-label="Stories navigation">
            <div className="pagination-indicators">
              <span className="pagination-page-label">
                Page <strong>{storiesPageIndex + 1}</strong> of <strong>{totalStoryPages}</strong>
              </span>
              <div className="pagination-dots">
                {Array.from({ length: totalStoryPages }).map((_, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className={`pagination-dot ${idx === storiesPageIndex ? 'active' : ''}`}
                    onClick={() => setStoriesPageIndex(idx)}
                    aria-label={`Go to page ${idx + 1}`}
                  />
                ))}
              </div>
            </div>

            <div className="pagination-arrow-btns">
              <button
                type="button"
                className="story-nav-arrow-btn prev"
                onClick={handlePrevStories}
                aria-label="Previous stories"
                title="Previous stories"
              >
                <ChevronLeft size={18} />
              </button>
              <button
                type="button"
                className="story-nav-arrow-btn next"
                onClick={handleNextStories}
                aria-label="Next stories"
                title="Next stories"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
        </div>

        {/* Horizontal 3-Column Stories Grid */}
        <div className="editorial-stories-horizontal-grid" key={storiesPageIndex}>
          {visibleStories.map((story) => (
            <article key={story.id} className="story-editorial-card vertical-card">
              <figure className="photo-matte-frame card-frame">
                <img
                  src={story.photo}
                  alt={story.title}
                  className="archival-photo"
                  loading="lazy"
                />
                <figcaption className="photo-caption">
                  <span>{story.caption}</span>
                </figcaption>
              </figure>

              <div className="story-card-body">
                <div className="card-period-tag">{story.period} · {story.year}</div>
                <h3
                  className="card-story-title"
                  onClick={() => handleOpenStory(story.id)}
                  title={`Read "${story.title}"`}
                >
                  {story.title}
                </h3>
                <p className="card-storyteller">Told by {story.teller}</p>

                <p className="card-excerpt">
                  "{story.excerpt}"
                </p>

                <div className="card-action-bar">
                  <button
                    type="button"
                    className="mini-audio-btn"
                    onClick={() => handlePlayAudio(story.id, story.excerpt, story.title)}
                  >
                    {playingId === story.id ? <Pause size={15} /> : <Play size={15} />}
                    <span>{playingId === story.id ? `Pause (${story.duration})` : `Listen (${story.duration})`}</span>
                  </button>

                  <button
                    type="button"
                    className="read-more-text"
                    onClick={() => handleOpenStory(story.id)}
                  >
                    Read memory →
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* Decorative Editorial Divider */}
      <div className="editorial-divider">
        <span className="divider-line" />
        <span className="divider-ornament">❦</span>
        <span className="divider-line" />
      </div>

      {/* 3. Stories Waiting to Be Told Section */}
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
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && onOpenAskModal && onOpenAskModal(ch.period, ch.prompt)}
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

      {/* 4. Recent Family Activity Section */}
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
                      {item.answer.audio_url && (
                        <span className="a-duration">{item.answer.duration_ms ? `${Math.round(item.answer.duration_ms / 1000)}s ses` : 'Ses'}</span>
                      )}
                    </div>

                    <p className="a-excerpt">"{item.answer.excerpt || item.answer.ai_summary}"</p>

                    {/* Core Emotional Connection: Call Grandma */}
                    <div className="call-grandma-intimate-box">
                      <div className="call-intimate-text">
                        <strong>Grandma just answered your question!</strong>
                        <span>Her voice is warm and she was thinking of you this morning.</span>
                      </div>
                      <button
                        type="button"
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
                      type="button"
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

      {/* 5. Floating / Editorial Contribution Bar */}
      <footer className="dashboard-editorial-footer">
        <div className="footer-callout">
          <div className="footer-callout-text">
            <h3>Every voice belongs in the archive.</h3>
            <p>Contribute your own memory or leave a question for Grandma's next conversation.</p>
          </div>
          <div className="footer-callout-actions">
            <button
              type="button"
              className="editorial-btn secondary"
              onClick={() => onOpenRecordModal && onOpenRecordModal()}
            >
              <Mic size={16} />
              <span>Record your own memory</span>
            </button>
            <button
              type="button"
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
