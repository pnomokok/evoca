import React, { useEffect, useRef, useState } from 'react';

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

// A dialog over the page: Escape and a click on the backdrop close it (onClose),
// focus moves into it when it opens, stays inside it, and goes back to the opener when it closes.
// The markup keeps the existing modal-overlay / modal-sheet classes.
export default function Modal({
  onClose,
  labelledBy,
  label,
  sheetClassName = 'modal-sheet archival-dialog',
  sheetStyle,
  closeOnBackdrop = true,
  children
}) {
  const sheetRef = useRef(null);
  // The opener is read on the first render: by the time effects run, an autoFocus
  // field inside the dialog already has the focus.
  const [opener] = useState(() => document.activeElement);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const sheet = sheetRef.current;
    // An element with autoFocus inside already has focus; otherwise the one marked data-autofocus
    // (it survives another dialog closing in the same render), else the first control.
    if (sheet && !sheet.contains(document.activeElement)) {
      const first = sheet.querySelector('[data-autofocus]') || sheet.querySelector(FOCUSABLE);
      (first || sheet).focus();
    }
    // Escape closes; Tab and Shift+Tab stay inside the dialog.
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current?.();
      } else if (e.key === 'Tab' && sheet) {
        const items = [...sheet.querySelectorAll(FOCUSABLE)].filter(el => !el.disabled);
        if (items.length === 0) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && (document.activeElement === first || !sheet.contains(document.activeElement))) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && (document.activeElement === last || !sheet.contains(document.activeElement))) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      if (opener && typeof opener.focus === 'function' && document.contains(opener)) opener.focus();
    };
  }, [opener]);

  return (
    <div
      className="modal-overlay"
      onClick={closeOnBackdrop ? () => onCloseRef.current?.() : undefined}
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      aria-label={labelledBy ? undefined : label}
    >
      <div ref={sheetRef} className={sheetClassName} style={sheetStyle} tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}
