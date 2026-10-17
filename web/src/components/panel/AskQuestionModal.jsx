import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { X, AlertTriangle, Send, Sparkles, HelpCircle } from 'lucide-react';

const PERIOD_OPTIONS = [
  { value: '', label: 'Herhangi Bir Dönem' },
  { value: 'childhood', label: 'Çocukluk (1948 – 1960)' },
  { value: 'youth', label: 'Gençlik (1961 – 1967)' },
  { value: 'marriage_early_years', label: 'İlk Evlilik Yılları (1968 – 1974)' },
  { value: 'raising_children', label: 'Aile Kurma (1975 – 1990)' },
  { value: 'midlife', label: 'Orta Yaş (1991 – 2008)' },
  { value: 'retirement', label: 'Emeklilik (2009 – Günümüz)' }
];

export default function AskQuestionModal({ isOpen, onClose, defaultPeriod = null, initialPrompt = '' }) {
  const { showToast, centerPersonId, circleData } = useApp();
  const [questionText, setQuestionText] = useState('');
  const [period, setPeriod] = useState(defaultPeriod || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [filterWarning, setFilterWarning] = useState(null);

  const centerPerson = circleData?.members?.find(m => m.role === 'center');
  const centerName = centerPerson?.name || 'Fatma Hanım';

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

    const targetId = centerPersonId || circleData?.circle?.center_person_id;
    if (!targetId) {
      showToast("Hedef kişi bulunamadı", "error");
      setIsSubmitting(false);
      return;
    }

    try {
      const res = await apiClient.postQuestion(targetId, questionText.trim(), period || null);
      if (res.status === 'filtered') {
        // Requirement 24: status "filtered" ise message'ı olduğu gibi göster (hangi konu olduğunu söylemez)
        setFilterWarning(res.message);
        showToast("Soru hassas konu filtresine takıldı.", "error");
      } else {
        showToast(`${centerName}'ın sabah sohbeti sırasına soru eklendi!`, "info");
        setQuestionText('');
        onClose();
      }
    } catch (err) {
      console.error(err);
      showToast(err.message || "Soru gönderilemedi", "error");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-sheet archival-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title-row">
          <div>
            <h2 className="archival-dialog-title">Ne öğrenmek istersiniz?</h2>
            <p className="archival-dialog-sub">
              {centerName}'ın sabah sohbetinde cevaplayabileceği bir aile sorusu bırakın.
            </p>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Kapat">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="archival-form">
          <div className="form-group">
            <label className="form-label">
              Hayat Dönemi (İsteğe bağlı)
            </label>
            <select
              className="archival-input-select"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              {PERIOD_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">
              Sorunuz
            </label>
            <textarea
              className="archival-textarea"
              placeholder={`Örn: ${centerName}, çocukluğunuzda kış günleri evde nasıl geçerdi?`}
              rows={4}
              value={questionText}
              onChange={(e) => {
                setQuestionText(e.target.value);
                if (filterWarning) setFilterWarning(null);
              }}
              autoFocus
            />
          </div>

          {/* Filter Warning message as-is from backend (Requirement 24) */}
          {filterWarning && (
            <div className="sensitive-guard-alert">
              <div className="alert-head">
                <AlertTriangle size={15} color="var(--accent-terracotta)" />
                <strong>Hassas Konu Koruması</strong>
              </div>
              <p>{filterWarning}</p>
            </div>
          )}

          <div className="prompt-suggestions-row">
            <span className="prompts-intro">Örnek sorular:</span>
            <div className="prompt-chips">
              <button
                type="button"
                className="chip-btn"
                onClick={() => setQuestionText("Köydeki eviniz kış aylarında nasıl ısıtılırdı?")}
              >
                "Köydeki eviniz kış aylarında nasıl ısıtılırdı?"
              </button>
              <button
                type="button"
                className="chip-btn"
                onClick={() => setQuestionText("Büyükbabamla ilk ne zaman ve nerede tanıştınız?")}
              >
                "Büyükbabamla ilk nerede tanıştınız?"
              </button>
              <button
                type="button"
                className="chip-btn"
                onClick={() => setQuestionText("Çocukken bayram sabahları neler yapardınız?")}
              >
                "Çocukken bayram sabahları neler yapardınız?"
              </button>
            </div>
          </div>

          <div className="dialog-action-bar">
            <button
              type="button"
              className="editorial-btn secondary"
              onClick={onClose}
            >
              Vazgeç
            </button>
            <button
              type="submit"
              className="editorial-btn primary"
              disabled={isSubmitting || !questionText.trim()}
            >
              <Send size={15} />
              <span>{isSubmitting ? "Gönderiliyor..." : "Evoca'ya Gönder"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
