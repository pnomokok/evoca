// A short, soft two-note chime made with Web Audio (no audio file): "I heard you, thinking now".

let context = null;

// Create or wake the audio context during a user gesture (pressing the talk button),
// so the chime may play later without an autoplay block.
export function primeChime() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    if (!context) context = new AudioContextClass();
    if (context.state === 'suspended') context.resume().catch(() => {});
  } catch {
    context = null;
  }
}

export function playChime() {
  primeChime();
  if (!context) return;
  const start = context.currentTime + 0.02;
  [[659.25, 0], [987.77, 0.14]].forEach(([frequency, offset]) => {
    const osc = context.createOscillator();
    const gain = context.createGain();
    osc.type = 'sine';
    osc.frequency.value = frequency;
    const t = start + offset;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.07, t + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.7);
    osc.connect(gain).connect(context.destination);
    osc.start(t);
    osc.stop(t + 0.75);
  });
}
