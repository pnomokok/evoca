import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { X, AlertTriangle, Send, Sparkles, HelpCircle } from 'lucide-react';

export default function AskQuestionModal({ isOpen, onClose, defaultPeriod = null, initialPrompt = '' }) {
  const { showToast } = useApp();
  const [questionText, setQuestionText] = useState('');
  const [period, setPeriod] = useState(defaultPeriod || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [filterWarning, setFilterWarning] = useState(null);

  useEffect(() => {
    if (isOpen) {
      if (initialPrompt) setQuestionText(initialPrompt);
      if (defaultPeriod) setPeriod(defaultPeriod);
      setFilterWarning(null);
    }
  }, [isOpen, initialPrompt, defaultPeriod]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!questionText.trim()) return;

    setIsSubmitting(true);
    setFilterWarning(null);

    try {
      const res = await apiClient.postQuestion('person_fatma', questionText.trim(), period || null);
      if (res.status === 'filtered') {
        setFilterWarning(res.message);
        showToast("Question was held by the family sensitive topic guard.", "error");
      } else {
        showToast("Question placed gently in Grandma's morning conversation queue!", "info");
        setQuestionText('');
        onClose();
      }
    } catch (err) {
      console.error(err);
      showToast("Unable to send question", "error");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-sheet archival-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title-row">
          <div>
            <h2 className="archival-dialog-title">What would you like to know?</h2>
            <p className="archival-dialog-sub">
              Ask a question that might unlock another family memory.
            </p>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close dialog">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="archival-form">
          <div className="form-group">
            <label className="form-label">
              Life Chapter (Optional)
            </label>
            <select
              className="archival-input-select"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              <option value="">Any Life Chapter</option>
              <option value="childhood">Childhood (1948 – 1960)</option>
              <option value="youth">Youth (1961 – 1967)</option>
              <option value="marriage_early_years">Early Adulthood & Marriage (1968 – 1974)</option>
              <option value="raising_children">Raising a Family (1975 – 1990)</option>
              <option value="midlife">Midlife (1991 – 2008)</option>
              <option value="retirement">Retirement (2009 – Present)</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">
              Your Question
            </label>
            <textarea
              className="archival-textarea"
              placeholder="e.g. Grandma, what was your childhood home like?"
              rows={4}
              value={questionText}
              onChange={(e) => {
                setQuestionText(e.target.value);
                if (filterWarning) setFilterWarning(null);
              }}
              autoFocus
            />
          </div>

          {filterWarning && (
            <div className="sensitive-guard-alert">
              <div className="alert-head">
                <AlertTriangle size={15} color="var(--accent-terracotta)" />
                <strong>Sensitive Topic Guard</strong>
              </div>
              <p>{filterWarning}</p>
            </div>
          )}

          <div className="prompt-suggestions-row">
            <span className="prompts-intro">Inspiration prompts:</span>
            <div className="prompt-chips">
              <button
                type="button"
                className="chip-btn"
                onClick={() => setQuestionText("What was your childhood home like?")}
              >
                "What was your childhood home like?"
              </button>
              <button
                type="button"
                className="chip-btn"
                onClick={() => setQuestionText("How did you meet Grandpa?")}
              >
                "How did you meet Grandpa?"
              </button>
              <button
                type="button"
                className="chip-btn"
                onClick={() => setQuestionText("What family tradition do you remember most?")}
              >
                "What family tradition do you remember most?"
              </button>
              <button
                type="button"
                className="chip-btn filter-test-chip"
                onClick={() => setQuestionText("What happened during the 1977 traffic accident?")}
                title="Test sensitive topic filter behavior"
              >
                Test filter: "1977 traffic accident"
              </button>
            </div>
          </div>

          <div className="dialog-action-bar">
            <button
              type="button"
              className="editorial-btn secondary"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="editorial-btn primary"
              disabled={isSubmitting || !questionText.trim()}
            >
              <Send size={15} />
              <span>{isSubmitting ? "Delivering..." : "Send question to Evoca"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
