import React, { useCallback, useState } from 'react';
import { AppProvider } from './context/AppContext';
import { useApp } from './context/useApp';
import { apiClient } from './api/client';
import DemoHeader from './components/DemoHeader';
import DeviceScreen from './components/DeviceScreen';
import FamilyPanel from './components/panel/FamilyPanel';
import LandingPage from './components/LandingPage';
import JoinPage from './components/JoinPage';
import CreateFamilyWizard from './components/CreateFamilyWizard';
import StageView from './components/StageView';
import DemoEntryModal from './components/DemoEntryModal';
import Avatar from './components/Avatar';
import { Info, AlertCircle, Users } from 'lucide-react';

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

function MainContent() {
  const { activeTab, enterDemo, openCreateFamily, isSignedIn } = useApp();
  const [choosingDemo, setChoosingDemo] = useState(false);

  if (activeTab === 'stage') {
    return (
      <div className="app-container">
        <StageView />
        <Toast />
      </div>
    );
  }

  return (
    <div className="app-container">
      <DemoHeader />

      <main className="view-viewport" style={{ padding: activeTab === 'landing' ? 0 : undefined }}>
        {activeTab === 'landing' && <div className="landing-stack">
          {!isSignedIn && (
            <div className="own-family-band">
              <span>Ready to keep your own family's stories?</span>
              <button type="button" className="editorial-btn primary" onClick={openCreateFamily}>
                <Users size={15} />
                <span>Create your family</span>
              </button>
            </div>
          )}
          {/* The demo entry: watch the loop or pick a role; either forgets any stored sign-in. */}
          <LandingPage onOpenDemo={(tab) => (tab === 'device' ? enterDemo('device') : setChoosingDemo(true))} />
        </div>}
        {activeTab === 'panel' && <FamilyPanel />}
        {activeTab === 'device' && <DeviceScreen />}
      </main>

      <Toast />
      {choosingDemo && (
        <DemoEntryModal
          onClose={() => setChoosingDemo(false)}
          onWatchLoop={() => { setChoosingDemo(false); enterDemo('stage'); }}
          onPickRole={() => { setChoosingDemo(false); enterDemo('panel'); }}
        />
      )}
    </div>
  );
}

// One pane of the stage: the device as the center person, or the family panel on a phone.
function EmbedContent() {
  const { activeTab, circleData } = useApp();
  if (activeTab === 'device') {
    return (
      <div className="app-container embed-device-view">
        <DeviceScreen />
        <Toast />
      </div>
    );
  }
  const me = circleData?.me;
  return (
    <div className="app-container">
      <div className="embed-phone-head">
        {me && <Avatar person={me} size={30} />}
        <span><strong>{me?.name?.split(' ')[0] || ''}</strong>{circleData?.circle?.name ? ` · ${circleData.circle.name}` : ''}</span>
      </div>
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
  const [start, setStart] = useState(() => ({ key: 0, tab: apiClient.isSignedIn ? 'home' : 'landing', toast: null }));
  const [creating, setCreating] = useState(false);

  const restartApp = useCallback((tab, toast = null) => {
    setStart(s => ({ key: s.key + 1, tab, toast }));
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
        initialTab={start.tab}
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
