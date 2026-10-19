import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../context/useApp';
import { apiClient } from '../api/client';
import Modal from './Modal';
import { formatDemoClock, hoursToNextMorning } from '../utils/demoClock';
import { useDemoArchiving } from '../utils/useDemoArchiving';
import { AlertTriangle, ChevronDown, Clock } from 'lucide-react';

const CLOCK_REFRESH_MS = 60_000;

// The demo clock and its menu (GET /api/demo/clock, POST /api/demo/advance, POST /api/demo/reset).
// Rendered only in demo mode: a 404 from the clock hides it.
// inline: the stage's bar, with every action as a visible button instead of a menu.
export default function DemoControls({ inline = false }) {
  const { circleData, demoAdvance, demoReset, showToast, isSignedIn } = useApp();
  const [clock, setClock] = useState(null);
  const [demoMode, setDemoMode] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [busy, setBusy] = useState(false);
  const menuRef = useRef(null);

  const loadClock = useCallback(() => apiClient.getDemoClock().then(
    c => { setClock(c); setDemoMode(Boolean(c)); },
    err => console.warn('Could not read the demo clock:', err)
  ), []);

  useEffect(() => {
    loadClock();
    const timer = setInterval(loadClock, CLOCK_REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadClock]);

  // The archivist is writing up a story: moving the clock now waits for it (POST /api/demo/advance).
  const archiving = useDemoArchiving(demoMode);

  // Close the menu on a click outside it or on Escape.
  useEffect(() => {
    if (!menuOpen) return;
    const onPointer = (e) => { if (!menuRef.current?.contains(e.target)) setMenuOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  if (!demoMode) return null;

  const timeZone = circleData?.circle?.timezone;
  const nextMorningHours = hoursToNextMorning(clock?.now, circleData?.circle?.chat_time, timeZone);

  const run = async (action, doneMessage) => {
    setMenuOpen(false);
    setBusy(true);
    try {
      const result = await action();
      showToast(typeof doneMessage === 'function' ? doneMessage(result) : doneMessage, 'info');
    } catch (err) {
      console.error('Demo control failed:', err);
      showToast("That didn't work. Please try again.", 'error');
    } finally {
      await loadClock();
      setBusy(false);
    }
  };

  // The server waits for a story being written up before it moves the clock (archive_wait).
  const advance = (hours, label) => run(() => demoAdvance(hours), result => (
    result?.archive_wait === 'timed_out'
      ? `Moved ahead: ${label}. The story was still being written up; it may need another move.`
      : `Moved ahead: ${label}`
  ));
  const busyLabel = archiving ? 'Waiting for the story...' : 'Moving time...';
  const writing = archiving && (
    <span className="demo-archiving" role="status">
      <span className="demo-spinner" aria-hidden="true" />
      Evoca is writing up the story...
    </span>
  );

  const handleReset = async () => {
    setConfirmReset(false);
    await run(demoReset, 'The demo has started over');
  };

  const resetDialog = confirmReset && (
    <Modal onClose={() => setConfirmReset(false)} labelledBy="reset-dialog-title" sheetStyle={{ maxWidth: '440px' }}>
      <div className="modal-title-row">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-terracotta)' }}>
          <AlertTriangle size={20} />
          <h3 id="reset-dialog-title" className="archival-dialog-title" style={{ margin: 0 }}>Reset the demo?</h3>
        </div>
      </div>
      <p style={{ fontSize: '14px', lineHeight: '1.6', margin: '16px 0', color: 'var(--text-charcoal-muted)' }}>
        The demo family goes back to its starting stories and the clock goes back to today.
        Everything recorded, asked or uploaded since then is deleted.
      </p>
      <div className="dialog-action-bar">
        <button type="button" className="editorial-btn secondary" onClick={() => setConfirmReset(false)}>
          Cancel
        </button>
        <button type="button" className="editorial-btn primary" onClick={handleReset}>
          Reset demo
        </button>
      </div>
    </Modal>
  );

  if (inline) {
    return (
      <div className="demo-controls inline" role="group" aria-label="Demo clock">
        {writing}
        <span className="demo-clock-text">
          <Clock size={13} />
          Demo time <b data-testid="demo-clock">{busy ? busyLabel : formatDemoClock(clock?.now, timeZone)}</b>
        </span>
        <button type="button" className="stage-btn" onClick={() => advance(1, '1 hour')} disabled={busy}>+1 hour</button>
        <button
          type="button"
          className="stage-btn"
          onClick={() => advance(nextMorningHours, 'next morning')}
          disabled={busy || nextMorningHours == null}
          title={circleData?.circle?.chat_time ? `To ${circleData.circle.chat_time} tomorrow, the family's chat time` : undefined}
        >
          Next morning
        </button>
        <button type="button" className="stage-btn" onClick={() => advance(24, '1 day')} disabled={busy}>+1 day</button>
        {!isSignedIn && (
          <button type="button" className="stage-btn quiet" onClick={() => setConfirmReset(true)} disabled={busy}>Reset</button>
        )}
        {resetDialog}
      </div>
    );
  }

  return (
    <div className="demo-controls" ref={menuRef}>
      {writing}
      <button
        type="button"
        className="demo-clock-chip"
        onClick={() => setMenuOpen(open => !open)}
        disabled={busy}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        title="Demo clock: move time forward or start over"
      >
        <Clock size={12} />
        <span data-testid="demo-clock">{busy ? busyLabel : formatDemoClock(clock?.now, timeZone)}</span>
        <ChevronDown size={12} />
      </button>

      {menuOpen && (
        <div className="demo-menu" role="menu" aria-label="Demo controls">
          <button type="button" role="menuitem" onClick={() => advance(1, '1 hour')}>+1 hour</button>
          <button
            type="button"
            role="menuitem"
            onClick={() => advance(nextMorningHours, 'next morning')}
            disabled={nextMorningHours == null}
            title={circleData?.circle?.chat_time ? `To ${circleData.circle.chat_time} tomorrow, the family's chat time` : undefined}
          >
            Next morning
          </button>
          <button type="button" role="menuitem" onClick={() => advance(24, '1 day')}>+1 day</button>
          {/* A reset rebuilds the database and deletes every family made with "Create your family". */}
          {!isSignedIn && (
            <button type="button" role="menuitem" className="danger" onClick={() => { setMenuOpen(false); setConfirmReset(true); }}>
              Reset demo
            </button>
          )}
        </div>
      )}

      {resetDialog}
    </div>
  );
}
