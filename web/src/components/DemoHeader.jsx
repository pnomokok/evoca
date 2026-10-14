import React from 'react';
import { useApp } from '../context/AppContext';
import { Tv, Smartphone, Users, UserCheck, Database, Server } from 'lucide-react';

export default function DemoHeader() {
  const {
    activeTab,
    setActiveTab,
    currentViewerId,
    switchViewer,
    useMock,
    toggleMock,
    circleData
  } = useApp();

  const members = circleData?.members || [
    { id: 'person_fatma', name: 'Fatma Yilmaz (Center / Elder)' },
    { id: 'person_ayse', name: 'Ayşe Yilmaz (Admin / Daughter)' },
    { id: 'person_elif', name: 'Elif Yilmaz (Member / Granddaughter)' },
    { id: 'person_can', name: 'Can Yilmaz (Member / Grandson)' }
  ];

  return (
    <header className="demo-bar">
      <div className="demo-bar-brand">
        <div className="brand-icon">E</div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="brand-title">Evoca</span>
            <span className="brand-tag">Alexa+ Demo</span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Voice-First Family Memory Archive
          </div>
        </div>
      </div>

      <nav className="demo-tabs">
        <button
          className={`demo-tab-btn ${activeTab === 'panel' ? 'active' : ''}`}
          onClick={() => setActiveTab('panel')}
        >
          <Smartphone size={16} />
          Family Panel (Mobile)
        </button>
        <button
          className={`demo-tab-btn ${activeTab === 'device' ? 'active' : ''}`}
          onClick={() => setActiveTab('device')}
        >
          <Tv size={16} />
          Device Screen (Echo Show)
        </button>
        <button
          className={`demo-tab-btn ${activeTab === 'gathering' ? 'active' : ''}`}
          onClick={() => setActiveTab('gathering')}
        >
          <Users size={16} />
          Gathering Screen
        </button>
      </nav>

      <div className="demo-controls">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <UserCheck size={14} color="var(--accent-gold)" />
          <select
            className="viewer-select"
            value={currentViewerId}
            onChange={(e) => switchViewer(e.target.value)}
            title="Switch authenticated viewer (X-Person-Id header)"
          >
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.role})
              </option>
            ))}
          </select>
        </div>

        <button
          className="mock-badge"
          onClick={() => toggleMock(!useMock)}
          title="Click to toggle between Mock API samples and Live FastAPI backend"
        >
          {useMock ? <Database size={13} /> : <Server size={13} />}
          {useMock ? "API: Mock Samples" : "API: Live Backend"}
        </button>
      </div>
    </header>
  );
}
