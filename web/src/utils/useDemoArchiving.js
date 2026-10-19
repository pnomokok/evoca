import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { listenForChanges } from './stageChannel';

const STATUS_REFRESH_MS = 3_000;

// Demo only: whether the demo family's archivist is still writing up a story (GET /api/demo/status).
// Moving the clock meanwhile waits for it on the server.
export function useDemoArchiving(enabled = true) {
  const [archiving, setArchiving] = useState(false);

  const load = useCallback(() => apiClient.getDemoStatus().then(
    s => setArchiving(Boolean(s?.archiving)),
    () => setArchiving(false)
  ), []);

  useEffect(() => {
    if (!enabled) return undefined;
    const first = setTimeout(load, 0);
    const timer = setInterval(load, STATUS_REFRESH_MS);
    const stop = listenForChanges(load);    // a goodbye on the stage's device
    return () => { clearTimeout(first); clearInterval(timer); stop(); };
  }, [enabled, load]);

  return enabled && archiving;
}
