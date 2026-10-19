import React, { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from 'react';
import { useApp } from '../context/useApp';
import { apiClient } from '../api/client';
import { listenForChanges, listenForTour, sendTour } from '../utils/stageChannel';
import { findTourTargets, isSuggestedQuestion, isUncovered, unionRect } from '../utils/tour';
import { useMediaQuery } from '../utils/useMediaQuery';
import { X } from 'lucide-react';
import '../styles/tour.css';

const POLL_MS = 3000;
const LAYOUT_MS = 200;
const SETTLE_MS = 300;               // conditions must hold this long before the step moves on
const MEASURE_GIVE_UP_MS = 2500;     // no visible target by then: the card shows without a spotlight
const SESSION_REPLY_MS = 600;
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
  { text: 'Evoca writes up the story and finds the part that answers Elif. The family has 24 hours to hide it before it is shared.',
    hint: 'Then press +1 day.', dockedHint: 'Then open Demo at the top and press +1 day.', done: 'question answered' },
  { text: "Elif hears the answer in Grandma's own voice. React to it.", done: 'reaction made' },
  { text: 'The next morning, Grandma hears it too.', done: 'next morning opening heard' },
];
const END = STEPS.length;
const NO_ANSWER = "Evoca didn't find an answer to Elif's question in this conversation. Talk again the next morning, or skip this step.";
const NEXT_MORNING = { place: 'strip', targets: ['next-morning', 'demo-menu'] };

// What a step shows: where (a pane or the demo strip) and the data-tour names, the first present wins.
function stepTarget(step, lightOn) {
  switch (step) {
    case 0: return { place: 'panel', targets: ['ask', 'ask-alt'] };
    case 1: return NEXT_MORNING;
    case 2: return { place: 'device', targets: ['talk'] };
    case 3: return { place: 'device', targets: ['answer'] };
    case 4: return { place: 'strip', targets: ['archiving', 'plus-day', 'demo-menu'] };
    case 5: return { place: 'panel', targets: ['answer-card', 'questions-tab'] };
    case 6: return lightOn ? { place: 'device', targets: ['talk'] } : NEXT_MORNING;
    default: return null;
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

const NO_FACTS = { questionExists: false, answered: false, reacted: false, lightOn: false, clockMoved: false, archiving: false, now: 0 };

// Each transition in dev builds: from, to, why.
function logTransition(from, to, reason) {
  if (import.meta.env.DEV) console.info(`[tour] step ${from + 1} -> ${to >= END ? 'end' : to + 1}: ${reason}`);
}

// --- Geometry (viewport pixels) ---

const area = (r) => Math.max(1, r.width * r.height);
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const pad = (r, p) => ({ left: r.left - p, top: r.top - p, width: r.width + 2 * p, height: r.height + 2 * p });
const onScreen = (r) => r && r.top + r.height > 0 && r.top < window.innerHeight && r.left + r.width > 0 && r.left < window.innerWidth;

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
// conversation is running on the device). Each step has a condition, checked on every change (stage
// channel events from the panes, and polling the existing endpoints). The tour only moves forward:
// once the conditions have held for a moment, it skips past every step that is already done.
// The pane finds the step's target, scrolls it into view and sends its box once nothing covers it;
// the stage then fades in a spotlight around it and puts the card beside it. Docked below 1100 px.
// onExplore opens the person picker.
export default function GuidedTour({ skipReset = false, centerId, askerId, onExplore }) {
  const { closeTour, startTour, openCreateFamily, demoReset } = useApp();
  const [phase, setPhase] = useState(skipReset ? 'running' : 'checking');  // checking | confirm | resetting | running
  const [facts, setFacts] = useState(NO_FACTS);
  const [flags, dispatch] = useReducer(flagsReducer, NO_FLAGS);
  const [step, setStep] = useState(0);
  const [paneRect, setPaneRect] = useState(null);   // { key, rect, visible } from the pane, in its own viewport
  const [layout, setLayout] = useState(null);       // { key, spot, glide, card }
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
    }, SETTLE_MS);
    return () => clearTimeout(timer);
  }, [phase, step, conditionKey]);

  const skip = () => {
    logTransition(step, step + 1, 'skipped');
    setStep(step + 1);
  };

  const running = phase === 'running';
  const current = running && step < END ? STEPS[step] : null;
  const target = current ? stepTarget(step, facts.lightOn) : null;
  // The key names the step's target: "<step>|<place>|<names>".
  const key = target ? `${step}|${target.place}|${target.targets.join(',')}` : '';
  const noAnswer = step === 4 && flags.endClock != null && !facts.answered && !facts.archiving
    && facts.now - flags.endClock >= DAY_MS;
  const hint = noAnswer ? null : (docked && current?.dockedHint) || current?.hint;

  // --- Tell the pane what to show; its box comes back over the channel ---
  useEffect(() => {
    const [, place, names] = key.split('|');
    const pane = place === 'device' || place === 'panel' ? place : null;
    const message = { kind: 'targets', pane, targets: pane ? names.split(',') : [], key };
    sendTour(message);
    return listenForTour(m => {
      if (m.kind === 'hello') sendTour(message);
      if (m.kind === 'rect' && m.key === key) setPaneRect({ key, rect: m.rect, visible: m.visible });
    });
  }, [key]);
  useEffect(() => () => sendTour({ kind: 'targets', pane: null, targets: [], key: '' }), []);

  // Docked, a strip target is at the top of the page.
  const onStrip = target?.place === 'strip';
  useEffect(() => {
    if (docked && onStrip) window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [docked, onStrip, key]);

  // --- Spotlight and card: measured again as anything moves; shown only once the target is ---
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
      let spot = null;
      let same = null;
      if (target?.place === 'strip') {
        const found = findTourTargets(target.targets);
        if (found.length && found.every(isUncovered)) spot = unionRect(found);
      } else if (target) {
        same = target.place === 'device' ? device : phone;
        const frame = rectOf(target.place === 'device' ? 'iframe.device-frame' : 'iframe.phone-frame');
        const measured = paneRect?.key === key && paneRect.visible ? paneRect.rect : null;
        if (frame && measured) {
          spot = { left: frame.left + measured.left, top: frame.top + measured.top, width: measured.width, height: measured.height };
        }
      }
      // The page itself scrolls (stacked panes): a target off screen, or under the docked card, comes
      // to the middle of what is left; once per target and window size.
      const room = docked ? vh - h - 2 * EDGE : vh;
      const scrollKey = `${key}|${vw}x${vh}`;
      if (spot && scrolledRef.current !== scrollKey && (spot.top < 0 || spot.top + spot.height > room)) {
        scrolledRef.current = scrollKey;
        window.scrollBy({ top: spot.top - Math.max(EDGE, (room - spot.height) / 2), behavior: 'smooth' });
      }
      const waited = Date.now() - keyStartRef.current.at;
      setLayout(prev => {
        let next;
        if (!target) {
          next = { key, spot: null, card: { left: (vw - w) / 2, top: vh - h - 24, arrow: null } };
        } else if (!spot && prev?.key === key && prev.card && !prev.kept) {
          // The target went out of sight within the step (the pane scrolls it back): no spotlight,
          // and the card stays without its arrow.
          next = { key, spot: null, card: { ...prev.card, arrow: null } };
        } else if (!spot) {
          // A new step, not measured yet: the card waits; the previous spotlight stays (and glides on
          // from there) only if it is still on screen, and only for a moment. After that the card
          // shows alone rather than point at nothing.
          const late = waited > MEASURE_GIVE_UP_MS;
          const keep = !late && prev?.spot && onScreen(prev.spot) && (prev.key !== key || prev.kept) ? prev.spot : null;
          next = { key, spot: keep, kept: Boolean(keep), glide: Boolean(keep), card: late ? { left: (vw - w) / 2, top: vh - h - 24, arrow: null } : null };
        } else {
          const others = [device, phone, rectOf('.demo-strip-inner')].filter(r => r && r !== same);
          const glide = prev?.key === key ? prev.glide : Boolean(prev?.spot && onScreen(prev.spot));
          let card;
          if (docked) {
            const top = vh - h - EDGE;
            card = { top, arrow: spot.top + spot.height / 2 < top ? 'up' : 'down', offset: clamp(spot.left + spot.width / 2 - 16, 24, w - 24) };
          } else {
            card = placeBeside(spot, same, others, w, h, vw, vh) || { left: vw - w - EDGE, top: vh - h - EDGE, arrow: null };
          }
          next = { key, spot, glide, card };
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
  const spot = running && layout?.spot ? pad(layout.spot, PAD) : null;
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
      <p id="tour-card-text" className="tour-card-text">{noAnswer ? NO_ANSWER : current.text}</p>
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
    {/* The scrim with a cut-out around the target; it never takes a click. */}
    <div
      className={`tour-spotlight ${spot ? 'on' : ''} ${layout?.glide ? 'glide' : ''}`}
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
