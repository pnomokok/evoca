// "Watch the loop": the stage and its two panes tell each other when something changed
// (a question, a session end, a reaction, a clock change), and the panes load again.

const CHANNEL_NAME = 'evoca-stage';

function openChannel() {
  try {
    return typeof BroadcastChannel === 'function' ? new BroadcastChannel(CHANNEL_NAME) : null;
  } catch {
    return null;
  }
}

// reason: 'question' | 'session_end' | 'reaction' | 'clock' | 'reset'
export function announceChange(reason) {
  const channel = openChannel();
  if (!channel) return;
  channel.postMessage({ type: 'changed', reason });
  channel.close();
}

// Calls onChange(reason) for changes announced by the other panes (a channel never hears its own messages).
export function listenForChanges(onChange) {
  const channel = openChannel();
  if (!channel) return () => {};
  channel.onmessage = (e) => {
    if (e.data?.type === 'changed') onChange(e.data.reason);
  };
  return () => channel.close();
}
