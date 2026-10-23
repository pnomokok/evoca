import { useCallback, useSyncExternalStore } from 'react';
import { apiClient } from '../api/client';

// "Show MCP calls" on the stage (demo strip): whether the device pane shows its MCP calls panel.
// Kept in local storage; the stage and its device pane are separate documents, so a change reaches
// this document by an event and the others by the browser's storage event.
const CHANGED = 'evoca-mcp-calls';
const KEY = 'evoca_show_mcp_calls';

function subscribe(onChange) {
  const onStorage = (e) => { if (e.key === KEY || e.key === null) onChange(); };
  window.addEventListener(CHANGED, onChange);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(CHANGED, onChange);
    window.removeEventListener('storage', onStorage);
  };
}

const read = () => apiClient.showMcpCalls;

export function useShowMcpCalls() {
  const on = useSyncExternalStore(subscribe, read);
  const setOn = useCallback((value) => {
    apiClient.setShowMcpCalls(value);
    window.dispatchEvent(new Event(CHANGED));
  }, []);
  return [on, setOn];
}
