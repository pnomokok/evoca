import React, { useCallback, useEffect, useState } from 'react';
import { AppProvider } from './context/AppContext';
import { useApp } from './context/useApp';
import { apiClient } from './api/client';
import { JOURNAL } from './utils/routes';
import DemoStrip from './components/DemoStrip';
import ArchiveHeader from './components/ArchiveHeader';
import DeviceScreen from './components/DeviceScreen';
import FamilyPanel from './components/panel/FamilyPanel';
import LandingPage from './components/LandingPage';
import JoinPage from './components/JoinPage';
import CreateFamilyWizard from './components/CreateFamilyWizard';
import StageView from './components/StageView';
import DemoEntryModal from './components/DemoEntryModal';
import PersonPicker from './components/PersonPicker';
import AnswerNotice from './components/panel/AnswerNotice';
import { useNewAnswers } from './components/panel/useNewAnswers';
import { focusLater } from './utils/focusLater';
import { usePaneTourTarget } from './utils/tour';
import { Info, AlertCircle, BookOpen } from 'lucide-react';
import './styles/navigation.css';

// A stage pane marks its document so the stage's styles can make the page fit the frame.
if (apiClient.embed) document.documentElement.dataset.embed = apiClient.embed.kind;

function Toast() {
  const { toast } = useApp();
  if (!toast) return null;
  return (
    <div className="toast-popup" role="status">
      {toast.type === 'error' ? (
        <AlertCircle size={18} color="#ef4444" />
      ) : (
        <Info size={18} color="var(--accent-gold)" />
      )}
      <span>{toast.message}</span>
    </div>
  );
}

// Opens one of the viewer's answered questions in My questions.
function useOpenAnswer() {
  const { navigate, reloadAll } = useApp();
  return useCallback((questionId) => {
    navigate({ tab: 'panel', subTab: 'questions' });
    reloadAll();   // the list may not know about the answer yet
    focusLater(`question-${questionId}`);
  }, [navigate, reloadAll]);
}

// In the archive (outside the stage): a toast when an answer to one of my questions appears.
function AnswerToast() {
  const { circleData, currentViewerId, centerPersonId, dataVersion } = useApp();
  const openAnswer = useOpenAnswer();
  const me = circleData?.me?.id === currentViewerId ? circleData.me : null;
  const { notice, dismiss } = useNewAnswers({
    circleId: circleData?.circle?.id, personId: currentViewerId,
    enabled: Boolean(me) && me.role !== 'center', reloadKey: dataVersion
  });
  const centerFirst = circleData?.members?.find(m => m.id === centerPersonId)?.name?.split(' ')[0] || '';
  return <AnswerNotice notice={notice} centerFirst={centerFirst} onOpen={openAnswer} onDismiss={dismiss} />;
}

// The landing page; its demo buttons open the demo modal, which leads to the stage or the person picker.
function Landing() {
  const { isSignedIn, openCreateFamily, openHome, navigate, startTour } = useApp();
  const [demoStep, setDemoStep] = useState(null); // null | 'entry' | 'picker'

  return (
    <div className="app-container">
      <main className="view-viewport" style={{ padding: 0 }}>
        <LandingPage
          isSignedIn={isSignedIn}
          onTryDemo={() => setDemoStep('entry')}
          onCreateFamily={openCreateFamily}
          onOpenFamily={openHome}
        />
      </main>
      <Toast />
      {demoStep === 'entry' && (
        <DemoEntryModal
          onClose={() => setDemoStep(null)}
          onWatchLoop={() => { setDemoStep(null); navigate({ tab: 'stage' }); startTour(); }}
          onExplore={() => setDemoStep('picker')}
        />
      )}
      {demoStep === 'picker' && <PersonPicker onClose={() => setDemoStep(null)} />}
    </div>
  );
}

// Every other page: the demo strip on top (demo only), then the stage, the archive or the device.
function MainContent() {
  const { activeTab, isSignedIn, navigate } = useApp();

  if (activeTab === 'landing') return <Landing />;

  return (
    <div className="app-container">
      {!isSignedIn && <DemoStrip />}

      {activeTab === 'stage' && <StageView />}

      {activeTab === 'panel' && <>
        <ArchiveHeader />
        <main className="view-viewport">
          <FamilyPanel />
        </main>
        <AnswerToast />
      </>}

      {/* The device is an object, not a web page: no product header. Signed in (only the center gets
          here), a quiet way back to her family's archive sits outside the device. */}
      {activeTab === 'device' && (
        <main className="view-viewport device-viewport">
          <DeviceScreen />
          {isSignedIn && (
            <button type="button" className="device-away-link" onClick={() => navigate(JOURNAL)}>
              <BookOpen size={14} />
              <span>Family archive</span>
            </button>
          )}
        </main>
      )}

      <Toast />
    </div>
  );
}

// One pane of the stage: the device as the center person, or the family panel on a phone.
function EmbedContent() {
  const { activeTab } = useApp();
  const openAnswer = useOpenAnswer();
  // The guided tour on the stage says what to show; the pane finds it and sends its box.
  usePaneTourTarget();
  // The stage's phone banner asks the panel to open an answer (StageView); same origin only.
  useEffect(() => {
    if (activeTab === 'device') return undefined;
    const onMessage = (e) => {
      if (e.origin === window.location.origin && e.data?.type === 'evoca-open-answer' && e.data.questionId) {
        openAnswer(e.data.questionId);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [activeTab, openAnswer]);
  if (activeTab === 'device') {
    return (
      <div className="app-container embed-device-view">
        <DeviceScreen />
        <Toast />
      </div>
    );
  }
  return (
    <div className="app-container">
      <ArchiveHeader />
      <FamilyPanel />
      <Toast />
    </div>
  );
}

function joinTokenFromPath() {
  const match = /^\/join\/([^/]+)\/?$/.exec(window.location.pathname);
  return match ? decodeURIComponent(match[1]) : null;
}

export default function App() {
  if (apiClient.embed) {
    return (
      <AppProvider initialTab={apiClient.embed.kind} initialPanelSubTab="questions">
        <EmbedContent />
      </AppProvider>
    );
  }
  return <FullApp />;
}

function FullApp() {
  const [joinToken, setJoinToken] = useState(joinTokenFromPath);
  // A new key remounts the whole app with fresh state whenever who is calling changes
  // (joined, created a family, left, back to the demo), so nothing from the old identity lingers.
  // The page comes from the URL: 'home' opens the family's journal (the device for the center), 'landing' /.
  const [start, setStart] = useState(() => ({ key: 0, home: false, toast: null }));
  const [creating, setCreating] = useState(false);

  const restartApp = useCallback((tab, toast = null) => {
    const path = tab === 'home' ? '/archive/journal' : '/';
    if (window.location.pathname !== path) window.history.pushState(null, '', path);
    window.scrollTo(0, 0);   // a new family's journal opens at its top (Getting started), not mid-page
    setStart(s => ({ key: s.key + 1, home: tab === 'home', toast }));
  }, []);
  const openCreateFamily = useCallback(() => setCreating(true), []);

  if (joinToken) {
    return (
      <JoinPage
        token={joinToken}
        onDone={(joined) => {
          setJoinToken(null);
          restartApp(joined ? 'home' : 'landing');
        }}
      />
    );
  }

  return (
    <>
      <AppProvider
        key={start.key}
        startAtHome={start.home}
        initialToast={start.toast}
        restartApp={restartApp}
        openCreateFamily={openCreateFamily}
      >
        <MainContent />
      </AppProvider>
      {creating && (
        <CreateFamilyWizard onClose={() => setCreating(false)} onCreated={() => restartApp('home')} />
      )}
    </>
  );
}
