import React from 'react';

// Warm, muted colours that hold white initials; one is picked from the person id.
const COLOURS = ['#A95F46', '#68775B', '#8C5A3C', '#8A6E4B', '#5E6F7A', '#7D5A6E'];

function initialsOf(name) {
  const words = (name || '').trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : '';
  return `${first}${last}`.toUpperCase();
}

function colourFor(id) {
  let hash = 0;
  for (const ch of String(id || '')) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return COLOURS[Math.abs(hash) % COLOURS.length];
}

// Initials only: there are no person photos in the data model, and none are ever made up.
export default function Avatar({ person, size = 32, className = '', ring = false }) {
  const style = {
    width: size,
    height: size,
    fontSize: Math.round(size * 0.38),
    background: colourFor(person?.id || person?.name)
  };
  return (
    <span className={`initials-avatar ${ring ? 'ring' : ''} ${className}`} style={style} aria-hidden="true">
      {initialsOf(person?.name)}
    </span>
  );
}
