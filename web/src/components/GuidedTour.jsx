import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useApp } from '../context/useApp';
import { apiClient } from '../api/client';
import { listenForChanges, listenForTour, sendTour } from '../utils/stageChannel';
import { useTourRings } from '../utils/tour';
import { useMediaQuery } from '../utils/useMediaQuery';
import { X } from 'lucide-react';
import '../styles/tour.css';

const POLL_MS = 3000;
const PLACE_MS = 400;
const GAP = 16;

// targets: data-tour names to ring, the first one present wins (on the stage itself or in a pane).
// place: where the card's arrow points: 'phone' | 'device' | 'strip'.
// dockedHint: below 1100 px the clock buttons are folded into the strip's Demo menu.
const NEXT_MORNING = { place: 'strip', targets: ['next-morning', 'demo-menu'] };
const STEPS = [
  { text: 'Elif lives far away. She asks Grandma a question.', hint: 'Press Send on her phone.',
    place: 'phone', targets: ['ask', 'ask-alt'] },
  { text: "Grandma's device wakes up at chat time.", hint: 'Press Next morning.',
    dockedHint: 'Open Demo at the top, then press Next morning.', ...NEXT_MORNING },
  { text: "Press Talk. Evoca brings up Elif's question at the right moment. Below the device you can watch the MCP tools it calls.",
    place: 'device', targets: ['talk'] },
  { text: 'Answer as Fatma: speak, or use a sample answer. Say goodbye when you are done.',
    place: 'device', targets: ['answer'] },
  { text: 'Evoca writes up the story and finds the part that answers Elif. The family has 24 hours to hide it before it is shared.',
    hint: 'Then press +1 day.', dockedHint: 'Then open Demo at the top and press +1 day.',
    place: 'strip', targets: ['archiving', 'plus-day', 'demo-menu'] },
  { text: "Elif hears the answer in Grandma's own voice. React to it.",
    place: 'phone', targets: ['answer-card', 'questions-tab'] },
  { text: 'The next morning, Grandma hears it too.', place: 'device', targets: ['talk'] },
];
const END = STEPS.length;

function placeRect(place) {
  const el = place === 'device' ? document.querySelector('.device-pane')
    : place === 'phone' ? document.querySelector('.stage-phone')
      : document.querySelector('.demo-strip .tour-ring') || document.querySelector('.demo-strip');
  return el?.getBoundingClientRect() || null;
}

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

// Where the card goes and where its arrow points. Wide: beside the pane it is about (over the other
// pane), or under the demo strip. Docked (stacked panes, phones): at the bottom, the arrow up or down.
function placeCard(card, place, docked) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = card.offsetWidth;
  const h = card.offsetHeight;
  const target = place ? placeRect(place) : null;
  if (docked) {
    const top = vh - h - 12;
    if (!target) return { top, arrow: null };
    const centerY = target.top + target.height / 2;
    const arrow = centerY < top ? 'up' : 'down';
    return { top, arrow, offset: clamp(target.left + target.width / 2 - GAP, 28, w - 28) };
  }
  // The end card: low and centred, clear of the device's words.
  if (!target) return { left: (vw - w) / 2, top: vh - h - 24, arrow: null };
  if (place === 'strip') {
    const left = clamp(target.left + target.width / 2 - w / 2, GAP, vw - w - GAP);
    return { left, top: target.bottom + 14, arrow: 'up', offset: clamp(target.left + target.width / 2 - left, 24, w - 24) };
  }
  const other = placeRect(place === 'device' ? 'phone' : 'device');
  const top = clamp((other?.bottom ?? vh) - h - 36, 60, vh - h - GAP);
  const offset = clamp(target.top + target.height / 2 - top, 28, h - 28);
  if (place === 'device') {
    const left = other ? other.left + (other.width - w) / 2 : target.right + GAP;
    return { left, top, arrow: 'left', offset };
  }
  const left = other ? other.right - w - 24 : target.left - w - GAP;
  return { left, top, arrow: 'right', offset };
}

// The guided tour on "Watch the loop" (demo only): a card on the stage with seven steps of the loop.
// Each step names the elements to ring (data-tour) on the stage and, over the stage channel, in the
// panes; a pane draws its own ring. A step moves on by itself when its event happens (channel
// messages, or polling the device invitation and My questions), or with Next.
// notice: the phone's answer notification (StageView); onExplore opens the person picker.
export default function GuidedTour({ notice, centerId, askerId, onExplore }) {
  const { closeTour, startTour, openCreateFamily } = useApp();
  const [step, setStep] = useState(0);
  const [lightOn, setLightOn] = useState(false);
  const [pos, setPos] = useState(null);
  const cardRef = useRef(null);
  const docked = useMediaQuery('(max-width: 1100px)');

  const next = useCallback(() => setStep(s => Math.min(s + 1, END)), []);

  // Step 5 ends when the phone shows the answer notification.
  if (step === 4 && notice) setStep(5);

  // What ends each step; the light (step 7) decides between "Next morning" and Talk.
  useEffect(() => {
    if (step >= END) return undefined;
    let cancelled = false;
    let clockMoved = false;
    let startedOff = null;
    const done = () => {
      if (cancelled) return;
      cancelled = true;
      setStep(s => (s === step ? s + 1 : s));
    };
    const checkLight = async () => {
      const inv = await apiClient.getDeviceInvitation(centerId).catch(() => null);
      if (cancelled || !inv) return;
      const on = Boolean(inv.active);
      setLightOn(on);
      if (startedOff === null) startedOff = !on;
      // A light already on when the step began only counts after the clock moved.
      if (step === 1 && on && (startedOff || clockMoved)) done();
    };
    const checkQuestion = async () => {
      const questions = await apiClient.getMyQuestions(askerId).catch(() => null);
      if ((questions || []).some(q => q.status === 'waiting')) done();
    };
    const poll = () => {
      if (!centerId || !askerId) return;
      if (step === 0) checkQuestion();
      if (step === 1 || step === 6) checkLight();
    };
    poll();
    const timer = setInterval(poll, POLL_MS);
    const stopChanges = listenForChanges(reason => {
      if (reason === 'clock') clockMoved = true;
      if ((step === 0 && reason === 'question') || (step === 3 && reason === 'session_end') || (step === 5 && reason === 'reaction')) {
        done();
      } else {
        poll();
      }
    });
    // Talk (steps 3 and 7) is done once the session's opening has been heard.
    const stopTour = listenForTour(m => {
      if (m.kind === 'event' && m.name === 'opening_played' && (step === 2 || step === 6)) done();
    });
    return () => { cancelled = true; clearInterval(timer); stopChanges(); stopTour(); };
  }, [step, centerId, askerId]);

  const current = step < END ? (step === 6 && !lightOn ? { ...STEPS[6], ...NEXT_MORNING, hint: 'Press Next morning, then Talk.', dockedHint: 'Open Demo at the top, press Next morning, then Talk.' } : STEPS[step]) : null;
  const hint = (docked && current?.dockedHint) || current?.hint;
  const targets = current?.targets || [];
  const place = current?.place || null;
  const key = targets.join(' ');

  // Tell the panes what to ring, again whenever a pane (re)loads; nothing once the tour closes.
  useEffect(() => {
    const names = key ? key.split(' ') : [];
    sendTour({ kind: 'targets', targets: names });
    return listenForTour(m => { if (m.kind === 'hello') sendTour({ kind: 'targets', targets: names }); });
  }, [key]);
  useEffect(() => () => sendTour({ kind: 'targets', targets: [] }), []);
  useTourRings(targets);

  // Keep the card next to what it is about as the page moves.
  useLayoutEffect(() => {
    const update = () => {
      if (!cardRef.current) return;
      const next = placeCard(cardRef.current, place, docked);
      setPos(prev => (prev && ['left', 'top', 'arrow', 'offset'].every(k => prev[k] === next[k]) ? prev : next));
    };
    update();
    const timer = setInterval(update, PLACE_MS);
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      clearInterval(timer);
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [place, docked, step]);

  // Docked, the page scrolls: bring what the step is about into view (a pane then centres its ring).
  useEffect(() => {
    if (!docked || !place) return;
    if (place === 'strip') window.scrollTo({ top: 0, behavior: 'smooth' });
    else document.querySelector(place === 'device' ? '.device-pane' : '.phone-pane')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, [docked, place, step]);

  // The card takes focus once, when the tour opens; Esc closes it.
  useEffect(() => {
    cardRef.current?.focus({ preventScroll: true });
    const onKey = (e) => { if (e.key === 'Escape') closeTour(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [closeTour]);

  const style = pos ? {
    top: `${pos.top}px`,
    ...(docked ? {} : { left: `${pos.left}px` }),
    '--arrow-offset': pos.offset != null ? `${pos.offset}px` : undefined
  } : { visibility: 'hidden' };
  const className = `tour-card ${docked ? 'docked' : ''} ${pos?.arrow ? `arrow-${pos.arrow}` : ''} ${current ? '' : 'end'}`;

  return (
    <div
      ref={cardRef}
      className={className}
      style={style}
      role="dialog"
      aria-modal="false"
      aria-labelledby="tour-card-step"
      aria-describedby="tour-card-text"
      tabIndex={-1}
      data-step={current ? step + 1 : 'end'}
    >
      <div className="tour-card-head">
        <span id="tour-card-step" className="tour-card-step">
          {current ? `Guide · step ${step + 1} of ${END}` : 'Guide · done'}
        </span>
        <button type="button" className="tour-card-close" onClick={closeTour} aria-label="Close the guide">
          <X size={16} />
        </button>
      </div>
      <div aria-live="polite">
        {current ? <>
          <p id="tour-card-text" className="tour-card-text">{current.text}</p>
          {hint && <p className="tour-card-hint">{hint}</p>}
        </> : (
          <p id="tour-card-text" className="tour-card-text">
            That is the loop: a question, her voice, a reaction, the next conversation.
          </p>
        )}
      </div>
      <div className="tour-card-actions">
        {current ? (
          <button type="button" className="tour-btn primary" onClick={next}>Next</button>
        ) : <>
          <button type="button" className="tour-btn primary" onClick={() => { closeTour(); onExplore(); }}>
            Explore as a family member
          </button>
          <button type="button" className="tour-btn" onClick={() => { closeTour(); openCreateFamily?.(); }}>
            Create your family
          </button>
          <button type="button" className="tour-btn quiet" onClick={startTour}>Start again</button>
        </>}
      </div>
    </div>
  );
}
