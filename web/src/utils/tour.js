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

// --- In a stage pane: the targets the stage asked for, from the channel ---

let paneTargets = [];
const subscribers = new Set();
let stopListening = null;

function subscribe(onChange) {
  subscribers.add(onChange);
  if (!stopListening) {
    stopListening = listenForTour(message => {
      if (message.kind !== 'targets') return;
      paneTargets = Array.isArray(message.targets) ? message.targets : [];
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

const noTargets = [];
const ignore = () => () => {};

// The data-tour names the stage wants ringed; always empty outside a stage pane.
export function usePaneTourTargets() {
  return useSyncExternalStore(
    apiClient.embed ? subscribe : ignore,
    () => (apiClient.embed ? paneTargets : noTargets)
  );
}

export function paneTourWants(name) {
  return Boolean(apiClient.embed) && paneTargets.includes(name);
}

// --- The ring itself, in this document ---

const visible = (el) => el.getClientRects().length > 0;

// Puts a soft pulsing ring on the visible elements with data-tour equal to the first of targets
// that has any, and keeps it right as the page changes. A newly ringed element is scrolled into view.
export function useTourRings(targets) {
  const key = targets.join(' ');
  useEffect(() => {
    if (!key) return undefined;
    const names = key.split(' ');
    let ringed = [];
    const apply = () => {
      let found = [];
      for (const name of names) {
        found = [...document.querySelectorAll(`[data-tour="${name}"]`)].filter(visible);
        if (found.length) break;
      }
      ringed.filter(el => !found.includes(el)).forEach(el => el.classList.remove('tour-ring'));
      const fresh = found.filter(el => !ringed.includes(el));
      found.forEach(el => el.classList.add('tour-ring'));
      fresh[0]?.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
      ringed = found;
    };
    apply();
    const observer = new MutationObserver(apply);
    // Only data-tour: the ring's own class change must not call apply again.
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-tour'] });
    return () => {
      observer.disconnect();
      ringed.forEach(el => el.classList.remove('tour-ring'));
    };
  }, [key]);
}
