// After a page change, scroll to an element of the new page and mark it for a moment
// (the page renders on the next frames, so this waits up to about a second for it, or `frames`).
// block: where it lands ('center', or 'start' to sit below the top bar by its scroll margin).
// fallbackId: scrolled to instead when the element never appears.
export function focusLater(elementId, { focusId = null, block = 'center', frames = 60, fallbackId = null } = {}) {
  let tries = 0;
  const step = () => {
    const el = document.getElementById(elementId);
    if (!el) {
      if (++tries < frames) requestAnimationFrame(step);
      else if (fallbackId) focusLater(fallbackId, { focusId });
      return;
    }
    el.scrollIntoView({ behavior: 'smooth', block });
    el.classList.add('focus-flash');
    setTimeout(() => el.classList.remove('focus-flash'), 2200);
    if (focusId) document.getElementById(focusId)?.focus({ preventScroll: true });
  };
  requestAnimationFrame(step);
}
