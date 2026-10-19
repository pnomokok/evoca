import React, { useEffect, useState } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import { formatWhen } from '../../utils/format';
import Avatar from '../Avatar';
import AnswerCard from './AnswerCard';
import FirstQuestionComposer from './FirstQuestionComposer';
import '../../styles/journal.css';

// The three steps of a question. The API only says "waiting" or "answered", so a question is on
// step 2 until it is answered; the page never guesses why it is still waiting.
const JOURNEY = ['You asked', 'Waiting for her morning chat', 'Answered'];

function Journey({ answered }) {
  const current = answered ? 3 : 2;
  return (
    <ol className="question-journey" aria-label={answered ? 'Answered' : 'Waiting for her morning chat'}>
      {JOURNEY.map((label, i) => {
        const step = i + 1;
        const state = step < current || answered ? 'done' : step === current ? 'now' : 'todo';
        return (
          <li key={label} className={state} aria-current={state === 'now' ? 'step' : undefined}>
            <i aria-hidden="true" />{label}
          </li>
        );
      })}
    </ol>
  );
}

// The viewer's own questions (GET /api/questions/mine), each with its journey; an answered one
// shows its answer card from the feed (GET /api/feed).
// "Ask a question" is in the archive header and the bottom bar.
export default function MyQuestions({ reloadKey }) {
  const { circleData, currentViewerId, viewerReady, dataVersion, openStory } = useApp();
  const [loaded, setLoaded] = useState({ viewerId: null, questions: [], answers: {}, failed: false });
  const [sent, setSent] = useState(0);   // bumped by the first-question composer

  useEffect(() => {
    if (!viewerReady) return;
    let cancelled = false;
    Promise.all([apiClient.getMyQuestions(), apiClient.getFeed().catch(() => null)])
      .then(([questions, feed]) => {
        if (cancelled) return;
        const answers = Object.fromEntries((feed?.items || [])
          .filter(i => i.type === 'question_answered' && i.answer && i.question?.id)
          .map(i => [i.question.id, i]));
        setLoaded({ viewerId: currentViewerId, questions: questions || [], answers, failed: false });
      })
      .catch(err => {
        console.error('Could not load my questions:', err);
        if (!cancelled) setLoaded({ viewerId: currentViewerId, questions: [], answers: {}, failed: true });
      });
    return () => { cancelled = true; };
  }, [viewerReady, currentViewerId, dataVersion, reloadKey, sent]);

  const ready = loaded.viewerId === currentViewerId;
  const questions = ready ? loaded.questions : [];
  const member = (id) => circleData?.members?.find(m => m.id === id) || null;
  const center = circleData?.members?.find(m => m.role === 'center');
  const centerFirst = center?.name?.split(' ')[0] || '';

  return (
    <div className="lifeline-archive-page my-questions-page">
      <header className="section-header-editorial">
        <span className="section-eyebrow">Your questions</span>
        <h1 className="section-title-serif">My questions</h1>
        <p className="section-desc">
          {centerFirst ? `${centerFirst} answers in her morning chat, in her own voice.` : 'Answered in the morning chat, in her own voice.'}
        </p>
      </header>

      {!ready && <p className="section-desc" role="status">Loading your questions...</p>}
      {ready && loaded.failed && <p role="alert">Not available.</p>}
      {ready && !loaded.failed && questions.length === 0 && (
        <FirstQuestionComposer onSent={() => setSent(n => n + 1)} />
      )}

      <ul className="question-list" aria-label="My questions">
        {questions.map(q => {
          const answered = q.status === 'answered' && Boolean(q.answer_story_id);
          const answerItem = answered ? loaded.answers[q.id] : null;
          const target = member(q.target_person_id);
          return (
            <li key={q.id} id={`question-${q.id}`} className="question-item">
              <div className="question-card" data-testid="question-card" data-status={answered ? 'answered' : 'waiting'}>
                <div className="question-head">
                  {target && <Avatar person={target} size={28} />}
                  <span className="question-meta">
                    {[target && `To ${target.name.split(' ')[0]}`, formatWhen(q.created_at)].filter(Boolean).join(' · ')}
                  </span>
                </div>
                <p className="question-text">“{q.text}”</p>
                <Journey answered={answered} />
                {answered && !answerItem && (
                  <button type="button" className="editorial-btn quiet question-open" onClick={() => openStory(q.answer_story_id)}>
                    Open the story that answers it →
                  </button>
                )}
              </div>
              {answerItem && <AnswerCard item={answerItem} showQuestion={false} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
