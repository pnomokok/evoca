import React from 'react';
import { useApp } from '../context/useApp';
import DemoControls from './DemoControls';
import { Sparkles, BookOpen, Tv, User, LogOut, Users } from 'lucide-react';

export default function DemoHeader() {
  const {
    activeTab,
    setActiveTab,
    currentViewerId,
    switchViewer,
    circleData,
    peopleList,
    centerPersonId,
    isSignedIn,
    leaveFamily,
    openCreateFamily
  } = useApp();

  // Combine circle members or people list
  const members = circleData?.members || peopleList?.map(p => ({
    id: p.id,
    name: p.name,
    role: p.circles?.[0]?.role || 'member',
    relation_to_center: p.circles?.[0]?.role === 'center' ? 'center' : null
  })) || [];

  // Which family this is; signed in, the session's person (no picker: the session fixes who you are).
  const familyName = circleData?.circle?.name;
  const me = circleData?.me?.id === currentViewerId ? circleData.me : null;
  // The device acts as the center: in a signed-in family only the center's own session can use it.
  const showDevice = !isSignedIn || (currentViewerId && currentViewerId === centerPersonId);

  return (
    <header className="archival-topbar">
      <div className="topbar-inner">
        {/* Brand & Identity */}
        <div 
          className="topbar-brand"
          onClick={() => setActiveTab('landing')}
          style={{ cursor: 'pointer' }}
          title="Go to Evoca Overview"
        >
          <span className="brand-monogram">E</span>
          <div className="brand-text-group">
            <span className="brand-name">Evoca</span>
            <span className="brand-tagline" data-testid="family-name">
              {familyName ? `${familyName}${isSignedIn ? '' : ' · demo'}` : 'A Living Family Archive'}
            </span>
          </div>
        </div>

        {/* Quiet Screen Switcher */}
        <nav className="topbar-nav" aria-label="Experience switcher">
          <button
            className={`topbar-nav-link ${activeTab === 'landing' ? 'active' : ''}`}
            onClick={() => setActiveTab('landing')}
          >
            <Sparkles size={14} />
            <span>Overview</span>
          </button>
          <button
            className={`topbar-nav-link ${activeTab === 'panel' ? 'active' : ''}`}
            onClick={() => setActiveTab('panel')}
          >
            <BookOpen size={14} />
            <span>Family Archive</span>
          </button>
          {showDevice && (
            <button
              className={`topbar-nav-link ${activeTab === 'device' ? 'active' : ''}`}
              onClick={() => setActiveTab('device')}
            >
              <Tv size={14} />
              <span>Living Room Device</span>
            </button>
          )}
        </nav>

        {/* Who is viewing (demo picker, or the signed-in person with Leave) and the demo clock */}
        <div className="topbar-controls">
          {isSignedIn ? <>
            <div className="viewer-picker" title={familyName ? `Signed in to ${familyName}` : undefined}>
              <User size={13} className="viewer-icon" />
              <span className="archival-select" data-testid="signed-in-as">
                {me ? `${me.name} (${me.relation_to_center || me.role})` : '...'}
              </span>
            </div>
            <button type="button" className="topbar-text-btn" onClick={leaveFamily} title="Sign out of this family on this device">
              <LogOut size={13} />
              <span>Leave</span>
            </button>
          </> : <>
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
            <button type="button" className="topbar-text-btn" onClick={openCreateFamily}>
              <Users size={13} />
              <span>Create your family</span>
            </button>
          </>}

          <DemoControls />
        </div>
      </div>
    </header>
  );
}
