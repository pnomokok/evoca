import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import { listenForChanges } from '../../utils/stageChannel';

const NOTICE_MS = 6000;
const POLL_MS = 15000;

// Which of a person's answered questions this browser has already announced (ids only).
const seenKey = (circleId, personId) => `evoca_seen_answers_${circleId}_${personId}`;

function readSeen(key) {
  try {
    const ids = JSON.parse(localStorage.getItem(key) || 'null');
    return Array.isArray(ids) ? ids : null;
  } catch {
    return null;
  }
}

function writeSeen(key, ids) {
  try {
    localStorage.setItem(key, JSON.stringify(ids));
  } catch {
    // Storage may be blocked; an answer may then be announced again after a reload.
  }
}

// Watches personId's questions (GET /api/questions/mine) and returns a notice for an answer that
// appeared since the last look: { questionId, text }, shown for 6 s. It looks again on every stage
// change (session end, clock, reaction) and every 15 s. The first look only remembers what is
// already answered, so old answers are never announced.
export function useNewAnswers({ circleId, personId, enabled = true, reloadKey = 0 }) {
  const [notice, setNotice] = useState(null);
  const timer = useRef(null);

  const check = useCallback(async () => {
    if (!enabled || !circleId || !personId) return;
    let questions;
    try {
      questions = await apiClient.getMyQuestions(personId);
    } catch {
      return;
    }
    const answered = (questions || []).filter(q => q.status === 'answered' && q.answer_story_id);
    const key = seenKey(circleId, personId);
    const seen = readSeen(key);
    writeSeen(key, answered.map(q => q.id));
    if (seen === null) return;
    const fresh = answered.find(q => !seen.includes(q.id));
    if (!fresh) return;
    setNotice({ questionId: fresh.id, text: fresh.text });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setNotice(null), NOTICE_MS);
  }, [enabled, circleId, personId]);

  useEffect(() => {
    const first = setTimeout(check, 0);
    const stop = listenForChanges(reason => { if (reason !== 'reset') check(); });
    const poll = setInterval(check, POLL_MS);
    return () => { clearTimeout(first); stop(); clearInterval(poll); };
  }, [check, reloadKey]);

  useEffect(() => () => clearTimeout(timer.current), []);

  const dismiss = useCallback(() => { clearTimeout(timer.current); setNotice(null); }, []);
  return { notice, dismiss };
}
