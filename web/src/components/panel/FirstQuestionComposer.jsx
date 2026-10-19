import React, { useState } from 'react';
import { AlertTriangle, Send } from 'lucide-react';
import { apiClient } from '../../api/client';
import { QUESTION_PLACEHOLDER, useSendQuestion } from './useSendQuestion';
import { SUGGESTED_QUESTION, usePaneTourTargets } from '../../utils/tour';

// My questions with nothing asked yet: ask the first question right here, through the same
// API, filtering and feedback as the Ask dialog. onSent() reloads the list.
// On the stage, while the guided tour points here, it is prefilled with the tour's question.
export default function FirstQuestionComposer({ onSent }) {
  const [text, setText] = useState('');
  const { send, isSubmitting, filterWarning, clearWarning, centerFirst } = useSendQuestion();
  const tourAsks = usePaneTourTargets().includes('ask');
  const [prefilled, setPrefilled] = useState(false);
  if (tourAsks && !prefilled) {
    setPrefilled(true);
    if (!text) setText(SUGGESTED_QUESTION);
  }

  const submit = async (e) => {
    e.preventDefault();
    if (await send(text)) {
      setText('');
      onSent?.();
    }
  };

  return (
    <form className="first-question-composer" onSubmit={submit} aria-labelledby="first-question-title">
      <h2 id="first-question-title" className="first-question-title">
        {centerFirst ? `Ask ${centerFirst} your first question` : 'Ask your first question'}
      </h2>
      {/* On the stage's phone, one line, so Send stays above the bottom bar. */}
      <p className="section-desc">
        {apiClient.embed
          ? 'Her answer comes back here, in her own voice.'
          : `Evoca brings it up in ${centerFirst ? `${centerFirst}'s` : 'her'} next morning chat, and her answer comes back here, in her own voice.`}
      </p>
      <label className="sr-only" htmlFor="first-question-text">Your question</label>
      <textarea
        id="first-question-text"
        className="archival-textarea"
        placeholder={QUESTION_PLACEHOLDER}
        rows={3}
        value={text}
        onChange={(e) => { setText(e.target.value); if (filterWarning) clearWarning(); }}
      />
      {filterWarning && (
        <div className="sensitive-guard-alert" role="alert">
          <div className="alert-head">
            <AlertTriangle size={15} color="var(--accent-terracotta)" />
            <strong>Not sent</strong>
          </div>
          <p>{filterWarning}</p>
        </div>
      )}
      <div className="first-question-actions">
        <button type="submit" className="editorial-btn primary" disabled={isSubmitting || !text.trim()} data-tour="ask">
          <Send size={15} />
          <span>{isSubmitting ? 'Sending...' : 'Send'}</span>
        </button>
      </div>
    </form>
  );
}
