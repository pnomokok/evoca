import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import { Play, ChevronRight, ChevronLeft, ArrowRight } from 'lucide-react';
import FamilyTreeCard from './FamilyTreeCard';
import FamilyTreeModal from './FamilyTreeModal';
import BlobPhoto from './BlobPhoto';
import AnswerCard from './AnswerCard';
import { periodLabel, periodYears } from '../../utils/periods';
import { formatDuration, formatWhen } from '../../utils/format';

const STORIES_PER_PAGE = 3;
const RECENT_STORY_LIMIT = 6;

// Gentle starter questions for a chapter; the family can edit them before sending.
const PERIOD_PROMPTS = {
  childhood: 'What games did you play as a child?',
  youth: 'What did you dream of becoming when you were young?',
  marriage_early_years: 'What do you remember about your first home together?',
  raising_children: 'What family tradition do you remember most when the children were small?',
  midlife: 'What was the biggest journey you ever took?',
  retirement: 'What brings you quiet joy these days?'
};

// onOpenAskModal(period, prompt): a chapter's own question (null for the center, who does not ask).
export default function FamilyDashboard({ onOpenAskModal }) {
  const { openStory, navigate, circleData, currentViewerId, viewerReady, centerPersonId, dataVersion } = useApp();
  // Loaded data is keyed by viewer; another viewer's feed is never shown.
  const [loaded, setLoaded] = useState({ viewerId: null, feedItems: [], lifeline: null });
  const [isTreeModalOpen, setIsTreeModalOpen] = useState(false);
  const [storiesPageIndex, setStoriesPageIndex] = useState(0);

  useEffect(() => {
    if (!viewerReady) return;
    let cancelled = false;
    async function loadData() {
      try {
        const [feed, life] = await Promise.all([
          apiClient.getFeed(),
          centerPersonId ? apiClient.getLifeline(centerPersonId).catch(() => null) : Promise.resolve(null)
        ]);
        if (cancelled) return;
        setLoaded({ viewerId: currentViewerId, feedItems: feed?.items || [], lifeline: life });
        setStoriesPageIndex(0);
      } catch (err) {
        console.error("Error loading dashboard data", err);
        if (!cancelled) setLoaded({ viewerId: currentViewerId, feedItems: [], lifeline: null });
      }
    }
    loadData();
    return () => { cancelled = true; };
  }, [viewerReady, centerPersonId, currentViewerId, dataVersion]);

  const isCurrent = loaded.viewerId === currentViewerId;
  const feedItems = isCurrent ? loaded.feedItems : [];
  const lifeline = isCurrent ? loaded.lifeline : null;

  const me = circleData?.me;
  const circle = circleData?.circle;
  const centerName = circleData?.members?.find(m => m.id === centerPersonId)?.name || '';
  const centerFirst = centerName.split(' ')[0];

  // The feed is newest first; story cards are the "story_published" items.
  const storyItems = feedItems.filter(i => i.type === 'story_published' && i.story).map(i => i.story);
  const recentStories = storyItems.slice(0, RECENT_STORY_LIMIT);
  const featuredStory = storyItems[0] || null;

  const totalStoryPages = Math.max(1, Math.ceil(recentStories.length / STORIES_PER_PAGE));
  const pageIndex = Math.min(storiesPageIndex, totalStoryPages - 1);
  const visibleStories = recentStories.slice(pageIndex * STORIES_PER_PAGE, (pageIndex + 1) * STORIES_PER_PAGE);

  // Story count from real data only: stories the viewer can see in the feed and the lifeline.
  const uniqueStoryIds = new Set(storyItems.map(s => s.id));
  (lifeline?.periods || []).forEach(p => (p.stories || []).forEach(s => s?.id && uniqueStoryIds.add(s.id)));
  const storyCount = uniqueStoryIds.size;

  const handleOpenStory = openStory;

  const answers = feedItems.filter(i => i.type === 'question_answered' && i.answer);

  return (
    <div className="album-dashboard">
      <div className="hero-two-column-wrapper">
        {/* Left card: welcome and the newest story */}
        <section className="hero-left-card welcome-memory-card" aria-labelledby="hero-heading">
          <div className="welcome-card-top">
            <div className="hero-greeting">
              {circle?.name && <span className="greeting-lead">Family Chronicle · {circle.name}</span>}
              {me?.name && <span className="greeting-viewer">Welcome back, {me.name.split(' ')[0]}</span>}
            </div>

            <h1 id="hero-heading" className="hero-headline">
              Every family carries a thousand untold stories.
            </h1>

            <p className="hero-supporting">
              The voices and memories that make your family yours, kept simply through
              everyday conversation{centerFirst ? ` with ${centerFirst}` : ''}.
            </p>
          </div>

          {featuredStory ? (
            <div className="hero-featured-memory-spread">
              <figure className="photo-matte-frame hero-card-photo-frame">
                <BlobPhoto
                  photoUrl={featuredStory.photo_url}
                  alt={featuredStory.photo_caption || featuredStory.title}
                  fallback={{ title: featuredStory.title, period: featuredStory.subjects?.[0]?.period, teller: featuredStory.teller?.name }}
                />
                {featuredStory.photo_url && featuredStory.photo_caption && (
                  <figcaption className="photo-caption">
                    <span>{featuredStory.photo_caption}</span>
                  </figcaption>
                )}
              </figure>

              <div className="hero-memory-quote-block">
                {featuredStory.ai_summary && (
                  <>
                    <span className="card-period-tag">AI summary</span>
                    <p className="hero-quote-text">{featuredStory.ai_summary}</p>
                  </>
                )}
                <div className="hero-memory-meta">
                  <span className="hero-memory-title">{featuredStory.title}</span>
                  {featuredStory.teller?.name && (
                    <span className="hero-memory-teller">Told by {featuredStory.teller.name}</span>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="hero-featured-memory-spread">
              <p className="hero-supporting">
                No stories yet. Ask a question and the first one will appear here.
              </p>
            </div>
          )}

          <div className="hero-cta-group">
            {featuredStory && (
              <button
                type="button"
                className="editorial-btn primary"
                onClick={() => handleOpenStory(featuredStory.id)}
              >
                <Play size={17} style={{ marginLeft: '2px' }} />
                <span>Listen to the story</span>
              </button>
            )}

            {featuredStory && (
              <button
                type="button"
                className="hero-read-more-link"
                onClick={() => handleOpenStory(featuredStory.id)}
              >
                <span>Read the full story</span>
                <ArrowRight size={14} />
              </button>
            )}
          </div>
        </section>

        <FamilyTreeCard
          circleData={circleData}
          currentViewerId={currentViewerId}
          storyCount={storyCount}
          onOpenTreeModal={() => setIsTreeModalOpen(true)}
        />
      </div>

      {isTreeModalOpen && (
        <FamilyTreeModal
          onClose={() => setIsTreeModalOpen(false)}
          circleData={circleData}
          onNavigateLifeline={() => navigate({ tab: 'panel', subTab: 'lifeline' })}
          storyCount={storyCount}
        />
      )}

      <div className="editorial-divider">
        <span className="divider-line" />
        <span className="divider-ornament">❦</span>
        <span className="divider-line" />
      </div>

      {/* Recent family stories: the newest story items in the feed */}
      <section className="recent-memories-section" aria-labelledby="recent-heading">
        <div className="section-header-editorial-with-nav">
          <div className="section-header-left">
            <span className="section-eyebrow">Archive Entries</span>
            <h2 id="recent-heading" className="section-title-serif">Recent family stories</h2>
            <p className="section-desc">
              Kept from the family's conversations with Evoca.
            </p>
          </div>

          {totalStoryPages > 1 && (
            <div className="stories-pagination-controls" aria-label="Stories navigation">
              <div className="pagination-indicators">
                <span className="pagination-page-label">
                  Page <strong>{pageIndex + 1}</strong> of <strong>{totalStoryPages}</strong>
                </span>
                <div className="pagination-dots">
                  {Array.from({ length: totalStoryPages }).map((_, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className={`pagination-dot ${idx === pageIndex ? 'active' : ''}`}
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
                  onClick={() => setStoriesPageIndex(pageIndex === 0 ? totalStoryPages - 1 : pageIndex - 1)}
                  aria-label="Previous stories"
                  title="Previous stories"
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  type="button"
                  className="story-nav-arrow-btn next"
                  onClick={() => setStoriesPageIndex((pageIndex + 1) % totalStoryPages)}
                  aria-label="Next stories"
                  title="Next stories"
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}
        </div>

        {recentStories.length === 0 ? (
          <p className="section-desc">No stories yet. They will appear here after the next conversation.</p>
        ) : (
          <div className="editorial-stories-horizontal-grid" key={pageIndex}>
            {visibleStories.map((story) => {
              const period = story.subjects?.[0]?.period;
              const duration = formatDuration(story.duration_ms);
              return (
                <article key={story.id} className="story-editorial-card vertical-card">
                  <figure className="photo-matte-frame card-frame">
                    <BlobPhoto
                      photoUrl={story.photo_url}
                      alt={story.photo_caption || story.title}
                      fallback={{ title: story.title, period, teller: story.teller?.name }}
                    />
                    {story.photo_url && story.photo_caption && (
                      <figcaption className="photo-caption">
                        <span>{story.photo_caption}</span>
                      </figcaption>
                    )}
                  </figure>

                  <div className="story-card-body">
                    {period && <div className="card-period-tag">{periodLabel(period)}</div>}
                    <h3
                      className="card-story-title"
                      onClick={() => handleOpenStory(story.id)}
                      title={`Read "${story.title}"`}
                    >
                      {story.title}
                    </h3>
                    {story.teller?.name && <p className="card-storyteller">Told by {story.teller.name}</p>}

                    {story.ai_summary && (
                      <p className="card-excerpt">
                        <span className="card-period-tag">AI summary · </span>{story.ai_summary}
                      </p>
                    )}

                    <div className="card-action-bar">
                      <button
                        type="button"
                        className="mini-audio-btn"
                        onClick={() => handleOpenStory(story.id)}
                      >
                        <Play size={15} />
                        <span>{duration ? `Listen (${duration})` : 'Listen'}</span>
                      </button>

                      <button
                        type="button"
                        className="read-more-text"
                        onClick={() => handleOpenStory(story.id)}
                      >
                        Read the story →
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <div className="editorial-divider">
        <span className="divider-line" />
        <span className="divider-ornament">❦</span>
        <span className="divider-line" />
      </div>

      {/* Chapters from the lifeline: which have stories and which are still waiting */}
      {lifeline?.periods?.length > 0 && (
        <section className="stories-waiting-section" aria-labelledby="waiting-heading">
          <div className="section-header-editorial">
            <span className="section-eyebrow">Life chapters</span>
            <h2 id="waiting-heading" className="section-title-serif">Stories waiting to be told</h2>
            <p className="section-desc">
              Every chapter holds memories worth hearing. Leave a gentle question for the next morning chat.
            </p>
          </div>

          <div className="waiting-chapters-grid">
            {lifeline.periods.map((p) => {
              const count = p.stories?.length || 0;
              const status = count > 0 ? 'has_stories' : 'waiting';
              const prompt = PERIOD_PROMPTS[p.period] || '';
              const years = periodYears(p.years);
              return (
                <div
                  key={p.period}
                  className={`chapter-card ${status}`}
                  onClick={onOpenAskModal ? () => onOpenAskModal(p.period, prompt) : undefined}
                  title={onOpenAskModal ? 'Ask a question about this chapter' : undefined}
                  role={onOpenAskModal ? 'button' : undefined}
                  tabIndex={onOpenAskModal ? 0 : undefined}
                  onKeyDown={onOpenAskModal ? (e) => e.key === 'Enter' && onOpenAskModal(p.period, prompt) : undefined}
                >
                  <div className="chapter-top">
                    <span className="chapter-name">{periodLabel(p.period)}</span>
                    {years && <span className="chapter-years">{years}</span>}
                  </div>

                  <div className="chapter-status-row">
                    <span className={`status-pill ${status}`}>
                      {count > 0 ? '● Recorded' : '○ Waiting'}
                    </span>
                    <span className="chapter-count">
                      {count > 0 ? `${count} ${count === 1 ? 'story' : 'stories'}` : 'No stories yet'}
                    </span>
                  </div>

                  {onOpenAskModal && (
                    <div className={`chapter-invitation ${count > 0 ? 'recorded' : ''}`}>
                      {count === 0 && prompt && (
                        <>
                          <span className="invitation-label">A gentle question:</span>
                          <p className="invitation-question">"{prompt}"</p>
                        </>
                      )}
                      <span className="ask-prompt-link">
                        {count > 0 ? '+ Ask another question' : '+ Ask this question'}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Answers to the viewer's own questions, and newly kept stories */}
      {feedItems.length > 0 && (
        <section className="family-activity-section" aria-labelledby="activity-heading">
          <div className="section-header-editorial">
            <span className="section-eyebrow">Family activity</span>
            <h2 id="activity-heading" className="section-title-serif">Recent family activity</h2>
            <p className="section-desc">
              Your questions and the answers they brought.
            </p>
          </div>

          <div className="activity-cards-list">
            {answers.map((item) => (
              <AnswerCard key={`${item.question?.id}-${item.answer.story_id}`} item={item} />
            ))}

            {feedItems.filter(i => i.type === 'story_published' && i.story).map((item) => {
              const duration = formatDuration(item.story.duration_ms);
              return (
                <div key={`story-${item.story.id}`} className="activity-item-card publish">
                  <div className="activity-badge-row">
                    <span className="activity-pill beige">New story</span>
                    <span className="activity-timestamp">{formatWhen(item.created_at)}</span>
                  </div>

                  <div className="activity-story-snippet">
                    <h4
                      className="activity-story-name"
                      onClick={() => handleOpenStory(item.story.id)}
                    >
                      {item.story.title}
                    </h4>
                    {item.story.ai_summary && (
                      <p className="activity-story-excerpt">
                        <span className="card-period-tag">AI summary · </span>{item.story.ai_summary}
                      </p>
                    )}
                    <button
                      type="button"
                      className="inline-listen-link"
                      onClick={() => handleOpenStory(item.story.id)}
                    >
                      {duration ? `Listen to the recording (${duration}) →` : 'Open the story →'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
