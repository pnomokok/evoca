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
    this.currentViewerId = readStorage('evoca_viewer_id') || '';
    // Left behind by the removed sample-data mode.
    writeStorage('evoca_use_mock', null);
  }

  setViewer(personId) {
    this.currentViewerId = personId;
    writeStorage('evoca_viewer_id', personId || null);
  }

  getHeaders(customHeaders = {}, overridePersonId = null) {
    const personId = overridePersonId || this.currentViewerId;
    const headers = { ...customHeaders };
    if (personId) {
      headers['X-Person-Id'] = personId;
    }
    return headers;
  }

  // --- Audio and photos: fetch with X-Person-Id and hand back a blob URL ---
  // (a plain <audio src> or <img src> cannot send the header).
  async fetchBlobUrl(path, personId = null) {
    if (!path) return null;
    // The person header only ever goes to our own API.
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
  async getLifeline(personId) {
    const res = await fetch(`${API_BASE_URL}/api/lifeline/${personId}`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  // --- Story Page ---
  async getStory(storyId) {
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}`, { headers: this.getHeaders() });
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
  async getMyQuestions() {
    const res = await fetch(`${API_BASE_URL}/api/questions/mine`, { headers: this.getHeaders() });
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

  // --- Demo controls (only with EVOCA_DEMO_MODE=1; no person header) ---
  // null when the server is not in demo mode (404), so the controls stay hidden.
  async getDemoClock() {
    const res = await fetch(`${API_BASE_URL}/api/demo/clock`);
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
