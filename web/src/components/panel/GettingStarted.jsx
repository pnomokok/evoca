import React, { useEffect, useState } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import { dismissGettingStarted, gettingStartedDismissed } from '../../utils/inviteLinks';
import { focusLater } from '../../utils/focusLater';
import { Check, ChevronRight, X } from 'lucide-react';

// A new family's first steps, at the top of the journal until the first story arrives
// (FamilyDashboard shows it only signed in, with no stories). Admins see all four steps,
// members only "Ask your first question". Each step ticks from the API, so it is right on any
// device: her link and an invited member (has_invite on GET /api/circle), a question asked
// (GET /api/questions/mine), a topic added (GET /api/admin/sensitive-topics).
export default function GettingStarted() {
  const { circleData, currentViewerId, dataVersion, navigate } = useApp();
  const circleId = circleData?.circle?.id;
  const me = circleData?.me?.id === currentViewerId ? circleData.me : null;
  const isAdmin = me?.role === 'admin';
  const members = circleData?.members || [];
  const center = members.find(m => m.role === 'center');
  const centerFirst = center?.name?.split(' ')[0] || 'the storyteller';

  const [dismissed, setDismissed] = useState(() => gettingStartedDismissed(circleId));
  const [counts, setCounts] = useState(null);   // { questions, topics } once loaded

  useEffect(() => {
    if (!me || dismissed) return;
    let cancelled = false;
    Promise.all([
      apiClient.getMyQuestions().catch(() => []),
      isAdmin ? apiClient.getSensitiveTopics().catch(() => []) : Promise.resolve([])
    ]).then(([questions, topics]) => {
      if (!cancelled) setCounts({ questions: (questions || []).length, topics: (topics || []).length });
    });
    return () => { cancelled = true; };
  }, [me, isAdmin, dismissed, dataVersion]);

  if (!me || me.role === 'center' || dismissed || !counts) return null;

  const openSettings = (elementId, focusId) => {
    navigate({ tab: 'panel', subTab: 'settings' });
    focusLater(elementId, { focusId });
  };

  const steps = [
    isAdmin && {
      key: 'device',
      label: `Connect ${centerFirst}'s device: make her personal link`,
      done: Boolean(center?.has_invite),
      go: () => center && openSettings(`member-${center.id}`),
    },
    isAdmin && {
      key: 'invite',
      label: 'Invite your family',
      done: members.some(m => m.role !== 'center' && m.id !== me.id && m.has_invite),
      go: () => openSettings('members-heading'),
    },
    {
      key: 'ask',
      label: 'Ask your first question',
      done: counts.questions > 0,
      go: () => navigate({ tab: 'panel', subTab: 'questions' }),   // the first-question composer
    },
    isAdmin && {
      key: 'topics',
      label: 'Add topics to avoid',
      done: counts.topics > 0,
      go: () => openSettings('topics-heading', 'new-topic'),
    },
  ].filter(Boolean);

  if (steps.every(s => s.done)) return null;

  const dismiss = () => {
    dismissGettingStarted(circleId);
    setDismissed(true);
  };

  return (
    <section className="getting-started" aria-labelledby="getting-started-title" data-testid="getting-started">
      <div className="getting-started-head">
        <div>
          <h2 id="getting-started-title" className="getting-started-title">Getting started</h2>
          <p className="section-desc">
            {isAdmin
              ? `A few steps and ${centerFirst}'s first story is on its way.`
              : `Leave ${centerFirst} a question; her answer comes back here in her own voice.`}
          </p>
        </div>
        <button type="button" className="close-btn" onClick={dismiss} aria-label="Dismiss getting started">
          <X size={18} />
        </button>
      </div>
      <ol className="getting-started-steps">
        {steps.map((s, i) => (
          <li key={s.key} className={s.done ? 'done' : ''} data-testid={`getting-started-${s.key}`}>
            <span className="getting-started-mark" aria-hidden="true">{s.done ? <Check size={14} /> : i + 1}</span>
            <button type="button" className="getting-started-step" onClick={s.go}>
              <span>
                {s.label}
                {s.done && <span className="sr-only"> (done)</span>}
              </span>
              <ChevronRight size={16} aria-hidden="true" className="getting-started-chevron" />
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
