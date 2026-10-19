// Which members already have a personal link, as far as this browser knows: the API does not say,
// so the ids of links made here are remembered per circle (ids only, never a token).

const key = circleId => `evoca_links_${circleId}`;

export function linkedPersonIds(circleId) {
  if (!circleId) return [];
  try {
    const ids = JSON.parse(localStorage.getItem(key(circleId)) || '[]');
    return Array.isArray(ids) ? ids : [];
  } catch {
    return [];
  }
}

function save(circleId, ids) {
  try {
    localStorage.setItem(key(circleId), JSON.stringify(ids));
  } catch {
    // Storage may be blocked; the label then just says "Invite link" again.
  }
}

export function markLinked(circleId, personId) {
  if (!circleId || !personId) return;
  const ids = linkedPersonIds(circleId);
  if (!ids.includes(personId)) save(circleId, [...ids, personId]);
}

export function forgetLinked(circleId, personId) {
  if (!circleId) return;
  save(circleId, linkedPersonIds(circleId).filter(id => id !== personId));
}

// The full link to share: this site plus the API's invite_url_path ("/join/<token>").
export function fullInviteUrl(path) {
  return `${window.location.origin}${path}`;
}

// The journal's "Getting started" card, once dismissed, stays away for that circle in this browser.
const dismissedKey = circleId => `evoca_getting_started_dismissed_${circleId}`;

export function gettingStartedDismissed(circleId) {
  if (!circleId) return false;
  try {
    return localStorage.getItem(dismissedKey(circleId)) === '1';
  } catch {
    return false;
  }
}

export function dismissGettingStarted(circleId) {
  if (!circleId) return;
  try {
    localStorage.setItem(dismissedKey(circleId), '1');
  } catch {
    // Storage may be blocked; the card is then hidden until the page loads again.
  }
}
