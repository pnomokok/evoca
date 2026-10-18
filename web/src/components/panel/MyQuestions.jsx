import React, { useEffect, useState } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import { ChevronRight, MessageSquarePlus } from 'lucide-react';
import { formatWhen } from '../../utils/format';

// The viewer's own questions (GET /api/questions/mine). The API only says "waiting" or "answered";
// anything else is shown as waiting too, and the page never guesses why a question is still waiting.
export default function MyQuestions({ onOpenAskModal, reloadKey }) {
  const { circleData, currentViewerId, viewerReady, dataVersion, setSelectedStoryId, setPanelSubTab } = useApp();
  const [loaded, setLoaded] = useState({ viewerId: null, questions: [], failed: false });

  useEffect(() => {
    if (!viewerReady) return;
    let cancelled = false;
    apiClient.getMyQuestions()
      .then(questions => { if (!cancelled) setLoaded({ viewerId: currentViewerId, questions: questions || [], failed: false }); })
      .catch(err => {
        console.error('Could not load my questions:', err);
        if (!cancelled) setLoaded({ viewerId: currentViewerId, questions: [], failed: true });
      });
    return () => { cancelled = true; };
  }, [viewerReady, currentViewerId, dataVersion, reloadKey]);

  const ready = loaded.viewerId === currentViewerId;
  const questions = ready ? loaded.questions : [];
  const memberName = (id) => circleData?.members?.find(m => m.id === id)?.name || '';
  const center = circleData?.members?.find(m => m.role === 'center');
  const centerFirst = center?.name?.split(' ')[0] || '';

  const openAnswer = (storyId) => {
    setSelectedStoryId(storyId);
    setPanelSubTab('story');
  };

  return (
    <div className="lifeline-archive-page my-questions-page">
      <header className="section-header-editorial">
        <span className="section-eyebrow">Your questions</span>
        <h1 className="section-title-serif">My questions</h1>
        <p className="section-desc">What you asked, and the stories that answered it.</p>
      </header>

      <section className="side-archival-card" aria-label="My questions">
        {!ready && <p className="section-desc" role="status">Loading your questions...</p>}
        {ready && loaded.failed && <p role="alert">Not available.</p>}
        {ready && !loaded.failed && questions.length === 0 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
            <p className="section-desc" style={{ margin: 0 }}>
              You haven't asked anything yet. {centerFirst ? `${centerFirst} answers` : 'Questions are answered'} in the next morning chat.
            </p>
            {onOpenAskModal && (
              <button type="button" className="editorial-btn primary" onClick={() => onOpenAskModal(null, '')}>
                <MessageSquarePlus size={15} />
                <span>Ask a question</span>
              </button>
            )}
          </div>
        )}

        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {questions.map(q => {
            const answered = q.status === 'answered' && Boolean(q.answer_story_id);
            const details = [memberName(q.target_person_id) && `To ${memberName(q.target_person_id)}`, formatWhen(q.created_at)]
              .filter(Boolean).join(' · ');
            const content = (
              <>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <strong>{q.text}</strong>
                  <div className="section-desc">{details}</div>
                </div>
                <span className={`status-pill ${answered ? 'has_stories' : 'waiting'}`}>{answered ? 'Answered' : 'Waiting'}</span>
                {answered && <ChevronRight size={16} aria-hidden="true" />}
              </>
            );
            const rowStyle = { display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 0', borderBottom: '1px solid var(--border-paper)' };
            return (
              <li key={q.id}>
                {answered ? (
                  <button
                    type="button"
                    onClick={() => openAnswer(q.answer_story_id)}
                    title="Open the story that answers it"
                    style={{ ...rowStyle, width: '100%', background: 'none', borderTop: 'none', borderLeft: 'none', borderRight: 'none', textAlign: 'left', cursor: 'pointer', color: 'inherit', font: 'inherit' }}
                  >
                    {content}
                  </button>
                ) : (
                  <div style={rowStyle}>{content}</div>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
