import React from 'react';
import { MessageCircleHeart, X } from 'lucide-react';

// The notice itself: a banner at the top of the stage's phone, or a toast in the archive.
// Tapping it opens the answer in My questions (onOpen).
export default function AnswerNotice({ notice, centerFirst, onOpen, onDismiss, variant = 'toast' }) {
  if (!notice) return null;
  return (
    <div className={`answer-notice ${variant}`} role="status" data-testid="answer-notice">
      <button type="button" className="answer-notice-body" onClick={() => { onOpen(notice.questionId); onDismiss(); }}>
        <span className="answer-notice-icon" aria-hidden="true"><MessageCircleHeart size={18} /></span>
        <span className="answer-notice-text">
          <strong>{centerFirst ? `${centerFirst} answered your question` : 'Your question was answered'}</strong>
          <span>{notice.text}</span>
        </span>
      </button>
      <button type="button" className="answer-notice-close" onClick={onDismiss} aria-label="Dismiss">
        <X size={14} />
      </button>
    </div>
  );
}
