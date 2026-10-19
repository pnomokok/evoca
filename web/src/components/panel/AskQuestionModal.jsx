import React, { useState } from 'react';
import { X, AlertTriangle, Send } from 'lucide-react';
import { PERIOD_LABELS } from '../../utils/periods';
import Modal from '../Modal';
import { QUESTION_PLACEHOLDER, useSendQuestion } from './useSendQuestion';

const SUGGESTIONS = [
  'How was your house kept warm in winter?',
  'Who was your best friend growing up?',
  'What did holiday mornings look like when you were a child?'
];

// Mounted only while open (see FamilyPanel), so the initial state comes straight from the props.
export default function AskQuestionModal({ onClose, defaultPeriod = null, initialPrompt = '' }) {
  const [questionText, setQuestionText] = useState(initialPrompt || '');
  const [period, setPeriod] = useState(defaultPeriod || '');
  const { send, isSubmitting, filterWarning, clearWarning, centerFirst } = useSendQuestion();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (await send(questionText, period)) onClose();
  };

  return (
    <Modal onClose={onClose} labelledBy="ask-dialog-title">
        <div className="modal-title-row">
          <div>
            <h2 id="ask-dialog-title" className="archival-dialog-title">What would you like to know?</h2>
            <p className="archival-dialog-sub">
              Leave a question {centerFirst ? `${centerFirst} can answer` : 'to be answered'} in the next morning chat.
            </p>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="archival-form">
          <div className="form-group">
            <label className="form-label" htmlFor="ask-period">
              Life chapter (optional)
            </label>
            <select
              id="ask-period"
              className="archival-input-select"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              <option value="">Any chapter</option>
              {Object.entries(PERIOD_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="ask-text">
              Your question
            </label>
            <textarea
              id="ask-text"
              className="archival-textarea"
              placeholder={QUESTION_PLACEHOLDER}
              rows={4}
              value={questionText}
              onChange={(e) => {
                setQuestionText(e.target.value);
                if (filterWarning) clearWarning();
              }}
              autoFocus
            />
          </div>

          {filterWarning && (
            <div className="sensitive-guard-alert" role="alert">
              <div className="alert-head">
                <AlertTriangle size={15} color="var(--accent-terracotta)" />
                <strong>Not sent</strong>
              </div>
              <p>{filterWarning}</p>
            </div>
          )}

          <div className="prompt-suggestions-row">
            <span className="prompts-intro">Ideas:</span>
            <div className="prompt-chips">
              {SUGGESTIONS.map(text => (
                <button key={text} type="button" className="chip-btn" onClick={() => setQuestionText(text)}>
                  "{text}"
                </button>
              ))}
            </div>
          </div>

          <div className="dialog-action-bar">
            <button type="button" className="editorial-btn secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="editorial-btn primary"
              disabled={isSubmitting || !questionText.trim()}
            >
              <Send size={15} />
              <span>{isSubmitting ? "Sending..." : "Send to Evoca"}</span>
            </button>
          </div>
        </form>
    </Modal>
  );
}
