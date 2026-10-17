import React, { useState } from 'react';
import { useApp } from '../../context/useApp';
import FamilyDashboard from './FamilyDashboard';
import LifelineView from './LifelineView';
import StoryView from './StoryView';
import AskQuestionModal from './AskQuestionModal';
import RecordMemoryModal from './RecordMemoryModal';
import { BookOpen, Hourglass, MessageSquarePlus, Mic, Sparkles } from 'lucide-react';

export default function FamilyPanel() {
  const { panelSubTab, setPanelSubTab } = useApp();
  const [askModalOpen, setAskModalOpen] = useState(false);
  const [recordModalOpen, setRecordModalOpen] = useState(false);
  const [targetPeriod, setTargetPeriod] = useState(null);
  const [initialPrompt, setInitialPrompt] = useState('');

  const handleOpenAskModal = (period = null, prompt = '') => {
    setTargetPeriod(period);
    setInitialPrompt(prompt);
    setAskModalOpen(true);
  };

  const handleOpenRecordModal = () => {
    setRecordModalOpen(true);
  };

  return (
    <div className="family-panel-canvas">
      {/* Sub-Header Navigation */}
      <nav className="panel-editorial-subnav" aria-label="Archive navigation">
        <div className="subnav-left">
          <button
            className={`subnav-pill ${panelSubTab === 'feed' ? 'active' : ''}`}
            onClick={() => setPanelSubTab('feed')}
          >
            <BookOpen size={16} />
            <span>Family Journal</span>
          </button>

          <button
            className={`subnav-pill ${panelSubTab === 'lifeline' ? 'active' : ''}`}
            onClick={() => setPanelSubTab('lifeline')}
          >
            <Hourglass size={16} />
            <span>Life Chapters</span>
          </button>

          <button
            className={`subnav-pill ${panelSubTab === 'story' ? 'active' : ''}`}
            onClick={() => setPanelSubTab('story')}
          >
            <Sparkles size={16} />
            <span>Story Detail</span>
          </button>
        </div>

        <div className="subnav-right">
          <button
            className="editorial-action-btn question"
            onClick={() => handleOpenAskModal(null, '')}
          >
            <MessageSquarePlus size={15} />
            <span>Ask a Question</span>
          </button>

          <button
            className="editorial-action-btn record"
            onClick={handleOpenRecordModal}
          >
            <Mic size={15} />
            <span>Record Memory</span>
          </button>
        </div>
      </nav>

      {/* Main Experience View */}
      <div className="panel-experience-content">
        {panelSubTab === 'feed' && (
          <FamilyDashboard
            onOpenAskModal={handleOpenAskModal}
            onOpenRecordModal={handleOpenRecordModal}
          />
        )}
        {panelSubTab === 'lifeline' && (
          <LifelineView onOpenAskModal={handleOpenAskModal} />
        )}
        {panelSubTab === 'story' && (
          <StoryView />
        )}
      </div>

      {/* Mobile Bottom Navigation Bar */}
      <nav className="mobile-archival-nav" aria-label="Mobile navigation">
        <button
          className={`mobile-tab-btn ${panelSubTab === 'feed' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('feed')}
        >
          <BookOpen size={18} />
          <span>Journal</span>
        </button>

        <button
          className={`mobile-tab-btn ${panelSubTab === 'lifeline' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('lifeline')}
        >
          <Hourglass size={18} />
          <span>Chapters</span>
        </button>

        <button
          className={`mobile-tab-btn ${panelSubTab === 'story' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('story')}
        >
          <Sparkles size={18} />
          <span>Story</span>
        </button>

        <button
          className="mobile-tab-btn action-ask"
          onClick={() => handleOpenAskModal(null, '')}
        >
          <MessageSquarePlus size={18} />
          <span>Ask</span>
        </button>
      </nav>

      {/* Modals */}
      {/* Mounted only while open, so each opening starts from fresh state */}
      {askModalOpen && (
        <AskQuestionModal
          onClose={() => setAskModalOpen(false)}
          defaultPeriod={targetPeriod}
          initialPrompt={initialPrompt}
        />
      )}
      {recordModalOpen && (
        <RecordMemoryModal onClose={() => setRecordModalOpen(false)} />
      )}
    </div>
  );
}
