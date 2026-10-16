import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { 
  Calendar, 
  HelpCircle, 
  Edit3, 
  Sparkles, 
  BookOpen, 
  Clock, 
  ChevronRight, 
  CheckCircle2, 
  AlertCircle,
  Play,
  MessageSquarePlus,
  Filter,
  MapPin,
  Check,
  X,
  Volume2
} from 'lucide-react';

const PERIOD_OPTIONS = [
  { id: 'childhood', label: 'Childhood (0-12)', era: '1948 – 1960' },
  { id: 'youth', label: 'Youth & Discovery (13-20)', era: '1961 – 1967' },
  { id: 'marriage_early_years', label: 'Early Adulthood & Marriage', era: '1968 – 1972' },
  { id: 'raising_children', label: 'Raising a Family', era: '1973 – 1984' },
  { id: 'midlife', label: 'Midlife & Journeys', era: '1985 – 2004' },
  { id: 'retirement', label: 'Golden Years & Wisdom', era: '2005 – Present' }
];

export default function LifelineView({ onOpenAskModal }) {
  const { setSelectedStoryId, setPanelSubTab, showToast } = useApp();
  const [lifelineData, setLifelineData] = useState(null);
  const [editingStoryId, setEditingStoryId] = useState(null);
  const [selectedPeriodTarget, setSelectedPeriodTarget] = useState('');
  const [activeFilter, setActiveFilter] = useState('all'); // 'all' | 'stories' | 'gaps'

  useEffect(() => {
    async function loadLifeline() {
      try {
        const data = await apiClient.getLifeline('person_fatma');
        setLifelineData(data);
      } catch (err) {
        console.error('Failed to load lifeline:', err);
      }
    }
    loadLifeline();
  }, []);

  const handleCorrectPeriod = async (storyId, newPeriod) => {
    try {
      await apiClient.patchStorySubject(storyId, 'person_fatma', newPeriod);
      showToast("Life chapter verified and saved to family archive!", "info");
      setEditingStoryId(null);
      // Reload updated lifeline
      const updated = await apiClient.getLifeline('person_fatma');
      setLifelineData(updated);
    } catch (err) {
      console.error(err);
      showToast("Could not update life chapter", "error");
    }
  };

  const handleOpenStory = (storyId) => {
    setSelectedStoryId(storyId);
    setPanelSubTab('story');
  };

  if (!lifelineData) {
    return (
      <div className="lifeline-loading-state">
        <div className="loading-spinner" />
        <p>Opening family chronological archive...</p>
      </div>
    );
  }

  const periods = lifelineData.periods || [];
  const totalStories = periods.reduce((acc, p) => acc + (p.stories?.length || 0), 0);
  const totalChapters = periods.length;
  const recordedChapters = periods.filter(p => p.stories && p.stories.length > 0).length;
  const gapChapters = totalChapters - recordedChapters;
  const coveragePercent = Math.round((recordedChapters / (totalChapters || 1)) * 100);

  const displayedPeriods = periods.filter(p => {
    const hasStories = p.stories && p.stories.length > 0;
    if (activeFilter === 'stories') return hasStories;
    if (activeFilter === 'gaps') return !hasStories;
    return true;
  });

  return (
    <div className="lifeline-archive-page">
      {/* Editorial Header / Living Timeline Hero */}
      <header className="lifeline-archive-hero">
        <div className="lifeline-hero-top-row">
          <div className="lifeline-elder-profile">
            <div className="elder-portrait-wrapper">
              <img 
                src={lifelineData.person.avatar_url || "/grandma_fatma.jpg"} 
                alt={lifelineData.person.name}
                className="elder-portrait-img"
                onError={(e) => {
                  e.target.onerror = null;
                  e.target.src = "/family_hero.jpg";
                }}
              />
              <span className="elder-portrait-badge">Central Teller</span>
            </div>

            <div className="elder-narrative-meta">
              <div className="section-eyebrow">CHRONOLOGICAL MEMORY MAP</div>
              <h1 className="lifeline-elder-title">{lifelineData.person.name}'s Life Chapters</h1>
              <p className="lifeline-elder-subtitle">
                Born {lifelineData.person.birth_year} in Akçaabat · 76 Years of Family Heritage · Living Audio Archive
              </p>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="lifeline-metrics-grid">
            <div className="lifeline-metric-card">
              <span className="metric-num">{totalStories}</span>
              <span className="metric-text">Stories Preserved</span>
            </div>
            <div className="lifeline-metric-card">
              <span className="metric-num">{recordedChapters}</span>
              <span className="metric-text">Recorded Eras</span>
            </div>
            <div className="lifeline-metric-card gap-highlight">
              <span className="metric-num">{gapChapters}</span>
              <span className="metric-text">Untold Gaps</span>
            </div>
            <div className="lifeline-metric-card">
              <span className="metric-num">{coveragePercent}%</span>
              <span className="metric-text">Timeline Mapped</span>
            </div>
          </div>
        </div>

        {/* Narrative Description & Filter Controls */}
        <div className="lifeline-filter-toolbar">
          <p className="lifeline-editorial-quote">
            “Every family memory belongs to a season of time. Explore Grandma's journey across the decades, 
            or ask a morning question to bridge the untold chapters.”
          </p>

          <div className="lifeline-filter-pills" role="tablist" aria-label="Timeline filter">
            <button 
              className={`filter-pill ${activeFilter === 'all' ? 'active' : ''}`}
              onClick={() => setActiveFilter('all')}
            >
              All Chapters ({totalChapters})
            </button>
            <button 
              className={`filter-pill ${activeFilter === 'stories' ? 'active' : ''}`}
              onClick={() => setActiveFilter('stories')}
            >
              <CheckCircle2 size={14} /> Preserved Memories ({recordedChapters})
            </button>
            <button 
              className={`filter-pill ${activeFilter === 'gaps' ? 'active' : ''}`}
              onClick={() => setActiveFilter('gaps')}
            >
              <AlertCircle size={14} /> Untold Gaps ({gapChapters})
            </button>
          </div>
        </div>
      </header>

      {/* Chronological Timeline Stream */}
      <main className="lifeline-chronology-stream">
        <div className="timeline-central-spine" aria-hidden="true" />

        {displayedPeriods.map((periodObj, chapterIdx) => {
          const hasStories = periodObj.stories && periodObj.stories.length > 0;
          const chapterNumber = String(chapterIdx + 1).padStart(2, '0');
          const eraLabel = periodObj.era || (PERIOD_OPTIONS.find(o => o.id === periodObj.period)?.era) || '';

          return (
            <article 
              key={periodObj.period || chapterIdx}
              className={`chapter-timeline-section ${hasStories ? 'section-has-stories' : 'section-is-gap'}`}
            >
              {/* Timeline Milestone Marker */}
              <div className="timeline-chapter-node">
                <span className="node-numeral">{chapterNumber}</span>
              </div>

              {/* Main Chapter Content Card */}
              <div className="chapter-body-card">
                {/* Chapter Banner */}
                <div className="chapter-header-bar">
                  <div className="chapter-header-titles">
                    <div className="chapter-meta-line">
                      <span className="chapter-tag">CHAPTER {chapterNumber}</span>
                      {eraLabel && <span className="chapter-era-bullet">·</span>}
                      {eraLabel && <span className="chapter-era">{eraLabel}</span>}
                    </div>
                    <h2 className="chapter-main-title">{periodObj.title || periodObj.period}</h2>
                    {periodObj.description && (
                      <p className="chapter-curator-desc">{periodObj.description}</p>
                    )}
                  </div>

                  <div className="chapter-status-col">
                    {hasStories ? (
                      <span className="chapter-status-pill preserved">
                        <CheckCircle2 size={13} />
                        {periodObj.stories.length} {periodObj.stories.length === 1 ? 'Story' : 'Stories'} Preserved
                      </span>
                    ) : (
                      <span className="chapter-status-pill gap">
                        <AlertCircle size={13} />
                        Untold Chapter · Gap
                      </span>
                    )}
                  </div>
                </div>

                {/* Chapter Stories List or Gap Prompt Box */}
                {hasStories ? (
                  <div className="chapter-stories-grid">
                    {periodObj.stories.map((story) => {
                      const isEditing = editingStoryId === story.id;
                      const isFamilyVerified = story.period_source === 'family';

                      return (
                        <div key={story.id} className="chapter-story-item">
                          {/* Photo Frame */}
                          {story.photo_url && (
                            <div className="story-photo-matting" onClick={() => handleOpenStory(story.id)}>
                              <img 
                                src={story.photo_url} 
                                alt={story.title} 
                                className="story-archival-photo"
                                onError={(e) => {
                                  e.target.onerror = null;
                                  e.target.src = "/mulberry_memory.jpg";
                                }}
                              />
                              {(story.place || story.year) && (
                                <span className="story-photo-caption-handwriting">
                                  {story.place ? `${story.place}` : ''}{story.year ? `, ${story.year}` : ''}
                                </span>
                              )}
                            </div>
                          )}

                          {/* Story Narrative Details */}
                          <div className="story-narrative-box">
                            <div className="story-headline-row">
                              <h3 className="story-entry-title" onClick={() => handleOpenStory(story.id)}>
                                {story.title}
                              </h3>

                              {/* Period Verification Tag / Edit Trigger */}
                              <div className="story-period-tag-container">
                                <button
                                  type="button"
                                  className={`period-tag-chip ${isFamilyVerified ? 'verified' : 'ai-estimate'}`}
                                  onClick={() => {
                                    setEditingStoryId(isEditing ? null : story.id);
                                    setSelectedPeriodTarget(periodObj.period);
                                  }}
                                  title="Click to verify or assign to another life chapter"
                                >
                                  {isFamilyVerified ? (
                                    <>
                                      <CheckCircle2 size={12} />
                                      <span>Family Verified</span>
                                    </>
                                  ) : (
                                    <>
                                      <Sparkles size={12} />
                                      <span>AI Estimate</span>
                                      <Edit3 size={11} className="edit-pen-icon" />
                                    </>
                                  )}
                                </button>
                              </div>
                            </div>

                            {/* Inline Period Editor Popover */}
                            {isEditing && (
                              <div className="inline-period-editor-modal" role="dialog" aria-label="Reassign Life Chapter">
                                <div className="editor-modal-title">
                                  <span>Reassign Life Chapter for this Memory</span>
                                  <button 
                                    className="modal-close-icon"
                                    onClick={() => setEditingStoryId(null)}
                                    aria-label="Close"
                                  >
                                    <X size={14} />
                                  </button>
                                </div>
                                <p className="editor-modal-desc">
                                  Select the accurate period for Grandma's permanent record:
                                </p>
                                <div className="period-options-list">
                                  {PERIOD_OPTIONS.map((opt) => (
                                    <button
                                      key={opt.id}
                                      type="button"
                                      className={`period-select-option ${selectedPeriodTarget === opt.id ? 'selected' : ''}`}
                                      onClick={() => setSelectedPeriodTarget(opt.id)}
                                    >
                                      <span className="opt-label">{opt.label}</span>
                                      <span className="opt-era">{opt.era}</span>
                                    </button>
                                  ))}
                                </div>
                                <div className="editor-modal-actions">
                                  <button
                                    type="button"
                                    className="btn-cancel-edit"
                                    onClick={() => setEditingStoryId(null)}
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    type="button"
                                    className="btn-save-edit"
                                    onClick={() => handleCorrectPeriod(story.id, selectedPeriodTarget)}
                                  >
                                    <Check size={14} /> Save Verification
                                  </button>
                                </div>
                              </div>
                            )}

                            {/* Excerpt / AI Summary */}
                            <p className="story-narrative-summary">
                              {story.excerpt || story.ai_summary}
                            </p>

                            {/* Card Footer Actions */}
                            <div className="story-action-strip">
                              <span className="audio-duration-pill">
                                <Volume2 size={13} />
                                <span>{Math.round((story.duration_ms || 30000) / 1000)}s voice recording</span>
                              </span>

                              <button 
                                className="story-open-link-btn"
                                onClick={() => handleOpenStory(story.id)}
                              >
                                <span>Listen & Explore</span>
                                <ChevronRight size={14} />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  /* Gap Bridge Invitation Card */
                  <div className="chapter-gap-invitation-box">
                    <div className="gap-icon-badge">
                      <HelpCircle size={24} />
                    </div>

                    <div className="gap-invitation-body">
                      <div className="gap-eyebrow">UNTOLD FAMILY CHAPTER</div>
                      <h3 className="gap-invitation-title">Bridge This Chapter's Memories</h3>
                      <p className="gap-invitation-text">
                        No audio recordings have been captured yet for Grandma's <strong>{periodObj.title}</strong>. 
                        Prompting her during her morning coffee helps unlock these precious recollections.
                      </p>

                      {periodObj.invitationPrompt && (
                        <div className="curated-prompt-quote-box">
                          <span className="quote-label">Suggested Morning Prompt:</span>
                          <p className="quote-text">“{periodObj.invitationPrompt}”</p>
                        </div>
                      )}

                      <div className="gap-action-buttons-row">
                        <button
                          type="button"
                          className="btn-ask-grandma-primary"
                          onClick={() => onOpenAskModal && onOpenAskModal(periodObj.period, periodObj.invitationPrompt || '')}
                        >
                          <MessageSquarePlus size={15} />
                          <span>Ask Grandma This Question</span>
                        </button>

                        <button
                          type="button"
                          className="btn-ask-custom-topic"
                          onClick={() => onOpenAskModal && onOpenAskModal(periodObj.period, '')}
                        >
                          <span>Ask a Custom Question</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </main>

      {/* Footnote / Living Archive Philosophy */}
      <footer className="lifeline-bottom-footnote">
        <p>
          Each recorded memory is verified and permanently linked into the Yilmaz family living archive. 
          New morning conversations automatically enrich Grandma's life chapters.
        </p>
      </footer>
    </div>
  );
}
