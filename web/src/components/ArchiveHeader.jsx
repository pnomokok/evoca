import React, { useCallback, useRef, useState } from 'react';
import { useApp } from '../context/useApp';
import { apiClient } from '../api/client';
import { JOURNAL, LANDING } from '../utils/routes';
import { useDismiss } from '../utils/useDismiss';
import Avatar from './Avatar';
import { BookOpen, Hourglass, ListChecks, LogOut, Menu, MessageSquarePlus, Mic, Settings } from 'lucide-react';

const TABS = [
  { key: 'feed', label: 'Journal', icon: BookOpen },
  { key: 'lifeline', label: 'Life chapters', icon: Hourglass },
  { key: 'questions', label: 'My questions', icon: ListChecks, canAsk: true },
  { key: 'settings', label: 'Family settings', icon: Settings, admin: true }
];

// The family archive's header, the same in the demo and signed in: brand and family name, the tabs,
// "Ask a question" and "Record memory", and when signed in the person's name and Leave.
// Below 768 px: brand, family name and a menu (Family settings, Leave); the tabs, "Ask a question"
// and "Record a memory" are in the bottom bar's "+" (FamilyPanel). In a stage pane: who is holding the phone, and the menu.
export default function ArchiveHeader() {
  const { panelSubTab, storyBack, navigate, circleData, currentViewerId, isSignedIn, leaveFamily, openAsk, openRecord } = useApp();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  useDismiss(menuOpen, menuRef, closeMenu);

  // Only once the circle data belongs to the current viewer (a switch updates the id first).
  const me = circleData?.me?.id === currentViewerId ? circleData.me : null;
  const canAsk = Boolean(me) && me.role !== 'center';
  const isAdmin = me?.role === 'admin';
  const familyName = circleData?.circle?.name;
  const embedded = Boolean(apiClient.embed);
  // A story is a sub-page of the page it was opened from.
  const current = panelSubTab === 'story' ? storyBack : panelSubTab;
  const tabs = TABS.filter(t => (!t.admin || isAdmin) && (!t.canAsk || canAsk));

  const menuItems = [
    isAdmin && { key: 'settings', label: 'Family settings', icon: Settings, run: () => navigate({ tab: 'panel', subTab: 'settings' }) },
    isSignedIn && !embedded && { key: 'leave', label: 'Leave', icon: LogOut, run: leaveFamily }
  ].filter(Boolean);

  return (
    <header className={`archival-topbar archive-header ${embedded ? 'embedded' : ''}`}>
      <div className="topbar-inner">
        {embedded ? (
          <div className="archive-identity">
            {me && <Avatar person={me} size={30} />}
            <span><strong>{me?.name?.split(' ')[0] || ''}</strong>{familyName ? ` · ${familyName}` : ''}</span>
          </div>
        ) : (
          <button
            type="button"
            className="topbar-brand"
            onClick={() => navigate(isSignedIn ? JOURNAL : LANDING)}
            title={isSignedIn ? 'Family journal' : 'Evoca'}
          >
            <span className="brand-monogram">E</span>
            <span className="brand-text-group">
              <span className="brand-name">Evoca</span>
              <span className="brand-tagline" data-testid="family-name">{familyName || 'A Living Family Archive'}</span>
            </span>
          </button>
        )}

        <nav className="archive-tabs" aria-label="Family archive">
          {tabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              className={`subnav-pill ${current === key ? 'active' : ''}`}
              onClick={() => navigate({ tab: 'panel', subTab: key })}
              aria-current={panelSubTab === key ? 'page' : undefined}
            >
              <Icon size={15} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="archive-actions">
          {canAsk && <>
            <button type="button" className="editorial-action-btn question" onClick={() => openAsk()}>
              <MessageSquarePlus size={15} />
              <span>Ask a question</span>
            </button>
            <button type="button" className="editorial-action-btn record" onClick={openRecord}>
              <Mic size={15} />
              <span>Record memory</span>
            </button>
          </>}
          {isSignedIn && <>
            <span className="archive-me" data-testid="signed-in-as">{me?.name || '...'}</span>
            <button type="button" className="topbar-text-btn" onClick={leaveFamily} title="Sign out of this family on this device">
              <LogOut size={13} />
              <span>Leave</span>
            </button>
          </>}
        </div>

        {menuItems.length > 0 && (
          <div className="archive-menu" ref={menuRef}>
            <button
              type="button"
              className="archive-menu-btn"
              onClick={() => setMenuOpen(open => !open)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label="Menu"
            >
              <Menu size={20} />
            </button>
            {menuOpen && (
              <div className="demo-menu" role="menu" aria-label="Family archive">
                {isSignedIn && me && <p className="archive-menu-me">{me.name}</p>}
                {menuItems.map(({ key, label, icon: Icon, run }) => (
                  <button key={key} type="button" role="menuitem" onClick={() => { setMenuOpen(false); run(); }}>
                    <Icon size={14} /> {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
