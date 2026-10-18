import { useEffect } from 'react';

// While open, a click outside ref's element or Escape calls onDismiss (menus and drop-down panels).
export function useDismiss(open, ref, onDismiss) {
  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (e) => { if (!ref.current?.contains(e.target)) onDismiss(); };
    const onKey = (e) => { if (e.key === 'Escape') onDismiss(); };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, ref, onDismiss]);
}
