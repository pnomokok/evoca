import React, { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from 'react';
import { useApp } from '../context/useApp';
import { apiClient } from '../api/client';
import { listenForChanges, listenForTour, sendTour } from '../utils/stageChannel';
import { TOUR_ANSWER_STEP, boxOf, findTourTargets, isSuggestedQuestion, isUncovered } from '../utils/tour';
import { useMediaQuery } from '../utils/useMediaQuery';
import { X } from 'lucide-react';
import '../styles/tour.css';

const POLL_MS = 3000;
const LAYOUT_MS = 200;
const SETTLE_MS = 300;               // conditions must hold this long before the step moves on
const MEASURE_GIVE_UP_MS = 2500;     // no visible targets by then: the card shows without a spotlight
const SESSION_REPLY_MS = 600;
const STATUS_FRESH_MS = 1500;        // step 5 trusts "not writing" only from a status read this long after it began
const DAY_MS = 24 * 3600_000;
const GAP = 18;
const EDGE = 12;
const PAD = 8;

const STEPS = [
  { text: 'Elif lives far away. She asks Grandma a question. The suggested question is ready; press Send. The sample answers fit it. Want to ask your own? Edit the text, or later use +.',
    done: 'question sent' },
  { text: "Grandma's device wakes up at chat time.", hint: 'Press Next morning.',
    dockedHint: 'Open Demo at the top, then press Next morning.', done: 'chat time reached' },
  { text: "Press Talk. Evoca brings up Elif's question at the right moment.", done: 'conversation started' },
  { text: 'Answer as Fatma: speak, or use a sample answer. Say goodbye when you are done.', done: 'conversation ended' },
  { text: "The story is ready. Press +1 day to skip the family's 24-hour window.",
    dockedHint: 'Open Demo at the top first.', done: 'question answered' },
  { text: "Elif hears the answer in Grandma's own voice. React to it.", done: 'reaction made' },
  { text: 'The next morning, Grandma hears it too.', hint: 'Press Next morning, then Talk.',
    dockedHint: 'Open Demo at the top, press Next morning, then Talk.', done: 'next morning opening heard' },
];
const END = STEPS.length;
const WRITING = 'Evoca is writing up the story from the conversation. This takes about half a minute; wait before moving the clock.';
const NO_ANSWER = "Evoca didn't find an answer to Elif's question in this conversation. Talk again the next morning, or skip this step.";

// Each step's one set of targets, fixed while the step shows: [{ place, names }], the card points at
// the first. place: a pane ('panel', 'device') or the demo strip. Below 1100 px the clock buttons are
// folded into the strip's Demo menu, so the menu button stands in for them. Step 5 has two phases:
// while the story is written up nothing is highlighted, then "+1 day".
function stepTargets(step, docked, writing) {
  const clock = (name) => ({ place: 'strip', names: [docked ? 'demo-menu' : name] });
  switch (step) {
    case 0: return [{ place: 'panel', names: ['ask'] }];
    case 1: return [clock('next-morning')];
    case 2: return [{ place: 'device', names: ['talk'] }];
    case 3: return [{ place: 'device', names: ['answer'] }];      // Hold, and the sample answer or its note
    case 4: return writing ? [] : [clock('plus-day')];
    case TOUR_ANSWER_STEP: return [{ place: 'panel', names: ['answer-card'] }];  // play and the reactions
    case 6: return [clock('next-morning'), { place: 'device', names: ['talk'] }];
    default: return [];
  }
}

// What the device told the stage since the tour started the demo over.
const NO_FLAGS = { sessionOpen: false, endedAfterQuestion: false, endClock: null, morningHeard: false };

function flagsReducer(flags, action) {
  switch (action.type) {
    case 'session_start': return { ...flags, sessionOpen: true };
    // The last step's opening: after a reaction, or whenever that step is showing (it may be skipped to).
    case 'opening_played': return { ...flags, morningHeard: flags.morningHeard || action.morning };
    case 'session_end': return action.questionExists
      ? { ...flags, sessionOpen: false, endedAfterQuestion: true, endClock: action.now }
      : { ...flags, sessionOpen: false };
    case 'reset': return NO_FLAGS;
    default: return flags;
  }
}

const NO_FACTS = { questionExists: false, answered: false, reacted: false, clockMoved: false, lightOn: false, archiving: false, now: 0, fetchedAt: 0 };

// Each transition in dev builds: from, to, why.
function logTransition(from, to, reason) {
  if (import.meta.env.DEV) console.info(`[tour] step ${from + 1} -> ${to >= END ? 'end' : to + 1}: ${reason}`);
}

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

// The card beside its first target: each side of that target and each side of its pane is tried.
// Never over any target; then the least cover of the same pane (weighted) and of the other areas (the
// other pane, the demo strip), each as a share of that area; beside beats above or below, and nearer
// wins a tie. Beside the target, the card starts at the target's top, so the words above stay clear.
// null when nothing fits.
function placeBeside(target, spots, same, others, w, h, vw, vh) {
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
      if (spots.some(s => overlap(card, pad(s, PAD)))) continue;
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
// conversation is running on the device). Each step has a condition, checked on every change (stage
// channel events from the panes, and polling the existing endpoints). The tour only moves forward:
// once the conditions have held for a moment, it skips past every step that is already done.
// Each step has one fixed set of targets. The panes find theirs, scroll them into view and send their
// boxes once nothing covers them; the stage then fades in a spotlight with a cut-out for each and puts
// the card beside the first. Docked at the bottom below 1100 px. onExplore opens the person picker.
// onStep(step | null): the step showing, null while the tour is not running (the stage closes its
// answer banner on the listening step, so it never covers the answer card).
export default function GuidedTour({ skipReset = false, centerId, askerId, onExplore, onStep }) {
  const { closeTour, startTour, openCreateFamily, demoReset } = useApp();
  const [phase, setPhase] = useState(skipReset ? 'running' : 'checking');  // checking | confirm | resetting | running
  const [facts, setFacts] = useState(NO_FACTS);
  const [flags, dispatch] = useReducer(flagsReducer, NO_FLAGS);
  const [step, setStep] = useState(0);
  const [stepAt, setStepAt] = useState(0);         // when the current step began (ms)
  const [paneRects, setPaneRects] = useState({});   // pane -> { key, rects, visible }, in the pane's viewport
  const [layout, setLayout] = useState(null);       // { key, spots, card }
  const cardRef = useRef(null);
  const factsRef = useRef(facts);
  const stepRef = useRef(step);
  const keyStartRef = useRef({ key: '', at: 0 });
  const scrolledRef = useRef('');
  const docked = useMediaQuery('(max-width: 1100px)');
  // demoReset is a new function on every render of the app; the start must run once.
  const demoResetRef = useRef(demoReset);
  useEffect(() => { factsRef.current = facts; stepRef.current = step; demoResetRef.current = demoReset; });

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
      fetchedAt: Date.now(),
    });
  }, [centerId, askerId]);

  useEffect(() => {
    if (phase !== 'running') return undefined;
    const first = setTimeout(refresh, 0);
    const poll = setInterval(refresh, POLL_MS);
    const stopChanges = listenForChanges(reason => {
      if (reason === 'session_end') {
        dispatch({ type: 'session_end', questionExists: factsRef.current.questionExists, now: factsRef.current.now });
      }
      refresh();
    });
    const stopEvents = listenForTour(m => {
      if (m.kind !== 'event') return;
      dispatch({ type: m.name, morning: factsRef.current.reacted || stepRef.current === END - 1 });
      refresh();
    });
    return () => { clearTimeout(first); clearInterval(poll); stopChanges(); stopEvents(); };
  }, [phase, refresh]);

  // --- Moving forward: past every step whose condition holds, after they have held a moment ---
  const conditions = [
    facts.questionExists,
    (facts.lightOn && facts.clockMoved) || flags.sessionOpen || flags.endedAfterQuestion,
    flags.sessionOpen || flags.endedAfterQuestion,
    flags.endedAfterQuestion,
    facts.answered,
    facts.reacted,
    flags.morningHeard,
  ];
  const conditionKey = conditions.map(Number).join('');
  useEffect(() => {
    if (phase !== 'running' || step >= END) return undefined;
    const met = conditionKey.split('').map(c => c === '1');
    let next = step;
    while (next < END && met[next]) next += 1;
    if (next === step) return undefined;
    const timer = setTimeout(() => {
      logTransition(step, next, STEPS.slice(step, next).map(s => s.done).join(', '));
      setStep(next);
      setStepAt(Date.now());
    }, SETTLE_MS);
    return () => clearTimeout(timer);
  }, [phase, step, conditionKey]);

  const skip = () => {
    logTransition(step, step + 1, 'skipped');
    setStep(step + 1);
    setStepAt(Date.now());
  };

  const running = phase === 'running';
  const shownStep = running && step < END ? step : null;
  useEffect(() => { onStep?.(shownStep); }, [onStep, shownStep]);
  const current = running && step < END ? STEPS[step] : null;
  const noAnswer = step === 4 && flags.endClock != null && !facts.answered && !facts.archiving
    && facts.now - flags.endClock >= DAY_MS;
  // Step 5 waits for the write-up: until a status read since the step began says it is done.
  const writing = step === 4 && !noAnswer && (facts.archiving || facts.fetchedAt < stepAt + STATUS_FRESH_MS);
  const targets = current ? stepTargets(step, docked, writing) : [];
  // The key names the step's target set; it changes only with the step (or docking).
  const key = current ? `${step}|${JSON.stringify(targets)}` : '';
  const text = noAnswer ? NO_ANSWER : writing ? WRITING : current?.text;
  const hint = noAnswer || writing ? null : (docked && current?.dockedHint) || current?.hint;

  // --- Tell the panes their part of the set; their boxes come back over the channel ---
  useEffect(() => {
    const set = key ? JSON.parse(key.slice(key.indexOf('|') + 1)) : [];
    const byPane = {};
    set.filter(t => t.place !== 'strip').forEach(t => { byPane[t.place] = [...(byPane[t.place] || []), ...t.names]; });
    const message = { kind: 'targets', byPane, key };
    sendTour(message);
    return listenForTour(m => {
      if (m.kind === 'hello') sendTour(message);
      if (m.kind === 'rect' && m.key === key) setPaneRects(prev => ({ ...prev, [m.pane]: { key, rects: m.rects || [], visible: m.visible } }));
    });
  }, [key]);
  useEffect(() => () => sendTour({ kind: 'targets', byPane: {}, key: '' }), []);

  // Docked, a strip target is at the top of the page.
  const onStrip = targets[0]?.place === 'strip';
  useEffect(() => {
    if (docked && onStrip) window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [docked, onStrip, key]);

  // --- Spotlight and card: shown once every target of the set is measured and uncovered ---
  useLayoutEffect(() => {
    if (keyStartRef.current.key !== key) keyStartRef.current = { key, at: Date.now() };
    const update = () => {
      const card = cardRef.current;
      if (!card) return;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const w = card.offsetWidth;
      const h = card.offsetHeight;
      const device = rectOf('.device-pane');
      const phone = rectOf('.stage-phone');
      // One box per target, in stage coordinates; null while any part of the set is not visible.
      let spots = [];
      for (const t of targets) {
        if (t.place === 'strip') {
          const found = findTourTargets(t.names);
          if (!found.length || !found.every(isUncovered)) { spots = null; break; }
          spots.push(...found.map(boxOf));
        } else {
          const frame = rectOf(t.place === 'device' ? 'iframe.device-frame' : 'iframe.phone-frame');
          const got = paneRects[t.place];
          if (!frame || got?.key !== key || !got.visible || !got.rects.length) { spots = null; break; }
          spots.push(...got.rects.map(r => ({ left: frame.left + r.left, top: frame.top + r.top, width: r.width, height: r.height })));
        }
      }
      const first = spots?.[0];
      // The page itself scrolls (stacked panes): a first target off screen, or under the docked card,
      // comes to the middle of what is left; once per step and window size.
      const room = docked ? vh - h - 2 * EDGE : vh;
      const scrollKey = `${key}|${vw}x${vh}`;
      if (first && scrolledRef.current !== scrollKey && (first.top < 0 || first.top + first.height > room)) {
        scrolledRef.current = scrollKey;
        window.scrollBy({ top: first.top - Math.max(EDGE, (room - first.height) / 2), behavior: 'smooth' });
      }
      const waited = Date.now() - keyStartRef.current.at;
      const alone = { left: (vw - w) / 2, top: vh - h - 24, arrow: null };
      setLayout(prev => {
        let next;
        if (!current || !targets.length) {
          next = { key, spots: [], card: alone };
        } else if (!spots) {
          // Not measured (yet), or gone out of sight within the step (a pane scrolls it back): no
          // spotlight. The card waits, keeps its place without its arrow, or after a while shows alone.
          const placed = prev?.key === key && prev.card ? { ...prev.card, arrow: null } : null;
          next = { key, spots: [], card: placed || (waited > MEASURE_GIVE_UP_MS ? alone : null) };
        } else {
          const same = targets[0].place === 'device' ? device : targets[0].place === 'panel' ? phone : null;
          const others = [device, phone, rectOf('.demo-strip-inner')].filter(r => r && r !== same);
          let cardBox;
          if (docked) {
            const top = vh - h - EDGE;
            cardBox = { top, arrow: first.top + first.height / 2 < top ? 'up' : 'down', offset: clamp(first.left + first.width / 2 - 16, 24, w - 24) };
          } else {
            cardBox = placeBeside(first, spots, same, others, w, h, vw, vh) || { left: vw - w - EDGE, top: vh - h - EDGE, arrow: null };
          }
          next = { key, spots, card: cardBox };
        }
        return JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
      });
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

  // Before the tour runs (confirm, resetting) the card sits low in the middle, without a spotlight.
  const placed = running ? (layout?.key === key ? layout.card : null) : { left: null, top: null, arrow: null };
  const spots = running && layout?.key === key ? layout.spots.map(s => pad(s, PAD)) : [];
  const style = placed && placed.top != null ? {
    top: `${placed.top}px`,
    ...(docked ? {} : { left: `${placed.left}px` }),
    '--arrow-offset': placed.offset != null ? `${placed.offset}px` : undefined
  } : placed ? undefined : { visibility: 'hidden', opacity: 0 };
  const ended = running && step >= END;
  const className = [
    'tour-card', docked && 'docked', placed?.arrow && `arrow-${placed.arrow}`, ended && 'end', !running && 'intro'
  ].filter(Boolean).join(' ');

  let label = 'Guide';
  let body;
  let actions = null;
  if (phase === 'confirm') {
    body = <p id="tour-card-text" className="tour-card-text">A conversation is running on Grandma's device. The guide starts the demo over, which ends it.</p>;
    actions = <>
      <button type="button" className="tour-btn quiet" onClick={closeTour}>Cancel</button>
      <button type="button" className="tour-btn primary" onClick={resetAndRun}>Start over</button>
    </>;
  } else if (!running) {
    body = <p id="tour-card-text" className="tour-card-text" role="status">Starting the demo over...</p>;
  } else if (current) {
    label = `Guide · step ${step + 1} of ${END}`;
    body = <>
      <p id="tour-card-text" className="tour-card-text">{text}</p>
      {writing && <span className="tour-progress" role="progressbar" aria-label="Writing up the story" />}
      {hint && <p className="tour-card-hint">{hint}</p>}
    </>;
    // While a conversation runs, step 4 ends it for you instead of skipping.
    actions = step === 3 && flags.sessionOpen
      ? <button type="button" className="tour-skip" onClick={() => sendTour({ kind: 'goodbye' })}>Say goodbye for me</button>
      : <button type="button" className="tour-skip" onClick={skip}>Skip step</button>;
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
    {/* The scrim: one rounded cut-out per target (an SVG mask), each with the same glow. It never
        takes a click. */}
    <svg className={`tour-scrim ${spots.length ? 'on' : ''}`} aria-hidden="true">
      <defs>
        <mask id="tour-scrim-mask">
          <rect x="0" y="0" width="100%" height="100%" fill="white" />
          {spots.map((s, i) => <rect key={i} x={s.left} y={s.top} width={s.width} height={s.height} rx="14" fill="black" />)}
        </mask>
      </defs>
      <rect x="0" y="0" width="100%" height="100%" mask="url(#tour-scrim-mask)" />
    </svg>
    {spots.map((s, i) => (
      <div
        key={i}
        className="tour-glow"
        data-tour-spot={i}
        style={{ left: `${s.left}px`, top: `${s.top}px`, width: `${s.width}px`, height: `${s.height}px` }}
        aria-hidden="true"
      />
    ))}
    <div
      ref={cardRef}
      className={className}
      style={style}
      role="dialog"
      aria-modal="false"
      aria-labelledby="tour-card-step"
      aria-describedby="tour-card-text"
      tabIndex={-1}
      data-step={!running ? phase : current ? step + 1 : 'end'}
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
