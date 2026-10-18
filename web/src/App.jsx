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
import { Info, AlertCircle, Users } from 'lucide-react';

function MainContent() {
  const { activeTab, enterDemo, openCreateFamily, isSignedIn, toast } = useApp();

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
          {/* The demo entry: it forgets any stored sign-in and opens the demo family. */}
          <LandingPage onOpenDemo={(tab) => enterDemo(tab || 'panel')} />
        </div>}
        {activeTab === 'panel' && <FamilyPanel />}
        {activeTab === 'device' && <DeviceScreen />}
      </main>

      {/* Global Toast */}
      {toast && (
        <div className="toast-popup" role="status">
          {toast.type === 'error' ? (
            <AlertCircle size={18} color="#ef4444" />
          ) : (
            <Info size={18} color="var(--accent-gold)" />
          )}
          <span>{toast.message}</span>
        </div>
      )}
    </div>
  );
}

function joinTokenFromPath() {
  const match = /^\/join\/([^/]+)\/?$/.exec(window.location.pathname);
  return match ? decodeURIComponent(match[1]) : null;
}

export default function App() {
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
