const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

function readStorage(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Storage may be blocked (private window); the app still works without it.
  }
}

const SESSION_KEY = 'evoca_session';

// {session_token, person_id, circle_id} from an invite link or a new family, or null.
function readSession() {
  try {
    const value = JSON.parse(readStorage(SESSION_KEY) || 'null');
    return value?.session_token && value?.person_id ? value : null;
  } catch {
    return null;
  }
}

// A pane of the "Watch the loop" stage: ?embed=device|panel&person=<id>. Its demo identity comes
// from the URL only, so it never reads or writes the stored sign-in or picker choice.
function readEmbed() {
  try {
    const params = new URLSearchParams(window.location.search);
    const kind = params.get('embed');
    const person = params.get('person');
    return (kind === 'device' || kind === 'panel') && person ? { kind, person } : null;
  } catch {
    return null;
  }
}

function apiError(status, message) {
  const err = new Error(message);
  err.status = status;
  return err;
}

// Errors carry the HTTP status; components pick the wording for their context
// (a missing story says so, other 403/404 stay neutral).
async function handleResponse(res) {
  if (res.ok) {
    if (res.status === 204) return null;
    return res.json();
  }

  let detail = '';
  try {
    const errJson = await res.json();
    detail = typeof errJson?.detail === 'string' ? errJson.detail : '';
  } catch {
    // Body is not JSON
  }

  if (res.status === 403 || res.status === 404) {
    throw apiError(res.status, 'Not available');
  }
  if (res.status === 400) {
    throw apiError(400, detail || 'That did not work. Please check and try again.');
  }
  throw apiError(res.status, detail || 'Something went wrong. Please try again.');
}

class EvocaApiClient {
  constructor() {
    // Two identity modes: a stored sign-in session (bearer token), else the demo person picker.
    // A stage pane is always the demo person in its URL.
    this.embed = readEmbed();
    this.session = this.embed ? null : readSession();
    this.demoViewerId = this.embed ? this.embed.person : (readStorage('evoca_viewer_id') || '');
    // Left behind by the removed sample-data mode.
    writeStorage('evoca_use_mock', null);
  }

  get isSignedIn() {
    return Boolean(this.session);
  }

  // The person every request is made as: the session's person, or the demo picker's choice.
  get currentViewerId() {
    return this.session ? this.session.person_id : this.demoViewerId;
  }

  setSession(session) {
    this.session = session ? {
      session_token: session.session_token,
      person_id: session.person_id,
      circle_id: session.circle_id
    } : null;
    writeStorage(SESSION_KEY, this.session ? JSON.stringify(this.session) : null);
  }

  clearSession() {
    this.setSession(null);
  }

  // Demo picker only; a signed-in session fixes the person.
  setViewer(personId) {
    this.demoViewerId = personId;
    if (!this.embed) writeStorage('evoca_viewer_id', personId || null);
  }

  // True once someone has chosen a person in the picker (before that, it suggests the default member).
  get viewerChosen() {
    return readStorage('evoca_viewer_chosen') === '1';
  }

  markViewerChosen() {
    writeStorage('evoca_viewer_chosen', '1');
  }

  // The stage's guided tour starts by itself only on the first visit.
  get tourSeen() {
    return readStorage('evoca_tour_seen') === '1';
  }

  markTourSeen() {
    writeStorage('evoca_tour_seen', '1');
  }

  // The stage shows the device's MCP calls panel only when someone turned it on ("Show MCP calls").
  get showMcpCalls() {
    return readStorage('evoca_show_mcp_calls') === '1';
  }

  setShowMcpCalls(on) {
    writeStorage('evoca_show_mcp_calls', on ? '1' : null);
  }

  // Signed in: only the bearer token (the session fixes person and circle).
  // Demo: X-Person-Id, the given person (the device acts as the center) or the picked viewer.
  getHeaders(customHeaders = {}, overridePersonId = null) {
    const headers = { ...customHeaders };
    if (this.session) {
      headers.Authorization = `Bearer ${this.session.session_token}`;
      return headers;
    }
    const personId = overridePersonId || this.demoViewerId;
    if (personId) {
      headers['X-Person-Id'] = personId;
    }
    return headers;
  }

  // --- Audio and photos: fetch with the identity header and hand back a blob URL ---
  // (a plain <audio src> or <img src> cannot send the header).
  async fetchBlobUrl(path, personId = null) {
    if (!path) return null;
    // The identity header only ever goes to our own API.
    if (!path.startsWith('/') && !path.startsWith(`${API_BASE_URL}/`)) {
      throw apiError(400, 'Not available');
    }
    const fullUrl = path.startsWith('/') ? `${API_BASE_URL}${path}` : path;
    const res = await fetch(fullUrl, { headers: this.getHeaders({}, personId) });
    if (!res.ok) {
      throw apiError(res.status, 'Not available');
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  }

  // --- People (password-less person picker) ---
  async getPeople() {
    // The demo circle's people, kept in the older {id, name, circles} shape the picker uses.
    const circle = await handleResponse(await fetch(`${API_BASE_URL}/api/circles/demo`));
    const res = await fetch(`${API_BASE_URL}/api/people?circle_id=${encodeURIComponent(circle.id)}`);
    const people = (await handleResponse(res)) || [];
    return people.map(p => ({ id: p.id, name: p.name, circles: [{ circle_id: circle.id, role: p.role }] }));
  }

  // --- Circle & Identity ---
  // personId: ask as someone without making them the viewer (choosing the default viewer).
  async getCircle(personId = null) {
    const res = await fetch(`${API_BASE_URL}/api/circle`, { headers: this.getHeaders({}, personId) });
    return handleResponse(res);
  }

  // --- Device Screen (always operates as the center person, never as the panel viewer) ---
  requireCenter(centerPersonId) {
    if (!centerPersonId) throw apiError(400, 'Not available');
  }

  async getDeviceInvitation(centerPersonId = null) {
    this.requireCenter(centerPersonId);
    const res = await fetch(`${API_BASE_URL}/api/device/invitation`, {
      headers: this.getHeaders({}, centerPersonId)
    });
    return handleResponse(res);
  }

  async postDeviceSessionStart(centerPersonId = null) {
    this.requireCenter(centerPersonId);
    const res = await fetch(`${API_BASE_URL}/api/device/session/start`, {
      method: 'POST',
      headers: this.getHeaders({}, centerPersonId)
    });
    return handleResponse(res);
  }

  async postDeviceTurn(audioBlob, sessionId, centerPersonId = null) {
    this.requireCenter(centerPersonId);
    const formData = new FormData();
    formData.append('session_id', sessionId);
    if (audioBlob) {
      formData.append('audio', audioBlob, 'turn.webm');
    }

    const res = await fetch(`${API_BASE_URL}/api/device/turn`, {
      method: 'POST',
      headers: this.getHeaders({}, centerPersonId),
      body: formData
    });
    return handleResponse(res);
  }

  async postDeviceSessionEnd(sessionId, centerPersonId = null) {
    this.requireCenter(centerPersonId);
    const res = await fetch(`${API_BASE_URL}/api/device/session/end`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }, centerPersonId),
      body: JSON.stringify({ session_id: sessionId })
    });
    return handleResponse(res);
  }

  // Best effort while the page is going away: keepalive lets the request outlive the page.
  endDeviceSessionOnUnload(sessionId, centerPersonId = null) {
    if (!sessionId || !centerPersonId) return;
    try {
      fetch(`${API_BASE_URL}/api/device/session/end`, {
        method: 'POST',
        keepalive: true,
        headers: this.getHeaders({ 'Content-Type': 'application/json' }, centerPersonId),
        body: JSON.stringify({ session_id: sessionId })
      }).catch(() => {});
    } catch {
      // Nothing more can be done during unload.
    }
  }

  // --- Feed ---
  async getFeed() {
    const res = await fetch(`${API_BASE_URL}/api/feed`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  // --- Lifeline ---
  // asPersonId: ask as someone else in demo mode (the device asks as the center person).
  async getLifeline(personId, asPersonId = null) {
    const res = await fetch(`${API_BASE_URL}/api/lifeline/${personId}`, { headers: this.getHeaders({}, asPersonId) });
    return handleResponse(res);
  }

  // --- Story Page ---
  // asPersonId: as someone else in the demo (the stage's tour checks the phone person's reactions).
  async getStory(storyId, asPersonId = null) {
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}`, { headers: this.getHeaders({}, asPersonId) });
    return handleResponse(res);
  }

  async getStoryPlaylist(storyId) {
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/playlist`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  // --- Reactions ({ present, mine }, NO counts) ---
  async postStoryReaction(storyId, emoji, action = 'add') {
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/reactions`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ emoji, action })
    });
    return handleResponse(res);
  }

  // --- Story Subject Period Correction ---
  async patchStorySubject(storyId, personId, period) {
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/subjects/${personId}`, {
      method: 'PATCH',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ period })
    });
    return handleResponse(res);
  }

  // --- Story Access & Hide ---
  async patchStory(storyId, { access, hidden }) {
    const body = {};
    if (access !== undefined) body.access = access;
    if (hidden !== undefined) body.hidden = hidden;

    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}`, {
      method: 'PATCH',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body)
    });
    return handleResponse(res);
  }

  // --- Delete Wrong Link ---
  async deleteLink(linkId) {
    const res = await fetch(`${API_BASE_URL}/api/links/${linkId}`, {
      method: 'DELETE',
      headers: this.getHeaders()
    });
    return handleResponse(res);
  }

  // --- Ask Question ---
  async postQuestion(targetPersonId, text, period = null) {
    const res = await fetch(`${API_BASE_URL}/api/questions`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ target_person_id: targetPersonId, text, period })
    });
    return handleResponse(res);
  }

  // The viewer's own questions: status is only "waiting" or "answered" (with answer_story_id).
  // personId: as someone else in the demo (the stage watches the phone's person); ignored signed in.
  async getMyQuestions(personId = null) {
    const res = await fetch(`${API_BASE_URL}/api/questions/mine`, { headers: this.getHeaders({}, personId) });
    return handleResponse(res);
  }

  // --- Story photo (POST /api/stories/{id}/photo: multipart image + caption?) ---
  async postStoryPhoto(storyId, imageFile, caption = '') {
    const formData = new FormData();
    formData.append('image', imageFile, imageFile.name || 'photo.jpg');
    if (caption && caption.trim()) formData.append('caption', caption.trim());
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/photo`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: formData
    });
    return handleResponse(res);
  }

  // --- Family settings (admin only: /api/admin/*) ---
  async getSensitiveTopics() {
    const res = await fetch(`${API_BASE_URL}/api/admin/sensitive-topics`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  async postSensitiveTopic(text) {
    const res = await fetch(`${API_BASE_URL}/api/admin/sensitive-topics`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ text })
    });
    return handleResponse(res);
  }

  async deleteSensitiveTopic(topicId) {
    const res = await fetch(`${API_BASE_URL}/api/admin/sensitive-topics/${topicId}`, {
      method: 'DELETE',
      headers: this.getHeaders()
    });
    return handleResponse(res);
  }

  async patchAdminCircle({ chat_time, timezone }) {
    const body = {};
    if (chat_time !== undefined) body.chat_time = chat_time;
    if (timezone !== undefined) body.timezone = timezone;
    const res = await fetch(`${API_BASE_URL}/api/admin/circle`, {
      method: 'PATCH',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body)
    });
    return handleResponse(res);
  }

  // --- Record Memory (POST /api/recordings) ---
  async postRecording(audioBlob, access = 'circle') {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('access', access);

    const res = await fetch(`${API_BASE_URL}/api/recordings`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: formData
    });
    return handleResponse(res);
  }

  // --- A new family (POST /api/circles, no identity): returns the creator's session and link ---
  async createCircle(body) {
    const res = await fetch(`${API_BASE_URL}/api/circles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return handleResponse(res);
  }

  // --- Invite links (no identity): who the link is for, then a sign-in session ---
  async getInvite(token) {
    const res = await fetch(`${API_BASE_URL}/api/invites/${encodeURIComponent(token)}`);
    return handleResponse(res);
  }

  async acceptInvite(token) {
    const res = await fetch(`${API_BASE_URL}/api/invites/${encodeURIComponent(token)}/accept`, { method: 'POST' });
    return handleResponse(res);
  }

  // Ends the stored session on the server (bearer only), then forgets it here even if that failed.
  async logout() {
    if (!this.session) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/logout`, { method: 'POST', headers: this.getHeaders() });
      await handleResponse(res);
    } finally {
      this.clearSession();
    }
  }

  // --- Members and their invite links (admin only: /api/admin/*) ---
  async addMember({ name, birth_year, relation_to_center, role }) {
    const res = await fetch(`${API_BASE_URL}/api/admin/members`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ name, birth_year, relation_to_center, role })
    });
    return handleResponse(res);
  }

  async patchMember(personId, changes) {
    const res = await fetch(`${API_BASE_URL}/api/admin/members/${personId}`, {
      method: 'PATCH',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(changes)
    });
    return handleResponse(res);
  }

  async removeMember(personId) {
    const res = await fetch(`${API_BASE_URL}/api/admin/members/${personId}`, {
      method: 'DELETE',
      headers: this.getHeaders()
    });
    return handleResponse(res);
  }

  // A personal link for any member (the center included); revokes their old link and its devices.
  async createInvite(personId) {
    const res = await fetch(`${API_BASE_URL}/api/admin/invites`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ person_id: personId })
    });
    return handleResponse(res);
  }

  // --- Demo controls (only with EVOCA_DEMO_MODE=1; no person header) ---
  // null when the server is not in demo mode (404), so the controls stay hidden.
  async getDemoClock() {
    const res = await fetch(`${API_BASE_URL}/api/demo/clock`);
    if (res.status === 404) return null;
    return handleResponse(res);
  }

  // {archiving}: whether the demo family's archivist is still writing up a story.
  async getDemoStatus() {
    const res = await fetch(`${API_BASE_URL}/api/demo/status`);
    if (res.status === 404) return null;
    return handleResponse(res);
  }

  async postDemoAdvance(hours) {
    const res = await fetch(`${API_BASE_URL}/api/demo/advance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hours })
    });
    return handleResponse(res);
  }

  // Rebuilds the demo database; person ids change, so the caller picks the viewer again.
  async postDemoReset() {
    const res = await fetch(`${API_BASE_URL}/api/demo/reset`, { method: 'POST' });
    return handleResponse(res);
  }
}

export const apiClient = new EvocaApiClient();
