import React, { useState, useEffect } from 'react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../api/client';
import { 
  Calendar, 
  HelpCircle, 
  Edit3, 
  Sparkles, 
  BookOpen, 
  Clock, 
  ChevronRight, 
  CheckCircle2, 
  AlertCircle,
  Play,
  MessageSquarePlus,
  Filter,
  MapPin,
  Check,
  X,
  Volume2
} from 'lucide-react';

const PERIOD_CONFIG = [
  { id: 'childhood', label: 'Çocukluk', era: '1948 – 1960', desc: 'Akçaabat köyünde çocukluk günleri, dut ağacı ve karlı okul yolları.' },
  { id: 'youth', label: 'Gençlik', era: '1961 – 1967', desc: 'Genç kızlık dönemi, terzi dükkanı, zeytin hasadı ve liman pazarı.' },
  { id: 'marriage_early_years', label: 'İlk Evlilik Yılları', era: '1968 – 1974', desc: 'Sahildeki taş eve yerleşme, ilk yıllar ve ortak hayatın kuruluşu.' },
  { id: 'raising_children', label: 'Aile Kurma', era: '1975 – 1990', desc: 'Çocukların büyümesi, taş verandada semaver sohbetleri.' },
  { id: 'midlife', label: 'Orta Yaş', era: '1991 – 2008', desc: 'Yolculuklar, aile düğünleri ve yeni neslin doğuşu.' },
  { id: 'retirement', label: 'Emeklilik', era: '2009 – Günümüz', desc: 'Sakin sabah kahveleri, torunlarla sohbetler ve bahçe günleri.' }
];

export default function LifelineView({ onOpenAskModal }) {
  const { setSelectedStoryId, setPanelSubTab, showToast, centerPersonId, currentViewerId } = useApp();
  const [lifelineData, setLifelineData] = useState(null);
  const [editingStoryId, setEditingStoryId] = useState(null);
  const [selectedPeriodTarget, setSelectedPeriodTarget] = useState('');
  const [activeFilter, setActiveFilter] = useState('all'); // 'all' | 'stories' | 'gaps'

  const targetPersonId = centerPersonId;

  const loadLifeline = async () => {
    if (!targetPersonId) return;
    try {
      const data = await apiClient.getLifeline(targetPersonId);
      setLifelineData(data);
    } catch (err) {
      console.error('Failed to load lifeline:', err);
    }
  };

  useEffect(() => {
    loadLifeline();
  }, [targetPersonId, currentViewerId]);

  const handleCorrectPeriod = async (storyId, newPeriod) => {
    if (!targetPersonId) return;
    try {
      await apiClient.patchStorySubject(storyId, targetPersonId, newPeriod);
      showToast("Dönem güncellendi ve aile çizgisine işlendi!", "info");
      setEditingStoryId(null);
      await loadLifeline();
    } catch (err) {
      console.error(err);
      showToast(err.message || "Dönem güncellenemedi", "error");
    }
  };

  const handleOpenStory = (storyId) => {
    setSelectedStoryId(storyId);
    setPanelSubTab('story');
  };

  if (!lifelineData) {
    return (
      <div className="lifeline-loading-state">
        <div className="loading-spinner" />
        <p>Aile hayat çizgisi yükleniyor...</p>
      </div>
    );
  }

  const periods = lifelineData.periods || [];
  const gapsSet = new Set(lifelineData.gaps || []);
  const totalStories = periods.reduce((acc, p) => acc + (p.stories?.length || 0), 0);
  const totalChapters = periods.length;
  const recordedChapters = periods.filter(p => p.stories && p.stories.length > 0).length;
  const gapChapters = periods.filter(p => !p.stories || p.stories.length === 0).length;
  const coveragePercent = Math.round((recordedChapters / (totalChapters || 1)) * 100);

  const displayedPeriods = periods.filter(p => {
    const hasStories = p.stories && p.stories.length > 0;
    if (activeFilter === 'stories') return hasStories;
    if (activeFilter === 'gaps') return !hasStories;
    return true;
  });

  return (
    <div className="lifeline-archive-page">
      {/* Editorial Header / Living Timeline Hero */}
      <header className="lifeline-archive-hero">
        <div className="lifeline-hero-top-row">
          <div className="lifeline-elder-profile">
            <div className="elder-portrait-wrapper">
              <div 
                className="elder-portrait-img"
                style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center', 
                  background: 'var(--accent-terracotta)', 
                  color: '#fff', 
                  fontSize: '28px', 
                  fontWeight: 600,
                  width: '72px',
                  height: '72px',
                  borderRadius: '50%'
                }}
              >
                {lifelineData.person?.name?.charAt(0) || 'F'}
              </div>
              <span className="elder-portrait-badge">Merkez Anlatan</span>
            </div>

            <div className="elder-narrative-meta">
              <div className="section-eyebrow">KRONOLOJİK HAYAT ÇİZGİSİ</div>
              <h1 className="lifeline-elder-title">{lifelineData.person?.name}'ın Hayat Dönemleri</h1>
              <p className="lifeline-elder-subtitle">
                Doğum {lifelineData.person?.birth_year || 1948} · Yaşayan Sözlü Aile Arşivi
              </p>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="lifeline-metrics-grid">
            <div className="lifeline-metric-card">
              <span className="metric-num">{totalStories}</span>
              <span className="metric-text">Kayıtlı Hikâye</span>
            </div>
            <div className="lifeline-metric-card">
              <span className="metric-num">{recordedChapters}</span>
              <span className="metric-text">Belgelenen Dönem</span>
            </div>
            <div className="lifeline-metric-card gap-highlight">
              <span className="metric-num">{gapChapters}</span>
              <span className="metric-text">Anlatılmamış Boşluk</span>
            </div>
            <div className="lifeline-metric-card">
              <span className="metric-num">{coveragePercent}%</span>
              <span className="metric-text">Haritalanan Çizgi</span>
            </div>
          </div>
        </div>

        {/* Narrative Description & Filter Controls */}
        <div className="lifeline-filter-toolbar">
          <p className="lifeline-editorial-quote">
            “Her anı bir zamana aittir. Yıllar boyunca biriken hikâyeleri keşfedin ya da anlatılmamış dönemler için sabah kahvesine bir soru bırakın.”
          </p>

          <div className="lifeline-filter-pills" role="tablist" aria-label="Timeline filter">
            <button 
              className={`filter-pill ${activeFilter === 'all' ? 'active' : ''}`}
              onClick={() => setActiveFilter('all')}
            >
              Tüm Dönemler ({totalChapters})
            </button>
            <button 
              className={`filter-pill ${activeFilter === 'stories' ? 'active' : ''}`}
              onClick={() => setActiveFilter('stories')}
            >
              <CheckCircle2 size={14} /> Kayıtlı Anılar ({recordedChapters})
            </button>
            <button 
              className={`filter-pill ${activeFilter === 'gaps' ? 'active' : ''}`}
              onClick={() => setActiveFilter('gaps')}
            >
              <AlertCircle size={14} /> Anlatılmamış Boşluklar ({gapChapters})
            </button>
          </div>
        </div>
      </header>

      {/* Chronological Timeline Stream */}
      <main className="lifeline-chronology-stream">
        <div className="timeline-central-spine" aria-hidden="true" />

        {displayedPeriods.map((periodObj, chapterIdx) => {
          const hasStories = periodObj.stories && periodObj.stories.length > 0;
          const chapterNumber = String(chapterIdx + 1).padStart(2, '0');
          const cfg = PERIOD_CONFIG.find(c => c.id === periodObj.period) || {};
          const periodTitle = cfg.label || periodObj.period;
          const eraLabel = cfg.era || '';
          const isGap = gapsSet.has(periodObj.period) || !hasStories;

          return (
            <article 
              key={periodObj.period || chapterIdx}
              className={`chapter-timeline-section ${hasStories ? 'section-has-stories' : 'section-is-gap'}`}
            >
              {/* Timeline Milestone Marker */}
              <div className="timeline-chapter-node">
                <span className="node-numeral">{chapterNumber}</span>
              </div>

              {/* Main Chapter Content Card */}
              <div className="chapter-body-card">
                {/* Chapter Banner */}
                <div className="chapter-header-bar">
                  <div className="chapter-header-titles">
                    <div className="chapter-meta-line">
                      <span className="chapter-tag">DÖNEM {chapterNumber}</span>
                      {eraLabel && <span className="chapter-era-bullet">·</span>}
                      {eraLabel && <span className="chapter-era">{eraLabel}</span>}
                    </div>
                    <h2 className="chapter-main-title">{periodTitle}</h2>
                    {cfg.desc && (
                      <p className="chapter-curator-desc">{cfg.desc}</p>
                    )}
                  </div>

                  <div className="chapter-status-col">
                    {hasStories ? (
                      <span className="chapter-status-pill preserved">
                        <CheckCircle2 size={13} />
                        {periodObj.stories.length} {periodObj.stories.length === 1 ? 'Hikâye' : 'Hikâye'}
                      </span>
                    ) : (
                      <span className="chapter-status-pill gap">
                        <AlertCircle size={13} />
                        Anlatılmamış Dönem · Boşluk
                      </span>
                    )}
                  </div>
                </div>

                {/* Chapter Stories List or Gap Prompt Box */}
                {hasStories ? (
                  <div className="chapter-stories-grid">
                    {periodObj.stories.map((story) => {
                      const isEditing = editingStoryId === story.id;
                      const isFamilyVerified = story.period_source === 'family';
                      const isEstimated = story.estimated || story.period_source === 'ai';

                      return (
                        <div key={story.id} className="chapter-story-item">
                          {/* Story Narrative Details */}
                          <div className="story-narrative-box">
                            <div className="story-headline-row">
                              <h3 className="story-entry-title" onClick={() => handleOpenStory(story.id)}>
                                {story.title}
                              </h3>

                              {/* Period Tag & Tahmini Badge (Requirement 16) */}
                              <div className="story-period-tag-container">
                                <button
                                  type="button"
                                  className={`period-tag-chip ${isFamilyVerified ? 'verified' : 'ai-estimate'}`}
                                  onClick={() => {
                                    setEditingStoryId(isEditing ? null : story.id);
                                    setSelectedPeriodTarget(periodObj.period);
                                  }}
                                  title="Dönemi düzeltmek için tıklayın"
                                >
                                  {isEstimated ? (
                                    <>
                                      <Sparkles size={12} />
                                      <span>tahmini</span>
                                      <Edit3 size={11} className="edit-pen-icon" />
                                    </>
                                  ) : (
                                    <>
                                      <CheckCircle2 size={12} />
                                      <span>Doğrulandı</span>
                                    </>
                                  )}
                                </button>
                              </div>
                            </div>

                            {/* Inline Period Editor Popover */}
                            {isEditing && (
                              <div className="inline-period-editor-modal" role="dialog" aria-label="Hayat Dönemini Değiştir">
                                <div className="editor-modal-title">
                                  <span>Bu Anının Hayat Dönemini Düzeltin</span>
                                  <button 
                                    className="modal-close-icon"
                                    onClick={() => setEditingStoryId(null)}
                                    aria-label="Kapat"
                                  >
                                    <X size={14} />
                                  </button>
                                </div>
                                <p className="editor-modal-desc">
                                  Doğru dönemi seçin:
                                </p>
                                <div className="period-options-list">
                                  {PERIOD_CONFIG.map((opt) => (
                                    <button
                                      key={opt.id}
                                      type="button"
                                      className={`period-select-option ${selectedPeriodTarget === opt.id ? 'selected' : ''}`}
                                      onClick={() => setSelectedPeriodTarget(opt.id)}
                                    >
                                      <span className="opt-label">{opt.label}</span>
                                      <span className="opt-era">{opt.era}</span>
                                    </button>
                                  ))}
                                </div>
                                <div className="editor-modal-actions">
                                  <button
                                    type="button"
                                    className="btn-cancel-edit"
                                    onClick={() => setEditingStoryId(null)}
                                  >
                                    İptal
                                  </button>
                                  <button
                                    type="button"
                                    className="btn-save-edit"
                                    onClick={() => handleCorrectPeriod(story.id, selectedPeriodTarget)}
                                  >
                                    <Check size={14} /> Kaydet
                                  </button>
                                </div>
                              </div>
                            )}

                            {/* Summary */}
                            <p className="story-narrative-summary">
                              {story.ai_summary || story.excerpt}
                            </p>

                            {/* Card Footer Actions */}
                            <div className="story-action-strip">
                              <span className="audio-duration-pill">
                                <Volume2 size={13} />
                                <span>{Math.round((story.duration_ms || 30000) / 1000)}s ses kaydı</span>
                              </span>

                              <button 
                                className="story-open-link-btn"
                                onClick={() => handleOpenStory(story.id)}
                              >
                                <span>Dinle & İncele</span>
                                <ChevronRight size={14} />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  /* Gap Bridge Invitation Card */
                  <div className="chapter-gap-invitation-box">
                    <div className="gap-icon-badge">
                      <HelpCircle size={24} />
                    </div>

                    <div className="gap-invitation-body">
                      <div className="gap-eyebrow">ANLATILMAMIŞ DÖNEM</div>
                      <h3 className="gap-invitation-title">{periodTitle} Hatıralarını Keşfedin</h3>
                      <p className="gap-invitation-text">
                        Bu döneme ait henüz bir ses kaydı bulunmuyor. Sabah kahvesinde sorulacak bir soruyla bu dönemin hatıralarını arşive kazandırabilirsiniz.
                      </p>

                      <div className="gap-action-buttons-row">
                        <button
                          type="button"
                          className="btn-ask-grandma-primary"
                          onClick={() => onOpenAskModal && onOpenAskModal(periodObj.period, '')}
                        >
                          <MessageSquarePlus size={15} />
                          <span>Bu Dönem Hakkında Soru Sor</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </main>
    </div>
  );
}
