import React, { useState } from 'react';
import { useApp } from '../../context/AppContext';
import FeedView from './FeedView';
import LifelineView from './LifelineView';
import StoryView from './StoryView';
import AskQuestionModal from './AskQuestionModal';
import RecordMemoryModal from './RecordMemoryModal';
import { Newspaper, Hourglass, BookOpen, MessageSquarePlus, Mic, Sparkles, Clock, Users } from 'lucide-react';

export default function FamilyPanel() {
  const { panelSubTab, setPanelSubTab, circleData, currentViewerId } = useApp();
  const [askModalOpen, setAskModalOpen] = useState(false);
  const [recordModalOpen, setRecordModalOpen] = useState(false);
  const [targetPeriod, setTargetPeriod] = useState(null);

  const me = circleData?.me || { name: 'Elif Yilmaz', role: 'member', relation_to_center: 'granddaughter' };
  const circle = circleData?.circle || { name: 'The Yilmaz Family', chat_time: '10:00' };

  const handleOpenAskModal = (period = null) => {
    setTargetPeriod(period);
    setAskModalOpen(true);
  };

  return (
    <div className="family-panel-container">
      {/* Responsive Web & Mobile Header */}
      <header className="panel-web-header">
        <div className="header-left-brand">
          <div className="circle-identity">
            <h1 className="circle-title-text">{circle.name}</h1>
            <div className="circle-status-row">
              <span className="live-status-dot" />
              <span className="status-label">Active Family Archive</span>
              <span className="bullet-sep">·</span>
              <span className="chat-time-tag">
                <Clock size={12} style={{ display: 'inline', marginRight: '4px' }} />
                Daily Chat {circle.chat_time || '10:00 AM'}
              </span>
            </div>
          </div>
        </div>

        {/* Desktop Web Sub-Navigation */}
        <nav className="panel-web-nav">
          <button
            className={`web-nav-btn ${panelSubTab === 'feed' ? 'active' : ''}`}
            onClick={() => setPanelSubTab('feed')}
          >
            <Newspaper size={17} />
            <span>Feed</span>
          </button>
          <button
            className={`web-nav-btn ${panelSubTab === 'lifeline' ? 'active' : ''}`}
            onClick={() => setPanelSubTab('lifeline')}
          >
            <Hourglass size={17} />
            <span>Lifeline</span>
          </button>
          <button
            className={`web-nav-btn ${panelSubTab === 'story' ? 'active' : ''}`}
            onClick={() => setPanelSubTab('story')}
          >
            <BookOpen size={17} />
            <span>Story Detail</span>
          </button>
        </nav>

        {/* Web Actions & Viewer Profile */}
        <div className="header-right-actions">
          <button
            className="panel-action-btn ask-btn"
            onClick={() => handleOpenAskModal(null)}
          >
            <MessageSquarePlus size={16} />
            <span>Ask Question</span>
          </button>

          <button
            className="panel-action-btn record-btn"
            onClick={() => setRecordModalOpen(true)}
          >
            <Mic size={16} />
            <span>Record Memory</span>
          </button>

          <div className="panel-viewer-badge">
            <span className="viewer-avatar-icon">
              {currentViewerId === 'person_fatma' ? '👵' : currentViewerId === 'person_ayse' ? '👩' : '👧'}
            </span>
            <div className="viewer-text-details">
              <span className="viewer-display-name">{me.name.split(' ')[0]}</span>
              <span className="viewer-relation-badge">
                {me.relation_to_center || me.role}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area (Naturally scrolling responsive canvas) */}
      <main className="panel-main-content">
        {panelSubTab === 'feed' && <FeedView onOpenAskModal={handleOpenAskModal} />}
        {panelSubTab === 'lifeline' && <LifelineView onOpenAskModal={handleOpenAskModal} />}
        {panelSubTab === 'story' && <StoryView />}
      </main>

      {/* Mobile Floating Action Buttons (Shown on small screens) */}
      <div className="mobile-fab-group">
        <button
          className="mobile-fab-btn ask-fab"
          onClick={() => handleOpenAskModal(null)}
          title="Ask Grandma a question"
        >
          <MessageSquarePlus size={22} />
        </button>
        <button
          className="mobile-fab-btn record-fab"
          onClick={() => setRecordModalOpen(true)}
          title="Record memory"
        >
          <Mic size={22} />
        </button>
      </div>

      {/* Mobile Bottom Navigation (Shown on mobile devices) */}
      <nav className="mobile-bottom-nav">
        <button
          className={`mobile-nav-item ${panelSubTab === 'feed' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('feed')}
        >
          <Newspaper size={18} />
          <span>Feed</span>
        </button>
        <button
          className={`mobile-nav-item ${panelSubTab === 'lifeline' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('lifeline')}
        >
          <Hourglass size={18} />
          <span>Lifeline</span>
        </button>
        <button
          className={`mobile-nav-item ${panelSubTab === 'story' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('story')}
        >
          <BookOpen size={18} />
          <span>Story</span>
        </button>
      </nav>

      {/* Modals */}
      <AskQuestionModal
        isOpen={askModalOpen}
        onClose={() => setAskModalOpen(false)}
        defaultPeriod={targetPeriod}
      />
      <RecordMemoryModal
        isOpen={recordModalOpen}
        onClose={() => setRecordModalOpen(false)}
      />
    </div>
  );
}
