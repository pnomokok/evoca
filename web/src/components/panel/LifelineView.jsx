import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { Calendar, HelpCircle, Edit3, Sparkles, BookOpen, Clock, ChevronRight } from 'lucide-react';

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
      showToast("Period corrected by family! (Saved to record)", "info");
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
    return <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px' }}>Loading Lifeline...</div>;
  }

  return (
    <div className="lifeline-container">
      {/* Elder Profile Header */}
      <div className="lifeline-person-header">
        <div className="elder-avatar-big">👵</div>
        <div>
          <div style={{ fontSize: '18px', fontWeight: 800, color: '#fff' }}>
            {lifelineData.person.name}'s Lifeline
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Born {lifelineData.person.birth_year} · Akçaabat & Istanbul
          </div>
        </div>
      </div>

      <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
        Memories chronologically anchored to life periods. Gaps highlight moments waiting to be shared.
      </div>

      {/* Life Periods List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {lifelineData.periods.map((p, idx) => {
          const hasStories = p.stories && p.stories.length > 0;
          return (
            <div key={idx} className="lifeline-period-block">
              <div className="period-heading">
                <span>{p.title || p.period.replace(/_/g, ' ').toUpperCase()}</span>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  ({p.stories.length} {p.stories.length === 1 ? 'memory' : 'memories'})
                </span>
              </div>

              {/* Story Cards in Period */}
              {hasStories ? (
                p.stories.map((s) => (
                  <div
                    key={s.id}
                    className="feed-card"
                    style={{ cursor: 'pointer', background: 'rgba(28, 35, 56, 0.45)' }}
                    onClick={() => handleOpenStory(s.id)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={{ fontSize: '16px', fontWeight: 700, color: '#fff' }}>
                        {s.title}
                      </div>
                      <span
                        className="feed-badge"
                        style={{
                          background: s.period_source === 'family' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                          color: s.period_source === 'family' ? 'var(--accent-emerald)' : 'var(--accent-gold)'
                        }}
                        title={s.period_source === 'family' ? 'Verified by family' : 'Estimated by AI'}
                      >
                        {s.period_source === 'family' ? 'Family Verified' : 'AI Estimate'}
                      </span>
                    </div>

                    <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      {s.ai_summary}
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Clock size={12} /> {Math.round(s.duration_ms / 1000)}s
                      </span>
                      <span style={{ fontSize: '12px', color: 'var(--accent-gold)', display: 'flex', alignItems: 'center' }}>
                        View Story <ChevronRight size={14} />
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                /* Gap Card (Boş Dönem) */
                <div className="gap-card">
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#e2e8f0' }}>
                      No stories preserved yet
                    </div>
                    <div className="gap-text">
                      Ask Fatma what was happening during this chapter of her life.
                    </div>
                  </div>
                  <button
                    className="ask-gap-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenAskModal(p.period);
                    }}
                  >
                    + Ask Question
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
