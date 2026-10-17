import React, { useState } from 'react';
import { useApp } from '../../context/useApp';
import FamilyDashboard from './FamilyDashboard';
import LifelineView from './LifelineView';
import StoryView from './StoryView';
import AskQuestionModal from './AskQuestionModal';
import RecordMemoryModal from './RecordMemoryModal';
import FamilySettings from './FamilySettings';
import { BookOpen, Hourglass, MessageSquarePlus, Mic, Settings, Sparkles, Tv } from 'lucide-react';

export default function FamilyPanel() {
  const { panelSubTab, setPanelSubTab, circleData, setActiveTab, currentViewerId } = useApp();
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

  // The center person talks to Evoca on the device; the panel never asks or records for her.
  // Only once the circle data belongs to the current viewer (a switch updates the id first).
  const role = circleData?.me?.id === currentViewerId ? circleData?.me?.role : null;
  const isCenter = role === 'center';
  const isAdmin = role === 'admin';
  const centerFirst = circleData?.me?.name?.split(' ')[0] || '';
  const askHandler = isCenter ? null : handleOpenAskModal;
  const recordHandler = isCenter ? null : handleOpenRecordModal;
  // Family settings is for the circle's admin only; anyone else lands on the journal.
  const subTab = panelSubTab === 'settings' && !isAdmin ? 'feed' : panelSubTab;

  return (
    <div className="family-panel-canvas">
      {/* Sub-Header Navigation */}
      <nav className="panel-editorial-subnav" aria-label="Archive navigation">
        <div className="subnav-left">
          <button
            className={`subnav-pill ${subTab === 'feed' ? 'active' : ''}`}
            onClick={() => setPanelSubTab('feed')}
          >
            <BookOpen size={16} />
            <span>Family Journal</span>
          </button>

          <button
            className={`subnav-pill ${subTab === 'lifeline' ? 'active' : ''}`}
            onClick={() => setPanelSubTab('lifeline')}
          >
            <Hourglass size={16} />
            <span>Life Chapters</span>
          </button>

          <button
            className={`subnav-pill ${subTab === 'story' ? 'active' : ''}`}
            onClick={() => setPanelSubTab('story')}
          >
            <Sparkles size={16} />
            <span>Story Detail</span>
          </button>

          {isAdmin && (
            <button
              className={`subnav-pill ${subTab === 'settings' ? 'active' : ''}`}
              onClick={() => setPanelSubTab('settings')}
            >
              <Settings size={16} />
              <span>Family settings</span>
            </button>
          )}
        </div>

        {!isCenter && (
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
        )}
      </nav>

      {isCenter && (
        <div className="sensitive-guard-alert center-device-note" role="note" style={{ margin: '12px auto', maxWidth: '960px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
          <p style={{ margin: 0 }}>{centerFirst || 'The storyteller'} talks to Evoca on the Living Room Device.</p>
          <button type="button" className="editorial-btn secondary" onClick={() => setActiveTab('device')}>
            <Tv size={15} />
            <span>Open the Living Room Device</span>
          </button>
        </div>
      )}

      {/* Main Experience View */}
      <div className="panel-experience-content">
        {subTab === 'feed' && (
          <FamilyDashboard
            onOpenAskModal={askHandler}
            onOpenRecordModal={recordHandler}
          />
        )}
        {subTab === 'lifeline' && (
          <LifelineView onOpenAskModal={askHandler} />
        )}
        {subTab === 'story' && (
          <StoryView />
        )}
        {subTab === 'settings' && isAdmin && (
          <FamilySettings />
        )}
      </div>

      {/* Mobile Bottom Navigation Bar */}
      <nav className="mobile-archival-nav" aria-label="Mobile navigation">
        <button
          className={`mobile-tab-btn ${subTab === 'feed' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('feed')}
        >
          <BookOpen size={18} />
          <span>Journal</span>
        </button>

        <button
          className={`mobile-tab-btn ${subTab === 'lifeline' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('lifeline')}
        >
          <Hourglass size={18} />
          <span>Chapters</span>
        </button>

        <button
          className={`mobile-tab-btn ${subTab === 'story' ? 'active' : ''}`}
          onClick={() => setPanelSubTab('story')}
        >
          <Sparkles size={18} />
          <span>Story</span>
        </button>

        {!isCenter && (
          <button
            className="mobile-tab-btn action-ask"
            onClick={() => handleOpenAskModal(null, '')}
          >
            <MessageSquarePlus size={18} />
            <span>Ask</span>
          </button>
        )}
      </nav>

      {/* Modals */}
      {/* Mounted only while open, so each opening starts from fresh state */}
      {askModalOpen && !isCenter && (
        <AskQuestionModal
          onClose={() => setAskModalOpen(false)}
          defaultPeriod={targetPeriod}
          initialPrompt={initialPrompt}
        />
      )}
      {recordModalOpen && !isCenter && (
        <RecordMemoryModal onClose={() => setRecordModalOpen(false)} />
      )}
    </div>
  );
}
