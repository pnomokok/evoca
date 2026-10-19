import React, { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from 'react';
import { useApp } from '../context/useApp';
import { apiClient } from '../api/client';
import { listenForChanges, listenForTour, sendTour } from '../utils/stageChannel';
import { findTourTargets, isSuggestedQuestion, unionRect } from '../utils/tour';
import { useMediaQuery } from '../utils/useMediaQuery';
import { X } from 'lucide-react';
import '../styles/tour.css';

const POLL_MS = 3000;
const LAYOUT_MS = 250;
const SESSION_REPLY_MS = 600;
const TRACE_MS = 5000;               // how long step 3 shows the tool trace after the opening
const UNANSWERED_MS = 24 * 3600_000; // a day after the session and still no answer: it waits again
const GAP = 18;
const EDGE = 12;
const PAD = 8;

const STEPS = [
  { text: 'Elif lives far away. She asks Grandma a question. Send the suggested question; the sample answers fit it. Or write your own and answer with your voice.' },
  { text: "Grandma's device wakes up at chat time.", hint: 'Press Next morning.',
    dockedHint: 'Open Demo at the top, then press Next morning.' },
  { text: "Press Talk. Evoca brings up Elif's question at the right moment. Below the device you can watch the MCP tools it calls." },
  { text: 'Answer as Fatma: speak, or use a sample answer. Say goodbye when you are done.' },
  { text: 'Evoca writes up the story and finds the part that answers Elif. The family has 24 hours to hide it before it is shared.',
    hint: 'Then press +1 day.', dockedHint: 'Then open Demo at the top and press +1 day.' },
  { text: "Elif hears the answer in Grandma's own voice. React to it." },
  { text: 'The next morning, Grandma hears it too.' },
];
const END = STEPS.length;
const NEXT_MORNING = { place: 'strip', targets: ['next-morning', 'demo-menu'] };

// What a step shows: where (a pane or the demo strip) and the data-tour names, the first present wins.
function stepTarget(step, { lightOn, flags }) {
  switch (step) {
    case 0: return { place: 'panel', targets: ['ask', 'ask-alt'] };
    case 1: return NEXT_MORNING;
    case 2: return { place: 'device', targets: [flags.sessionOpen && flags.openingAt != null ? 'trace' : 'talk'] };
    case 3: return { place: 'device', targets: ['answer'] };
    case 4: return { place: 'strip', targets: ['archiving', 'plus-day', 'demo-menu'] };
    case 5: return { place: 'panel', targets: ['answer-card', 'questions-tab'] };
    case 6: return lightOn ? { place: 'device', targets: ['talk'] } : NEXT_MORNING;
    default: return null;
  }
}

// What the device told the stage since the tour started the demo over.
const NO_FLAGS = { sessionOpen: false, openingAt: null, turned: false, asked: false, endClock: null, morningHeard: false };

function flagsReducer(flags, action) {
  switch (action.type) {
    case 'session_start': return { ...flags, sessionOpen: true, openingAt: null, turned: false };
    // The last step's opening: after a reaction, or whenever that step is showing (it may be skipped to).
    case 'opening_played': return { ...flags, openingAt: Date.now(), morningHeard: flags.morningHeard || action.morning };
    case 'question_asked': return { ...flags, asked: true, endClock: null };
    case 'turn_sent': return { ...flags, turned: true };
    case 'session_end': return { ...flags, sessionOpen: false, openingAt: null, endClock: flags.asked ? action.now : flags.endClock };
    case 'reset': return NO_FLAGS;
    default: return flags;
  }
}

const NO_FACTS = { questionExists: false, answered: false, reacted: false, lightOn: false, clockMoved: false, archiving: false, now: 0 };

// --- Geometry (viewport pixels) ---

const area = (r) => Math.max(1, r.width * r.height);
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const pad = (r, p) => ({ left: r.left - p, top: r.top - p, width: r.width + 2 * p, height: r.height + 2 * p });

function overlap(a, b) {
  if (!a || !b) return 0;
  const w = Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left);
  const h = Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top);
  return w > 0 && h > 0 ? w * h : 0;
}

function rectOf(selector) {
  const r = document.querySelector(selector)?.getBoundingClientRect();
  return r ? { left: r.left, top: r.top, width: r.width, height: r.height } : null;
}

// The card beside its target: each side of the target and each side of the target's pane is tried.
// Never over the target; then the least cover of the same pane (weighted) and of the other areas (the
// other pane, the demo strip), each as a share of that area; beside beats above or below, and nearer
// wins a tie. Beside the target, the card starts at the target's top, so the words above stay clear.
// null when nothing fits.
function placeBeside(target, same, others, w, h, vw, vh) {
  const cx = target.left + target.width / 2;
  const cy = target.top + target.height / 2;
  let best = null;
  for (const anchor of same ? [target, same] : [target]) {
    for (const side of ['right', 'left', 'below', 'above']) {
      const left = side === 'right' ? anchor.left + anchor.width + GAP
        : side === 'left' ? anchor.left - GAP - w
          : clamp(cx - w / 2, EDGE, vw - w - EDGE);
      const top = side === 'below' ? anchor.top + anchor.height + GAP
        : side === 'above' ? anchor.top - GAP - h
          : clamp(target.top - 10, EDGE, vh - h - EDGE);
      if (left < EDGE || left + w > vw - EDGE || top < EDGE || top + h > vh - EDGE) continue;
      const card = { left, top, width: w, height: h };
      if (overlap(card, pad(target, PAD))) continue;
      const distance = Math.hypot(left + w / 2 - cx, top + h / 2 - cy);
      const score = (same ? 1.5 * overlap(card, same) / area(same) : 0)
        + others.reduce((sum, o) => sum + overlap(card, o) / area(o), 0)
        + (side === 'above' || side === 'below' ? 0.03 : 0)
        + distance / 10000;
      if (!best || score < best.score) {
        const arrow = { right: 'left', left: 'right', below: 'up', above: 'down' }[side];
        const offset = arrow === 'left' || arrow === 'right' ? clamp(cy - top, 20, h - 20) : clamp(cx - left, 20, w - 20);
        best = { left, top, arrow, offset, score };
      }
    }
  }
  return best && { left: best.left, top: best.top, arrow: best.arrow, offset: best.offset };
}

// The guided tour on "Watch the loop" (demo only). Starting it resets the demo (after asking, if a
// conversation is running on the device). Each step has a condition, checked again on every change
// (stage channel events from the panes, and polling the existing endpoints); the card shows the first
// step whose condition is not met yet, so acting early or in another order never gets stuck.
// The pane finds the step's target, scrolls it into view and sends its box; the stage dims both panes
// with a spotlight around it and puts the card beside it. Docked at the bottom below 1100 px.
// notice: the phone's answer notification (StageView); onExplore opens the person picker.
export default function GuidedTour({ skipReset = false, notice, centerId, askerId, onExplore }) {
  const { closeTour, startTour, openCreateFamily, demoReset } = useApp();
  const [phase, setPhase] = useState(skipReset ? 'running' : 'checking');  // checking | confirm | resetting | running
  const [facts, setFacts] = useState(NO_FACTS);
  const [flags, dispatch] = useReducer(flagsReducer, NO_FLAGS);
  const [skipFloor, setSkipFloor] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [paneRect, setPaneRect] = useState(null);   // { key, rect } from the pane, in its own viewport
  const [layout, setLayout] = useState(null);
  const cardRef = useRef(null);
  const scrolledRef = useRef('');
  const factsRef = useRef(facts);
  const stepRef = useRef(null);
  const docked = useMediaQuery('(max-width: 1100px)');

  // demoReset is a new function on every render of the app; the start must run once.
  const demoResetRef = useRef(demoReset);
  useEffect(() => { factsRef.current = facts; demoResetRef.current = demoReset; });

  // --- Starting: ask the device, maybe confirm, reset the demo ---
  const resetAndRun = useCallback(async () => {
    setPhase('resetting');
    try {
      await demoResetRef.current();
    } catch (err) {
      console.warn('The guide could not reset the demo:', err);
    }
    dispatch({ type: 'reset' });
    setPhase('running');
  }, []);

  useEffect(() => {
    if (skipReset) return undefined;
    let decided = false;
    const decide = (open) => {
      if (decided) return;
      decided = true;
      if (open) setPhase('confirm');
      else resetAndRun();
    };
    const stop = listenForTour(m => {
      if (m.kind === 'event' && (m.name === 'session_open' || m.name === 'session_closed')) decide(m.name === 'session_open');
    });
    sendTour({ kind: 'ask-session' });
    const timer = setTimeout(() => decide(false), SESSION_REPLY_MS);   // no device pane: nothing running
    return () => { decided = true; stop(); clearTimeout(timer); };
  }, [skipReset, resetAndRun]);

  // --- Facts from the server ---
  const refresh = useCallback(async () => {
    if (!centerId || !askerId) return;
    const [questions, invitation, status, clock] = await Promise.all([
      apiClient.getMyQuestions(askerId).catch(() => null),
      apiClient.getDeviceInvitation(centerId).catch(() => null),
      apiClient.getDemoStatus().catch(() => null),
      apiClient.getDemoClock().catch(() => null),
    ]);
    const list = questions || [];
    const answeredQ = list.find(q => q.status === 'answered' && q.answer_story_id && isSuggestedQuestion(q.text))
      || list.find(q => q.status === 'answered' && q.answer_story_id);
    const story = answeredQ ? await apiClient.getStory(answeredQ.answer_story_id, askerId).catch(() => null) : null;
    setFacts({
      questionExists: list.length > 0,
      answered: Boolean(answeredQ),
      reacted: Boolean(story?.reactions?.mine?.length),
      lightOn: Boolean(invitation?.active),
      clockMoved: Number(clock?.offset_hours) > 0,
      archiving: Boolean(status?.archiving),
      now: clock?.now ? new Date(clock.now).getTime() : 0,
    });
  }, [centerId, askerId]);

  useEffect(() => {
    if (phase !== 'running') return undefined;
    const first = setTimeout(refresh, 0);
    const poll = setInterval(refresh, POLL_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const stopChanges = listenForChanges(reason => {
      if (reason === 'session_end') dispatch({ type: 'session_end', now: factsRef.current.now });
      if (reason === 'reset') { dispatch({ type: 'reset' }); setSkipFloor(0); }
      refresh();
    });
    const stopEvents = listenForTour(m => {
      if (m.kind !== 'event') return;
      dispatch({ type: m.name, morning: factsRef.current.reacted || stepRef.current === END - 1 });
      refresh();
    });
    return () => { clearTimeout(first); clearInterval(poll); clearInterval(tick); stopChanges(); stopEvents(); };
  }, [phase, refresh]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(refresh, 0);
    return () => clearTimeout(timer);
  }, [notice, refresh]);

  // --- Which step: the first one whose condition is not met yet (never below a skipped step) ---
  // Asked, but a day after the session still no answer (the archivist found none): it waits again.
  const asked = flags.asked && !(flags.endClock != null && !flags.sessionOpen && !facts.answered && !facts.archiving
    && facts.now - flags.endClock >= UNANSWERED_MS);
  const conditions = [
    facts.questionExists,
    (facts.lightOn && facts.clockMoved) || flags.sessionOpen || asked || facts.answered,
    facts.answered || (asked && !flags.sessionOpen)
      || (flags.sessionOpen && flags.openingAt != null && (flags.turned || now - flags.openingAt >= TRACE_MS)),
    facts.answered || (asked && !flags.sessionOpen),
    facts.answered,
    facts.reacted,
    flags.morningHeard,
  ];
  // A skipped step counts as done.
  const firstUnmet = conditions.findIndex((met, i) => !met && i >= skipFloor);
  const step = phase === 'running' ? (firstUnmet === -1 ? END : firstUnmet) : null;
  useEffect(() => { stepRef.current = step; });
  const current = step != null && step < END ? STEPS[step] : null;
  const target = current ? stepTarget(step, { lightOn: facts.lightOn, flags }) : null;
  // The key names the step's target: "<step>|<place>|<names>".
  const key = target ? `${step}|${target.place}|${target.targets.join(',')}` : '';
  const hint = (docked && current?.dockedHint) || current?.hint;

  // --- Tell the pane what to show; its box comes back over the channel ---
  useEffect(() => {
    const [, place, names] = key.split('|');
    const pane = place === 'device' || place === 'panel' ? place : null;
    const message = { kind: 'targets', pane, targets: pane ? names.split(',') : [], key };
    sendTour(message);
    return listenForTour(m => {
      if (m.kind === 'hello') sendTour(message);
      if (m.kind === 'rect' && m.key === key) setPaneRect({ key, rect: m.rect });
    });
  }, [key]);
  useEffect(() => () => sendTour({ kind: 'targets', pane: null, targets: [], key: '' }), []);

  // Docked, a strip target is at the top of the page.
  const onStrip = target?.place === 'strip';
  useEffect(() => {
    if (docked && onStrip) window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [docked, onStrip, key]);

  // --- Spotlight and card position, measured again as anything moves ---
  useLayoutEffect(() => {
    const update = () => {
      const card = cardRef.current;
      if (!card) return;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const w = card.offsetWidth;
      const h = card.offsetHeight;
      const device = rectOf('.device-pane');
      const phone = rectOf('.stage-phone');
      let spot = null;
      let same = null;
      if (target?.place === 'strip') {
        spot = unionRect(findTourTargets(target.targets)) || rectOf('.demo-strip');
      } else if (target) {
        same = target.place === 'device' ? device : phone;
        const frame = rectOf(target.place === 'device' ? 'iframe.device-frame' : 'iframe.phone-frame');
        const rect = paneRect?.key === key ? paneRect.rect : null;
        if (frame && rect) {
          // Into stage coordinates, clipped to the frame: what is outside it cannot be seen.
          const left = Math.max(frame.left, frame.left + rect.left);
          const top = Math.max(frame.top, frame.top + rect.top);
          const right = Math.min(frame.left + frame.width, frame.left + rect.left + rect.width);
          const bottom = Math.min(frame.top + frame.height, frame.top + rect.top + rect.height);
          if (right - left > 4 && bottom - top > 4) spot = { left, top, width: right - left, height: bottom - top };
        }
        spot = spot || same;   // not found (yet): the whole pane
      }
      const others = [device, phone, rectOf('.demo-strip-inner')].filter(r => r && r !== same);
      // The page itself scrolls (stacked panes): bring a target that is off screen, or under the docked
      // card, to the middle of what is left; once per target and window size.
      const room = docked ? vh - h - 2 * EDGE : vh;
      const scrollKey = `${key}|${vw}x${vh}`;
      if (spot && scrolledRef.current !== scrollKey && (spot.top < 0 || spot.top + spot.height > room)) {
        scrolledRef.current = scrollKey;
        window.scrollBy({ top: spot.top - Math.max(EDGE, (room - spot.height) / 2), behavior: 'smooth' });
      }
      let next;
      if (!spot) {
        next = { spot: null, left: (vw - w) / 2, top: vh - h - 24, arrow: null };
      } else if (docked) {
        const top = vh - h - EDGE;
        const cy = spot.top + spot.height / 2;
        next = { spot, top, arrow: cy < top ? 'up' : 'down', offset: clamp(spot.left + spot.width / 2 - 16, 24, w - 24) };
      } else {
        next = { spot, ...(placeBeside(spot, same, others, w, h, vw, vh) || { left: vw - w - EDGE, top: vh - h - EDGE, arrow: null }) };
      }
      setLayout(prev => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
    };
    update();
    const timer = setInterval(update, LAYOUT_MS);
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      clearInterval(timer);
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  });

  // The card takes focus once, when the tour opens; Esc closes it.
  useEffect(() => {
    cardRef.current?.focus({ preventScroll: true });
    const onKey = (e) => { if (e.key === 'Escape') closeTour(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [closeTour]);

  const spot = layout?.spot ? pad(layout.spot, PAD) : null;
  const style = layout ? {
    top: `${layout.top}px`,
    ...(docked ? {} : { left: `${layout.left}px` }),
    '--arrow-offset': layout.offset != null ? `${layout.offset}px` : undefined
  } : { visibility: 'hidden' };
  const ended = phase === 'running' && step >= END;
  const className = `tour-card ${docked ? 'docked' : ''} ${layout?.arrow ? `arrow-${layout.arrow}` : ''} ${ended ? 'end' : ''}`;

  let label = 'Guide';
  let body;
  let actions = null;
  if (phase === 'confirm') {
    body = <p id="tour-card-text" className="tour-card-text">A conversation is running on Grandma's device. The guide starts the demo over, which ends it.</p>;
    actions = <>
      <button type="button" className="tour-btn quiet" onClick={closeTour}>Cancel</button>
      <button type="button" className="tour-btn primary" onClick={resetAndRun}>Start over</button>
    </>;
  } else if (phase !== 'running') {
    body = <p id="tour-card-text" className="tour-card-text" role="status">Starting the demo over...</p>;
  } else if (current) {
    label = `Guide · step ${step + 1} of ${END}`;
    body = <>
      <p id="tour-card-text" className="tour-card-text">{current.text}</p>
      {hint && <p className="tour-card-hint">{hint}</p>}
    </>;
    actions = <button type="button" className="tour-skip" onClick={() => setSkipFloor(step + 1)}>Skip step</button>;
  } else {
    label = 'Guide · done';
    body = <p id="tour-card-text" className="tour-card-text">That is the loop: a question, her voice, a reaction, the next conversation.</p>;
    actions = <>
      <button type="button" className="tour-btn primary" onClick={() => { closeTour(); onExplore(); }}>
        Explore as a family member
      </button>
      <button type="button" className="tour-btn" onClick={() => { closeTour(); openCreateFamily?.(); }}>
        Create your family
      </button>
      <button type="button" className="tour-btn quiet" onClick={() => startTour()}>Start again</button>
    </>;
  }

  return <>
    {/* The scrim with a cut-out around the target; it never takes a click. */}
    <div
      className={`tour-spotlight ${spot ? 'on' : ''}`}
      style={spot ? { left: `${spot.left}px`, top: `${spot.top}px`, width: `${spot.width}px`, height: `${spot.height}px` } : undefined}
      aria-hidden="true"
    />
    <div
      ref={cardRef}
      className={className}
      style={style}
      role="dialog"
      aria-modal="false"
      aria-labelledby="tour-card-step"
      aria-describedby="tour-card-text"
      tabIndex={-1}
      data-step={phase !== 'running' ? phase : current ? step + 1 : 'end'}
    >
      <div className="tour-card-head">
        <span id="tour-card-step" className="tour-card-step">{label}</span>
        <button type="button" className="tour-card-close" onClick={closeTour} aria-label="Close the guide">
          <X size={16} />
        </button>
      </div>
      <div aria-live="polite">{body}</div>
      {actions && <div className="tour-card-actions">{actions}</div>}
    </div>
  </>;
}
