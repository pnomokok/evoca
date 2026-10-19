import React from 'react';

// A photo's caption with who added it ("Fatma in the village garden, around 1956 — Ayşe"):
// the caption is the uploader's words, so the panel says whose.
export default function PhotoCaption({ caption, addedBy }) {
  if (!caption) return null;
  return (
    <>
      <span>{caption}</span>
      {addedBy && <span className="photo-caption-by"> — {addedBy}</span>}
    </>
  );
}
