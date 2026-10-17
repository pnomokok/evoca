import React from 'react';
import { useApp } from '../context/useApp';
import { BookOpen, Tv, User, Database, Server } from 'lucide-react';

export default function DemoHeader() {
  const {
    activeTab,
    setActiveTab,
    currentViewerId,
    switchViewer,
    useMock,
    toggleMock,
    circleData,
    peopleList
  } = useApp();

  // Combine circle members or people list
  const members = circleData?.members || peopleList?.map(p => ({
    id: p.id,
    name: p.name,
    role: p.circles?.[0]?.role || 'member',
    relation_to_center: p.circles?.[0]?.role === 'center' ? 'center' : null
  })) || [];

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
        </nav>

        {/* Quiet Viewer and API Mode Controls */}
        <div className="topbar-controls">
          <div className="viewer-picker">
            <User size={13} className="viewer-icon" />
            <select
              className="archival-select"
              value={currentViewerId || ''}
              onChange={(e) => switchViewer(e.target.value)}
              title="See the archive as this family member"
              aria-label="Viewing as"
            >
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.relation_to_center || m.role})
                </option>
              ))}
            </select>
          </div>

          {/* Mock samples are a development aid; production always uses the live backend */}
          {import.meta.env.DEV && (
            <button
              className={`api-mode-chip ${useMock ? 'mock' : 'live'}`}
              onClick={() => toggleMock(!useMock)}
              title="Development only: switch between sample data and the live backend"
            >
              {useMock ? <Database size={12} /> : <Server size={12} />}
              <span>{useMock ? 'Sample data' : 'Live data'}</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
