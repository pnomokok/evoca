import { useEffect, useSyncExternalStore } from 'react';
import { apiClient } from '../api/client';
import { listenForTour, sendTour } from './stageChannel';
import '../styles/tour.css';

// The guided tour on "Watch the loop" (components/GuidedTour.jsx): its suggested question and the
// sample answers that belong to it (scripts/make_demo_audio.py, Fatma's voice).
export const SUGGESTED_QUESTION = 'Grandma, what games did you play when you were little?';
export const SAMPLE_ANSWERS = ['/demo-audio/answer_1.mp3', '/demo-audio/answer_2.mp3', '/demo-audio/goodbye.mp3'];

const normalize = (text) => (text || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();

export function isSuggestedQuestion(text) {
  return normalize(text) === normalize(SUGGESTED_QUESTION);
}

// --- In a stage pane: the targets the stage asked this pane for, from the channel ---

const noTargets = [];
let paneTargets = noTargets;
let paneKey = '';
const subscribers = new Set();
let stopListening = null;

function subscribe(onChange) {
  subscribers.add(onChange);
  if (!stopListening) {
    stopListening = listenForTour(message => {
      if (message.kind !== 'targets') return;
      const mine = message.pane === apiClient.embed?.kind && Array.isArray(message.targets);
      paneTargets = mine ? message.targets : noTargets;
      paneKey = mine ? message.key || '' : '';
      subscribers.forEach(fn => fn());
    });
    sendTour({ kind: 'hello' });
  }
  return () => {
    subscribers.delete(onChange);
    if (subscribers.size === 0 && stopListening) {
      stopListening();
      stopListening = null;
    }
  };
}

const ignore = () => () => {};

// The data-tour names the stage wants shown in this pane; always empty outside a stage pane.
export function usePaneTourTargets() {
  return useSyncExternalStore(
    apiClient.embed ? subscribe : ignore,
    () => (apiClient.embed ? paneTargets : noTargets)
  );
}

function usePaneTourKey() {
  return useSyncExternalStore(apiClient.embed ? subscribe : ignore, () => paneKey);
}

export function paneTourWants(name) {
  return Boolean(apiClient.embed) && paneTargets.includes(name);
}

// --- Finding and measuring a target in this document ---

const visible = (el) => el.getClientRects().length > 0;

// The visible elements with data-tour equal to the first of names that has any.
export function findTourTargets(names) {
  for (const name of names) {
    const found = [...document.querySelectorAll(`[data-tour="${name}"]`)].filter(visible);
    if (found.length) return found;
  }
  return [];
}

// Nothing covers the element: the topmost element at its centre is the element itself or inside it
// (a fixed bar over it, or a centre outside the viewport, fails).
export function isUncovered(el) {
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2;
  const y = r.top + r.height / 2;
  if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) return false;
  const hit = document.elementFromPoint(x, y);
  return Boolean(hit) && (hit === el || el.contains(hit));
}

// The union of the elements' boxes in this document's viewport, rounded; null for none.
export function unionRect(elements) {
  if (!elements.length) return null;
  const boxes = elements.map(el => el.getBoundingClientRect());
  const left = Math.min(...boxes.map(b => b.left));
  const top = Math.min(...boxes.map(b => b.top));
  const right = Math.max(...boxes.map(b => b.right));
  const bottom = Math.max(...boxes.map(b => b.bottom));
  return { left: Math.round(left), top: Math.round(top), width: Math.round(right - left), height: Math.round(bottom - top) };
}

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

// In a stage pane: finds the target the stage asked for, scrolls it into view (centred, clear of the
// fixed bars by its scroll margin) when it appears, and sends its box to the stage with whether
// nothing covers it, again whenever it moves (resize, scroll, layout changes). The stage draws the
// spotlight and places the card only for a visible target.
export function usePaneTourTarget() {
  const targets = usePaneTourTargets();
  const key = usePaneTourKey();
  useEffect(() => {
    if (!apiClient.embed || !key) return undefined;
    const pane = apiClient.embed.kind;
    let current = [];
    let lastSent = '';
    const scrolled = new WeakSet();   // elements already scrolled into view once
    let frame = 0;
    const resize = typeof ResizeObserver === 'function' ? new ResizeObserver(() => schedule()) : null;
    const measure = () => {
      frame = 0;
      const found = findTourTargets(targets);
      const fresh = found.filter(el => !current.includes(el));
      current.filter(el => !found.includes(el)).forEach(el => { el.classList.remove('tour-target'); resize?.unobserve(el); });
      fresh.forEach(el => { el.classList.add('tour-target'); resize?.observe(el); });
      current = found;
      const rect = unionRect(found);
      const visible = found.length > 0 && found.every(isUncovered);
      // Not visible (new, re-rendered, or behind a bar): scroll it into view, once per element.
      if (found.length && !visible && !scrolled.has(found[0])) {
        found.forEach(el => scrolled.add(el));
        // Several elements (play and reactions): from the top of the group when it fits, else centred.
        const fits = rect.height < window.innerHeight - 140;
        found[0].scrollIntoView({ block: found.length > 1 && fits ? 'start' : 'center', inline: 'nearest', behavior: reducedMotion() ? 'auto' : 'smooth' });
      }
      const message = JSON.stringify([rect, visible]);
      if (message !== lastSent) {
        lastSent = message;
        sendTour({ kind: 'rect', pane, key, rect, visible });
      }
    };
    function schedule() {
      if (!frame) frame = requestAnimationFrame(measure);
    }
    measure();
    const observer = new MutationObserver(schedule);
    // Only data-tour and structure: the target's own class change must not measure again.
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-tour', 'disabled'] });
    window.addEventListener('resize', schedule);
    window.addEventListener('scroll', schedule, true);
    // The stage (re)loaded or lost track: send the box again.
    const stopHello = listenForTour(m => { if (m.kind === 'measure') { lastSent = ''; schedule(); } });
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      resize?.disconnect();
      window.removeEventListener('resize', schedule);
      window.removeEventListener('scroll', schedule, true);
      stopHello();
      current.forEach(el => el.classList.remove('tour-target'));
      sendTour({ kind: 'rect', pane, key, rect: null, visible: false });
    };
  }, [key, targets]);
}
