import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { LogIn } from 'lucide-react';

// The token must not stay in the address bar (or reach history, bookmarks or a shared screen).
function dropTokenFromUrl() {
  window.history.replaceState(null, '', '/');
}

// /join/<token>: who the link is for (GET /api/invites/{token}), then "Join" signs this browser in
// (POST /api/invites/{token}/accept). Every failure looks the same, so a link reveals nothing.
export default function JoinPage({ token, onDone }) {
  const [state, setState] = useState({ phase: 'loading', invite: null });

  useEffect(() => {
    let cancelled = false;
    apiClient.getInvite(token).then(
      invite => { if (!cancelled) setState({ phase: 'ready', invite }); },
      () => {
        if (cancelled) return;
        dropTokenFromUrl();
        setState({ phase: 'invalid', invite: null });
      }
    );
    return () => { cancelled = true; };
  }, [token]);

  const join = async () => {
    setState(s => ({ ...s, phase: 'joining' }));
    try {
      const session = await apiClient.acceptInvite(token);
      apiClient.setSession(session);
      dropTokenFromUrl();
      onDone(true);
    } catch {
      dropTokenFromUrl();
      setState({ phase: 'invalid', invite: null });
    }
  };

  const leave = () => {
    dropTokenFromUrl();
    onDone(false);
  };

  const { phase, invite } = state;
  return (
    <div className="app-container join-page">
      <main className="view-viewport">
        <section className="side-archival-card join-card" aria-live="polite">
          <img className="brand-mark" src="/evoca-mark.svg" alt="" />
          {phase === 'loading' && <p className="section-desc" role="status">Opening your link...</p>}

          {(phase === 'ready' || phase === 'joining') && invite && <>
            <h1 className="section-title-serif">Welcome, {invite.person_name}.</h1>
            <p className="section-desc">You are joining {invite.circle_name}.</p>
            <button type="button" className="editorial-btn primary" onClick={join} disabled={phase === 'joining'} autoFocus>
              <LogIn size={15} />
              <span>{phase === 'joining' ? 'Joining...' : 'Join'}</span>
            </button>
          </>}

          {phase === 'invalid' && <>
            <h1 className="section-title-serif">This link doesn't work</h1>
            <p className="section-desc">It may be old or mistyped. Ask your family for a new link.</p>
            <button type="button" className="editorial-btn secondary" onClick={leave}>Go to Evoca</button>
          </>}
        </section>
      </main>
    </div>
  );
}
