import React, { useState, useEffect, useCallback } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import {
  HelpCircle,
  Edit3,
  Sparkles,
  ChevronRight,
  CheckCircle2,
  AlertCircle,
  MessageSquarePlus,
  Check,
  X,
  Volume2
} from 'lucide-react';
import { PERIOD_LABELS, periodLabel, periodYears } from '../../utils/periods';
import { formatDuration } from '../../utils/format';
import BlobPhoto from './BlobPhoto';

export default function LifelineView({ onOpenAskModal }) {
  const { setSelectedStoryId, setPanelSubTab, showToast, centerPersonId, currentViewerId, viewerReady, dataVersion } = useApp();
  // Loaded data is keyed by viewer and person; data for another viewer is never shown.
  const [loaded, setLoaded] = useState({ key: null, data: null, failed: false });
  const [editingStoryId, setEditingStoryId] = useState(null);
  const [selectedPeriodTarget, setSelectedPeriodTarget] = useState('');
  const [activeFilter, setActiveFilter] = useState('all'); // 'all' | 'stories' | 'gaps'

  const targetPersonId = centerPersonId;
  const loadKey = `${currentViewerId}:${targetPersonId}`;

  const loadLifeline = useCallback(async () => {
    try {
      const data = await apiClient.getLifeline(targetPersonId);
      setLoaded({ key: loadKey, data, failed: false });
    } catch (err) {
      console.error('Failed to load lifeline:', err);
      setLoaded({ key: loadKey, data: null, failed: true });
    }
  }, [targetPersonId, loadKey]);

  useEffect(() => {
    if (!viewerReady || !targetPersonId) return;
    let cancelled = false;
    apiClient.getLifeline(targetPersonId)
      .then(data => {
        if (!cancelled) setLoaded({ key: loadKey, data, failed: false });
      })
      .catch(err => {
        console.error('Failed to load lifeline:', err);
        if (!cancelled) setLoaded({ key: loadKey, data: null, failed: true });
      });
    return () => { cancelled = true; };
  }, [viewerReady, targetPersonId, loadKey, dataVersion]);

  useEffect(() => {
    if (!editingStoryId) return;
    const onKeyDown = (e) => { if (e.key === 'Escape') setEditingStoryId(null); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [editingStoryId]);

  const current = loaded.key === loadKey ? loaded : { data: null, failed: false };
  const lifelineData = current.data;

  const handleCorrectPeriod = async (storyId, newPeriod) => {
    if (!targetPersonId) return;
    try {
      await apiClient.patchStorySubject(storyId, targetPersonId, newPeriod);
      showToast("Thanks! The chapter is updated.", "info");
      setEditingStoryId(null);
      await loadLifeline();
    } catch (err) {
      console.error(err);
      showToast("The chapter couldn't be changed.", "error");
    }
  };

  const handleOpenStory = (storyId) => {
    setSelectedStoryId(storyId);
    setPanelSubTab('story');
  };

  if (current.failed) {
    return (
      <div className="lifeline-loading-state">
        <p>Not available.</p>
      </div>
    );
  }

  if (!lifelineData) {
    return (
      <div className="lifeline-loading-state" role="status">
        <div className="loading-spinner" />
        <p>Loading the life chapters...</p>
      </div>
    );
  }

  const person = lifelineData.person;
  const firstName = person?.name?.split(' ')[0] || '';
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
      <header className="lifeline-archive-hero">
        <div className="lifeline-hero-top-row">
          <div className="lifeline-elder-profile">
            <div className="elder-portrait-wrapper">
              <div
                className="elder-portrait-img"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'var(--accent-terracotta)',
                  color: '#fff',
                  fontSize: '28px',
                  fontWeight: 600,
                  width: '72px',
                  height: '72px',
                  borderRadius: '50%'
                }}
                aria-hidden="true"
              >
                {person?.name?.charAt(0) || '?'}
              </div>
              <span className="elder-portrait-badge">Storyteller</span>
            </div>

            <div className="elder-narrative-meta">
              <div className="section-eyebrow">LIFE CHAPTERS</div>
              <h1 className="lifeline-elder-title">
                {firstName ? `${firstName}'s life chapters` : 'Life chapters'}
              </h1>
              {person?.birth_year && (
                <p className="lifeline-elder-subtitle">Born {person.birth_year}</p>
              )}
            </div>
          </div>

          <div className="lifeline-metrics-grid">
            <div className="lifeline-metric-card">
              <span className="metric-num">{totalStories}</span>
              <span className="metric-text">{totalStories === 1 ? 'Story' : 'Stories'}</span>
            </div>
            <div className="lifeline-metric-card">
              <span className="metric-num">{recordedChapters}</span>
              <span className="metric-text">Chapters with stories</span>
            </div>
            <div className="lifeline-metric-card gap-highlight">
              <span className="metric-num">{gapChapters}</span>
              <span className="metric-text">Still untold</span>
            </div>
            <div className="lifeline-metric-card">
              <span className="metric-num">{coveragePercent}%</span>
              <span className="metric-text">Of the life covered</span>
            </div>
          </div>
        </div>

        <div className="lifeline-filter-toolbar">
          <p className="lifeline-editorial-quote">
            Every memory belongs to a time. Explore the stories so far, or leave a question for a chapter no one has heard yet.
          </p>

          <div className="lifeline-filter-pills" role="tablist" aria-label="Chapter filter">
            <button
              className={`filter-pill ${activeFilter === 'all' ? 'active' : ''}`}
              onClick={() => setActiveFilter('all')}
            >
              All chapters ({totalChapters})
            </button>
            <button
              className={`filter-pill ${activeFilter === 'stories' ? 'active' : ''}`}
              onClick={() => setActiveFilter('stories')}
            >
              <CheckCircle2 size={14} /> With stories ({recordedChapters})
            </button>
            <button
              className={`filter-pill ${activeFilter === 'gaps' ? 'active' : ''}`}
              onClick={() => setActiveFilter('gaps')}
            >
              <AlertCircle size={14} /> Still untold ({gapChapters})
            </button>
          </div>
        </div>
      </header>

      <main className="lifeline-chronology-stream">
        <div className="timeline-central-spine" aria-hidden="true" />

        {displayedPeriods.map((periodObj, chapterIdx) => {
          const hasStories = periodObj.stories && periodObj.stories.length > 0;
          const chapterNumber = String(chapterIdx + 1).padStart(2, '0');
          const periodTitle = periodLabel(periodObj.period);
          const yearsLabel = periodYears(periodObj.years);

          return (
            <article
              key={periodObj.period || chapterIdx}
              className={`chapter-timeline-section ${hasStories ? 'section-has-stories' : 'section-is-gap'}`}
            >
              <div className="timeline-chapter-node" aria-hidden="true">
                <span className="node-numeral">{chapterNumber}</span>
              </div>

              <div className="chapter-body-card">
                <div className="chapter-header-bar">
                  <div className="chapter-header-titles">
                    <div className="chapter-meta-line">
                      <span className="chapter-tag">CHAPTER {chapterNumber}</span>
                      {yearsLabel && <span className="chapter-era-bullet">·</span>}
                      {yearsLabel && <span className="chapter-era">{yearsLabel}</span>}
                    </div>
                    <h2 className="chapter-main-title">{periodTitle}</h2>
                  </div>

                  <div className="chapter-status-col">
                    {hasStories ? (
                      <span className="chapter-status-pill preserved">
                        <CheckCircle2 size={13} />
                        {periodObj.stories.length} {periodObj.stories.length === 1 ? 'story' : 'stories'}
                      </span>
                    ) : (
                      <span className="chapter-status-pill gap">
                        <AlertCircle size={13} />
                        Still untold
                      </span>
                    )}
                  </div>
                </div>

                {hasStories ? (
                  <div className="chapter-stories-grid">
                    {periodObj.stories.map((story) => {
                      const isEditing = editingStoryId === story.id;
                      const isEstimated = story.estimated || story.period_source === 'ai';
                      const duration = formatDuration(story.duration_ms);

                      return (
                        <div key={story.id} className="chapter-story-item">
                          {story.photo_url && (
                            <figure className="photo-matte-frame card-frame">
                              <BlobPhoto
                                photoUrl={story.photo_url}
                                alt={story.photo_caption || story.title}
                                fallback={{ title: story.title, period: periodObj.period, teller: story.teller?.name }}
                              />
                              {story.photo_caption && (
                                <figcaption className="photo-caption"><span>{story.photo_caption}</span></figcaption>
                              )}
                            </figure>
                          )}
                          <div className="story-narrative-box">
                            <div className="story-headline-row">
                              <h3 className="story-entry-title" onClick={() => handleOpenStory(story.id)}>
                                {story.title}
                              </h3>

                              <div className="story-period-tag-container">
                                <button
                                  type="button"
                                  className={`period-tag-chip ${isEstimated ? 'ai-estimate' : 'verified'}`}
                                  onClick={() => {
                                    setEditingStoryId(isEditing ? null : story.id);
                                    setSelectedPeriodTarget(periodObj.period);
                                  }}
                                  title="Change the chapter"
                                >
                                  {isEstimated ? (
                                    <>
                                      <Sparkles size={12} />
                                      <span>estimated</span>
                                      <Edit3 size={11} className="edit-pen-icon" />
                                    </>
                                  ) : (
                                    <>
                                      <CheckCircle2 size={12} />
                                      <span>Confirmed by family</span>
                                    </>
                                  )}
                                </button>
                              </div>
                            </div>

                            {isEditing && (
                              <div className="inline-period-editor-modal" role="dialog" aria-label="Change the chapter">
                                <div className="editor-modal-title">
                                  <span>Which chapter does this story belong to?</span>
                                  <button
                                    className="modal-close-icon"
                                    onClick={() => setEditingStoryId(null)}
                                    aria-label="Close"
                                  >
                                    <X size={14} />
                                  </button>
                                </div>
                                <div className="period-options-list">
                                  {Object.entries(PERIOD_LABELS).map(([id, label]) => (
                                    <button
                                      key={id}
                                      type="button"
                                      className={`period-select-option ${selectedPeriodTarget === id ? 'selected' : ''}`}
                                      onClick={() => setSelectedPeriodTarget(id)}
                                    >
                                      <span className="opt-label">{label}</span>
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
                                    <Check size={14} /> Save
                                  </button>
                                </div>
                              </div>
                            )}

                            <p className="card-storyteller">
                              {periodTitle}{story.teller?.name ? ` · Told by ${story.teller.name}` : ''}
                            </p>

                            {story.ai_summary && (
                              <p className="story-narrative-summary">{story.ai_summary}</p>
                            )}

                            <div className="story-action-strip">
                              {duration && (
                                <span className="audio-duration-pill">
                                  <Volume2 size={13} />
                                  <span>{duration}</span>
                                </span>
                              )}

                              <button
                                className="story-open-link-btn"
                                onClick={() => handleOpenStory(story.id)}
                              >
                                <span>Listen and read</span>
                                <ChevronRight size={14} />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="chapter-gap-invitation-box">
                    <div className="gap-icon-badge" aria-hidden="true">
                      <HelpCircle size={24} />
                    </div>

                    <div className="gap-invitation-body">
                      <div className="gap-eyebrow">STILL UNTOLD</div>
                      <h3 className="gap-invitation-title">{periodTitle}</h3>
                      <p className="gap-invitation-text">
                        No stories from this chapter yet. A question in the next morning chat could bring the first one.
                      </p>

                      {onOpenAskModal && (
                        <div className="gap-action-buttons-row">
                          <button
                            type="button"
                            className="btn-ask-grandma-primary"
                            onClick={() => onOpenAskModal(periodObj.period, '')}
                          >
                            <MessageSquarePlus size={15} />
                            <span>Ask about this chapter</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </main>
    </div>
  );
}
