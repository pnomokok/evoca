import React, { useState } from 'react';
import { useApp } from '../../context/AppContext';
import FeedView from './FeedView';
import LifelineView from './LifelineView';
import StoryView from './StoryView';
import AskQuestionModal from './AskQuestionModal';
import RecordMemoryModal from './RecordMemoryModal';
import { Newspaper, Hourglass, BookOpen, MessageSquarePlus, Mic, Wifi, Battery, Signal } from 'lucide-react';

export default function FamilyPanel() {
  const { panelSubTab, setPanelSubTab, circleData, currentViewerId } = useApp();
  const [askModalOpen, setAskModalOpen] = useState(false);
  const [recordModalOpen, setRecordModalOpen] = useState(false);
  const [targetPeriod, setTargetPeriod] = useState(null);

  const me = circleData?.me || { name: 'Elif Yilmaz', role: 'member', relation_to_center: 'granddaughter' };
  const circle = circleData?.circle || { name: 'The Yilmaz Family' };

  const handleOpenAskModal = (period = null) => {
    setTargetPeriod(period);
    setAskModalOpen(true);
  };

  return (
    <div className="phone-viewport-container">
      {/* Mobile Top Status Bar & Notch */}
      <div className="phone-notch-bar">
        <span>9:41</span>
        <div className="phone-notch-pill" />
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Signal size={12} />
          <Wifi size={12} />
          <Battery size={14} />
        </div>
      </div>

      {/* Header */}
      <header className="panel-header">
        <div className="circle-info-group">
          <span className="circle-name">{circle.name}</span>
          <span className="circle-meta">
            <span>● Active Archive</span> · <span>Chat 10:00 AM</span>
          </span>
        </div>

        <div className="viewer-pill">
          <span className="viewer-avatar">
            {currentViewerId === 'person_fatma' ? '👵' : currentViewerId === 'person_ayse' ? '👩' : '👧'}
          </span>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span className="viewer-role-name">{me.name.split(' ')[0]}</span>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
              {me.relation_to_center ? me.relation_to_center : me.role}
            </span>
          </div>
        </div>
      </header>

      {/* Main Scrollable View */}
      <main className="panel-body">
        {panelSubTab === 'feed' && <FeedView />}
        {panelSubTab === 'lifeline' && <LifelineView onOpenAskModal={handleOpenAskModal} />}
        {panelSubTab === 'story' && <StoryView />}
      </main>

      {/* Floating Action Buttons */}
      <div className="panel-fab-row">
        <button
          className="fab-btn"
          onClick={() => handleOpenAskModal(null)}
          title="Ask Grandma a question"
        >
          <MessageSquarePlus size={22} />
        </button>
        <button
          className="fab-btn record-fab"
          onClick={() => setRecordModalOpen(true)}
          title="Record your memory"
        >
          <Mic size={22} />
        </button>
      </div>

      {/* Bottom Navigation */}
      <nav className="panel-bottom-nav">
        <button
          className={`nav-tab-btn ${panelSubTab === 'feed' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('feed')}
        >
          <Newspaper size={18} />
          <span>Feed</span>
        </button>
        <button
          className={`nav-tab-btn ${panelSubTab === 'lifeline' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('lifeline')}
        >
          <Hourglass size={18} />
          <span>Lifeline</span>
        </button>
        <button
          className={`nav-tab-btn ${panelSubTab === 'story' ? 'active' : ''}`}
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
