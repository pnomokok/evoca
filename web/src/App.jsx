import React from 'react';
import { AppProvider } from './context/AppContext';
import { useApp } from './context/useApp';
import DemoHeader from './components/DemoHeader';
import DeviceScreen from './components/DeviceScreen';
import FamilyPanel from './components/panel/FamilyPanel';
import LandingPage from './components/LandingPage';
import { Info, AlertCircle } from 'lucide-react';

function MainContent() {
  const { activeTab, setActiveTab, toast } = useApp();

  return (
    <div className="app-container">
      <DemoHeader />

      <main className="view-viewport" style={{ padding: activeTab === 'landing' ? 0 : undefined }}>
        {activeTab === 'landing' && (
          <LandingPage onOpenDemo={(tab) => setActiveTab(tab || 'panel')} />
        )}
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

export default function App() {
  return (
    <AppProvider>
      <MainContent />
    </AppProvider>
  );
}
