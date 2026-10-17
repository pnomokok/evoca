import React, { useEffect, useRef, useState } from 'react';

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

// A dialog over the page: Escape and a click on the backdrop close it (onClose),
// focus moves into it when it opens and goes back to the opener when it closes.
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
    // An element with autoFocus inside already has focus; otherwise focus the first control.
    if (sheet && !sheet.contains(document.activeElement)) {
      const first = sheet.querySelector(FOCUSABLE);
      (first || sheet).focus();
    }
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current?.();
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
