import React, { useState } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { X, AlertTriangle, Send, Sparkles } from 'lucide-react';

export default function AskQuestionModal({ isOpen, onClose, defaultPeriod = null }) {
  const { showToast } = useApp();
  const [questionText, setQuestionText] = useState('');
  const [period, setPeriod] = useState(defaultPeriod || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [filterWarning, setFilterWarning] = useState(null);

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
        showToast("Question blocked by sensitive topic filter.", "error");
      } else {
        showToast("Question queued for Grandma's morning conversation!", "info");
        setQuestionText('');
        onClose();
      }
    } catch (err) {
      console.error(err);
      showToast("Failed to submit question", "error");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title-row">
          <div className="modal-title">Ask Grandma a Question</div>
          <button className="close-btn" onClick={onClose}><X size={20} /></button>
        </div>

        <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
          When Grandma talks with Evoca, your question will be naturally introduced during the conversation.
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px', display: 'block' }}>
              Target Life Period (Optional)
            </label>
            <select
              className="viewer-select"
              style={{ width: '100%' }}
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              <option value="">Any Life Period</option>
              <option value="childhood">Childhood (0-12)</option>
              <option value="youth">Youth (13-20)</option>
              <option value="marriage_early_years">Early Marriage</option>
              <option value="raising_children">Raising Children</option>
              <option value="midlife">Midlife</option>
              <option value="retirement">Retirement</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px', display: 'block' }}>
              Your Question
            </label>
            <textarea
              className="modal-textarea"
              placeholder="e.g. Grandma, who was your best friend during school?"
              value={questionText}
              onChange={(e) => {
                setQuestionText(e.target.value);
                if (filterWarning) setFilterWarning(null);
              }}
            />
          </div>

          {filterWarning && (
            <div className="modal-warning-box">
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, marginBottom: '2px' }}>
                <AlertTriangle size={15} color="#ef4444" /> Sensitive Topic Guard
              </div>
              <div>{filterWarning}</div>
            </div>
          )}

          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Try quick examples:</span>
            <button
              type="button"
              style={{ background: 'rgba(255,255,255,0.06)', border: 'none', color: 'var(--text-secondary)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
              onClick={() => setQuestionText("Did you ever meet anyone famous growing up?")}
            >
              "Meet anyone famous?"
            </button>
            <button
              type="button"
              style={{ background: 'rgba(239,68,68,0.1)', border: 'none', color: '#fca5a5', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
              onClick={() => setQuestionText("What happened during the 1977 traffic accident?")}
              title="Test sensitive topic filter"
            >
              Test Filter: "1977 traffic accident"
            </button>
          </div>

          <button
            type="submit"
            className="modal-submit-btn"
            disabled={isSubmitting || !questionText.trim()}
          >
            {isSubmitting ? "Checking & Submitting..." : "Send Question to Evoca"}
          </button>
        </form>
      </div>
    </div>
  );
}
