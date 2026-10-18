import React, { useState } from 'react';
import { useApp } from '../../context/useApp';
import FamilyDashboard from './FamilyDashboard';
import LifelineView from './LifelineView';
import StoryView from './StoryView';
import AskQuestionModal from './AskQuestionModal';
import RecordMemoryModal from './RecordMemoryModal';
import FamilySettings from './FamilySettings';
import MyQuestions from './MyQuestions';
import { BookOpen, Hourglass, ListChecks, MessageSquarePlus, Tv } from 'lucide-react';

// The archive's pages under its header (ArchiveHeader): the page comes from the URL (AppContext).
// Below 768 px the bottom bar holds Journal, Chapters, Questions and Ask.
export default function FamilyPanel() {
  const { panelSubTab, storyBack, navigate, circleData, currentViewerId, isSignedIn, askDialog, openAsk, closeAsk, recordOpen, closeRecord } = useApp();
  // Bumped when the ask dialog closes, so My questions shows a question just asked.
  const [askCount, setAskCount] = useState(0);

  // The center person talks to Evoca on the device; the panel never asks or records for her.
  // Only once the circle data belongs to the current viewer (a switch updates the id first).
  const role = circleData?.me?.id === currentViewerId ? circleData?.me?.role : null;
  const isCenter = role === 'center';
  const isAdmin = role === 'admin';
  const centerFirst = circleData?.me?.name?.split(' ')[0] || '';
  const askHandler = isCenter ? null : openAsk;
  // Family settings is for the circle's admin only, My questions for those who can ask;
  // anyone else sees the journal (AppContext also puts the journal in the address bar).
  const subTab = (panelSubTab === 'settings' && !isAdmin) || (panelSubTab === 'questions' && isCenter) ? 'feed' : panelSubTab;
  const current = subTab === 'story' ? storyBack : subTab;
  const goTo = (key) => navigate({ tab: 'panel', subTab: key });

  return (
    <div className="family-panel-canvas">
      {/* Signed in only: in the demo the storyteller's pick opens the device instead of the archive. */}
      {isCenter && isSignedIn && (
        <div className="sensitive-guard-alert center-device-note" role="note" style={{ margin: '12px auto', maxWidth: '960px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
          <p style={{ margin: 0 }}>{centerFirst || 'The storyteller'} talks to Evoca on the Living Room Device.</p>
          <button type="button" className="editorial-btn secondary" onClick={() => navigate({ tab: 'device' })}>
            <Tv size={15} />
            <span>Open the Living Room Device</span>
          </button>
        </div>
      )}

      {/* Main Experience View */}
      <div className="panel-experience-content">
        {subTab === 'feed' && (
          <FamilyDashboard onOpenAskModal={askHandler} />
        )}
        {subTab === 'lifeline' && (
          <LifelineView onOpenAskModal={askHandler} />
        )}
        {subTab === 'story' && (
          <StoryView />
        )}
        {subTab === 'questions' && !isCenter && (
          <MyQuestions reloadKey={askCount} />
        )}
        {subTab === 'settings' && isAdmin && (
          <FamilySettings />
        )}
      </div>

      {/* Mobile Bottom Navigation Bar */}
      <nav className="mobile-archival-nav" aria-label="Family archive">
        <button
          className={`mobile-tab-btn ${current === 'feed' ? 'active' : ''}`}
          onClick={() => goTo('feed')}
          aria-current={subTab === 'feed' ? 'page' : undefined}
        >
          <BookOpen size={18} />
          <span>Journal</span>
        </button>

        <button
          className={`mobile-tab-btn ${current === 'lifeline' ? 'active' : ''}`}
          onClick={() => goTo('lifeline')}
          aria-current={subTab === 'lifeline' ? 'page' : undefined}
        >
          <Hourglass size={18} />
          <span>Chapters</span>
        </button>

        {!isCenter && (
          <button
            className={`mobile-tab-btn ${current === 'questions' ? 'active' : ''}`}
            onClick={() => goTo('questions')}
            aria-current={subTab === 'questions' ? 'page' : undefined}
          >
            <ListChecks size={18} />
            <span>Questions</span>
          </button>
        )}

        {!isCenter && (
          <button
            className="mobile-tab-btn action-ask"
            onClick={() => openAsk()}
          >
            <MessageSquarePlus size={18} />
            <span>Ask</span>
          </button>
        )}
      </nav>

      {/* Modals */}
      {/* Mounted only while open, so each opening starts from fresh state */}
      {askDialog && !isCenter && (
        <AskQuestionModal
          onClose={() => { closeAsk(); setAskCount(n => n + 1); }}
          defaultPeriod={askDialog.period}
          initialPrompt={askDialog.prompt}
        />
      )}
      {recordOpen && !isCenter && (
        <RecordMemoryModal onClose={closeRecord} />
      )}
    </div>
  );
}
