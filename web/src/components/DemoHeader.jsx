import React from 'react';
import { useApp } from '../context/AppContext';
import { BookOpen, Tv, Users, User, Database, Server } from 'lucide-react';

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
    { id: 'person_fatma', name: 'Fatma Yilmaz', role: 'center' },
    { id: 'person_ayse', name: 'Ayşe Yilmaz', role: 'admin' },
    { id: 'person_elif', name: 'Elif Yilmaz', role: 'member' },
    { id: 'person_can', name: 'Can Yilmaz', role: 'member' }
  ];

  return (
    <header className="archival-topbar">
      <div className="topbar-inner">
        {/* Brand & Identity */}
        <div className="topbar-brand">
          <span className="brand-monogram">E</span>
          <div className="brand-text-group">
            <span className="brand-name">Evoca</span>
            <span className="brand-tagline">A Living Family Archive</span>
          </div>
        </div>

        {/* Quiet Screen Switcher */}
        <nav className="topbar-nav" aria-label="Experience switcher">
          <button
            className={`topbar-nav-link ${activeTab === 'panel' ? 'active' : ''}`}
            onClick={() => setActiveTab('panel')}
          >
            <BookOpen size={15} />
            <span>Family Archive</span>
          </button>
          <button
            className={`topbar-nav-link ${activeTab === 'device' ? 'active' : ''}`}
            onClick={() => setActiveTab('device')}
          >
            <Tv size={15} />
            <span>Living Room Device</span>
          </button>
          <button
            className={`topbar-nav-link ${activeTab === 'gathering' ? 'active' : ''}`}
            onClick={() => setActiveTab('gathering')}
          >
            <Users size={15} />
            <span>Gathering Mode</span>
          </button>
        </nav>

        {/* Quiet Viewer and API Mode Controls */}
        <div className="topbar-controls">
          <div className="viewer-picker">
            <User size={13} className="viewer-icon" />
            <select
              className="archival-select"
              value={currentViewerId}
              onChange={(e) => switchViewer(e.target.value)}
              title="Change family viewer perspective (X-Person-Id)"
            >
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.relation_to_center || m.role})
                </option>
              ))}
            </select>
          </div>

          <button
            className={`api-mode-chip ${useMock ? 'mock' : 'live'}`}
            onClick={() => toggleMock(!useMock)}
            title="Toggle between mock JSON samples and live FastAPI backend"
          >
            {useMock ? <Database size={12} /> : <Server size={12} />}
            <span>{useMock ? 'Demo Samples' : 'Live Backend'}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
