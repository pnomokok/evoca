// After a page change, scroll to an element of the new page and mark it for a moment
// (the page renders on the next frames, so this waits up to about a second for it).
export function focusLater(elementId, { focusId = null } = {}) {
  let tries = 0;
  const step = () => {
    const el = document.getElementById(elementId);
    if (!el) {
      if (++tries < 60) requestAnimationFrame(step);
      return;
    }
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('focus-flash');
    setTimeout(() => el.classList.remove('focus-flash'), 2200);
    if (focusId) document.getElementById(focusId)?.focus({ preventScroll: true });
  };
  requestAnimationFrame(step);
}
