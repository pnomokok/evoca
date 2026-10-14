import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { Calendar, HelpCircle, Edit3, Sparkles, BookOpen, Clock, ChevronRight, CheckCircle2, AlertCircle } from 'lucide-react';

export default function LifelineView({ onOpenAskModal }) {
  const { setSelectedStoryId, setPanelSubTab, showToast } = useApp();
  const [lifelineData, setLifelineData] = useState(null);
  const [editingStoryId, setEditingStoryId] = useState(null);

  useEffect(() => {
    async function loadLifeline() {
      try {
        const data = await apiClient.getLifeline('person_fatma');
        setLifelineData(data);
      } catch (err) {
        console.error(err);
      }
    }
    loadLifeline();
  }, []);

  const handleCorrectPeriod = async (storyId, newPeriod) => {
    try {
      await apiClient.patchStorySubject(storyId, 'person_fatma', newPeriod);
      showToast("Period corrected by family! (Saved to permanent record)", "info");
      setEditingStoryId(null);
      // Reload updated lifeline
      const updated = await apiClient.getLifeline('person_fatma');
      setLifelineData(updated);
    } catch (err) {
      console.error(err);
    }
  };

  const handleOpenStory = (storyId) => {
    setSelectedStoryId(storyId);
    setPanelSubTab('story');
  };

  if (!lifelineData) {
    return <div className="loading-state">Loading Lifeline archive...</div>;
  }

  const totalStories = lifelineData.periods.reduce((acc, p) => acc + (p.stories?.length || 0), 0);
  const totalGaps = lifelineData.gaps?.length || 0;

  return (
    <div className="lifeline-web-container">
      {/* Top Profile & Timeline Stats Header */}
      <div className="lifeline-hero-banner">
        <div className="hero-left-profile">
          <div className="elder-avatar-big">👵</div>
          <div>
            <div className="elder-hero-name">{lifelineData.person.name}'s Lifeline</div>
            <div className="elder-hero-meta">
              Born {lifelineData.person.birth_year} · Akçaabat & Istanbul · Living Memory Archive
            </div>
          </div>
        </div>

        <div className="hero-stats-row">
          <div className="stat-box">
            <span className="stat-number">{totalStories}</span>
            <span className="stat-label">Stories Preserved</span>
          </div>
          <div className="stat-box">
            <span className="stat-number highlight-gap">{totalGaps}</span>
            <span className="stat-label">Chapters with Gaps</span>
          </div>
        </div>
      </div>

      <div className="lifeline-intro-bar">
        <p>
          Stories are chronologically categorized into life chapters. Periods marked with <strong>Gap</strong> invite family members to ask questions and bridge missing memories.
        </p>
      </div>

      {/* Vertical Timeline */}
      <div className="lifeline-periods-tree">
        {lifelineData.periods.map((p, idx) => {
          const hasStories = p.stories && p.stories.length > 0;
          return (
            <section key={idx} className={`timeline-period-node ${hasStories ? 'has-content' : 'is-gap'}`}>
              <div className="timeline-node-marker">
                <span className="marker-dot" />
              </div>

              <div className="timeline-period-content">
                <div className="period-title-bar">
                  <div className="period-title-group">
                    <h3 className="period-title-heading">{p.title || p.period.replace(/_/g, ' ').toUpperCase()}</h3>
                    <span className="period-count-badge">
                      {hasStories ? `${p.stories.length} ${p.stories.length === 1 ? 'memory' : 'memories'}` : 'Gap · No memories yet'}
                    </span>
                  </div>
                </div>

                {/* Stories in Period */}
                {hasStories ? (
                  <div className="period-stories-grid">
                    {p.stories.map((s) => (
                      <div
                        key={s.id}
                        className="lifeline-story-card"
                        onClick={() => handleOpenStory(s.id)}
                      >
                        <div className="card-top-row">
                          <h4 className="story-card-title">{s.title}</h4>
                          <span
                            className={`period-source-badge ${s.period_source === 'family' ? 'verified' : 'ai-estimate'}`}
                            title={s.period_source === 'family' ? 'Verified by family' : 'Estimated by AI'}
                          >
                            {s.period_source === 'family' ? '✓ Family Verified' : 'AI Estimated'}
                          </span>
                        </div>

                        <p className="story-card-summary">{s.ai_summary}</p>

                        <div className="story-card-footer">
                          <span className="duration-tag">
                            <Clock size={12} /> {Math.round(s.duration_ms / 1000)}s audio
                          </span>
                          <span className="view-link">
                            Open Memory <ChevronRight size={14} />
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  /* Gap Card */
                  <div className="timeline-gap-card">
                    <div className="gap-info">
                      <div className="gap-title">
                        <AlertCircle size={16} color="var(--accent-gold)" />
                        <span>Missing Life Chapter</span>
                      </div>
                      <p className="gap-desc">
                        No recordings exist for Grandma's {p.title || p.period}. Ask a question to encourage her morning conversation!
                      </p>
                    </div>
                    <button
                      className="gap-action-btn"
                      onClick={() => onOpenAskModal && onOpenAskModal(p.period)}
                    >
                      + Ask About This Period
                    </button>
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
