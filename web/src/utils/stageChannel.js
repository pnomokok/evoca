// "Watch the loop": the stage and its two panes tell each other when something changed
// (a question, a session end, a reaction, a clock change), and the panes load again.
// The guided tour (components/GuidedTour.jsx) talks on the same channel with its own messages.

const CHANNEL_NAME = 'evoca-stage';

function openChannel() {
  try {
    return typeof BroadcastChannel === 'function' ? new BroadcastChannel(CHANNEL_NAME) : null;
  } catch {
    return null;
  }
}

function post(message) {
  const channel = openChannel();
  if (!channel) return;
  channel.postMessage(message);
  channel.close();
}

function listen(type, onMessage) {
  const channel = openChannel();
  if (!channel) return () => {};
  channel.onmessage = (e) => {
    if (e.data?.type === type) onMessage(e.data);
  };
  return () => channel.close();
}

// reason: 'question' | 'session_end' | 'reaction' | 'clock' | 'reset'
export function announceChange(reason) {
  post({ type: 'changed', reason });
}

// Calls onChange(reason) for changes announced by the other panes (a channel never hears its own messages).
export function listenForChanges(onChange) {
  return listen('changed', data => onChange(data.reason));
}

// The tour's messages:
//   { kind: 'targets', byPane, key } from the stage: the step's data-tour names, per pane;
//   { kind: 'rect', pane, key, rects, visible } from a pane: one box per target, in its own viewport;
//   { kind: 'hello' } from a pane that just loaded, so the stage sends its targets again;
//   { kind: 'event', name } from the device: 'session_start' | 'opening_played' | 'session_open' |
//     'session_closed' | 'question_asked' | 'turn_sent'; { kind: 'ask-session' } and { kind: 'goodbye' }
//     from the stage.
export function sendTour(message) {
  post({ ...message, type: 'tour' });
}

export function listenForTour(onMessage) {
  return listen('tour', onMessage);
}
