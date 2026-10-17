import {
  initialCircle,
  initialDeviceInvitation,
  initialDeviceTurn,
  initialFeed,
  initialLifeline,
  initialStoryMulberry,
  initialStoryMulberryPlaylist,
  SENSITIVE_TOPIC_KEYWORDS,
  STORIES_DATABASE
} from './mockData';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

// Mock samples are a development aid only; a production build always talks to the backend.
const MOCK_ALLOWED = import.meta.env.DEV;

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
    this.useMock = MOCK_ALLOWED && readStorage('evoca_use_mock') === 'true';
    this.currentViewerId = readStorage('evoca_viewer_id') || '';

    // In-memory mock store for development
    this.circle = JSON.parse(JSON.stringify(initialCircle));
    this.invitation = JSON.parse(JSON.stringify(initialDeviceInvitation));
    this.feed = JSON.parse(JSON.stringify(initialFeed));
    this.lifeline = JSON.parse(JSON.stringify(initialLifeline));
    this.story = JSON.parse(JSON.stringify(initialStoryMulberry));
    this.playlist = JSON.parse(JSON.stringify(initialStoryMulberryPlaylist));
  }

  setViewer(personId) {
    this.currentViewerId = personId;
    writeStorage('evoca_viewer_id', personId || null);
    const member = this.circle?.members?.find(m => m.id === personId);
    if (member) {
      this.circle.me = {
        id: member.id,
        name: member.name,
        role: member.role,
        relation_to_center: member.relation_to_center
      };
    }
  }

  setUseMock(flag) {
    this.useMock = MOCK_ALLOWED && flag;
    writeStorage('evoca_use_mock', this.useMock ? 'true' : 'false');
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
    if (this.useMock) {
      // Mock samples have no audio or photo files.
      return null;
    }
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
    if (this.useMock) {
      return this.circle.members.map(m => ({
        id: m.id,
        name: m.name,
        circles: [{ circle_id: this.circle.circle.id, role: m.role }]
      }));
    }
    const res = await fetch(`${API_BASE_URL}/api/people`);
    return handleResponse(res);
  }

  // --- Circle & Identity ---
  // personId: ask as someone without making them the viewer (choosing the default viewer).
  async getCircle(personId = null) {
    if (this.useMock) {
      return { ...this.circle };
    }
    const res = await fetch(`${API_BASE_URL}/api/circle`, { headers: this.getHeaders({}, personId) });
    return handleResponse(res);
  }

  // --- Device Screen (always operates as the center person, never as the panel viewer) ---
  requireCenter(centerPersonId) {
    if (!this.useMock && !centerPersonId) throw apiError(400, 'Not available');
  }

  async getDeviceInvitation(centerPersonId = null) {
    this.requireCenter(centerPersonId);
    if (this.useMock) {
      return { ...this.invitation };
    }
    const res = await fetch(`${API_BASE_URL}/api/device/invitation`, {
      headers: this.getHeaders({}, centerPersonId)
    });
    return handleResponse(res);
  }

  async postDeviceSessionStart(centerPersonId = null) {
    this.requireCenter(centerPersonId);
    if (this.useMock) {
      return { ...JSON.parse(JSON.stringify(initialDeviceTurn)), session_id: `session_mock_${Date.now()}` };
    }

    const res = await fetch(`${API_BASE_URL}/api/device/session/start`, {
      method: 'POST',
      headers: this.getHeaders({}, centerPersonId)
    });
    return handleResponse(res);
  }

  async postDeviceTurn(audioBlob, sessionId, centerPersonId = null) {
    this.requireCenter(centerPersonId);
    if (this.useMock) {
      await new Promise(r => setTimeout(r, 600));
      return {
        session_id: sessionId || `session_mock_${Date.now()}`,
        session_open: true,
        heard_text: "We used to climb the mulberry tree and eat until our hands turned purple...",
        reply_text: "What a lovely memory! Is that tree still standing in the garden?",
        reply_audio_url: null,
        cards: []
      };
    }

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
    if (this.useMock) {
      this.invitation.active = false;
      return {
        session_id: sessionId,
        ended_at: new Date().toISOString(),
        processing: "started"
      };
    }
    const res = await fetch(`${API_BASE_URL}/api/device/session/end`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }, centerPersonId),
      body: JSON.stringify({ session_id: sessionId })
    });
    return handleResponse(res);
  }

  // Best effort while the page is going away: keepalive lets the request outlive the page.
  endDeviceSessionOnUnload(sessionId, centerPersonId = null) {
    if (this.useMock || !sessionId || !centerPersonId) return;
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
    if (this.useMock) {
      return { ...this.feed };
    }
    const res = await fetch(`${API_BASE_URL}/api/feed`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  // --- Lifeline ---
  async getLifeline(personId) {
    if (this.useMock) {
      return { ...this.lifeline };
    }
    const res = await fetch(`${API_BASE_URL}/api/lifeline/${personId}`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  // --- Story Page ---
  async getStory(storyId) {
    if (this.useMock) {
      if (storyId && STORIES_DATABASE[storyId]) {
        return JSON.parse(JSON.stringify(STORIES_DATABASE[storyId]));
      }
      return { ...this.story };
    }
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  async getStoryPlaylist(storyId) {
    if (this.useMock) {
      return { ...this.playlist };
    }
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/playlist`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  // --- Reactions ({ present, mine }, NO counts) ---
  async postStoryReaction(storyId, emoji, action = 'add') {
    if (this.useMock) {
      const reactions = this.story.reactions || { present: [], mine: [] };
      if (!Array.isArray(reactions.present)) reactions.present = [];
      if (!Array.isArray(reactions.mine)) reactions.mine = [];

      if (action === 'add') {
        if (!reactions.mine.includes(emoji)) reactions.mine.push(emoji);
        if (!reactions.present.includes(emoji)) reactions.present.push(emoji);
      } else {
        reactions.mine = reactions.mine.filter(e => e !== emoji);
        // present remains if another simulated person has it
      }
      return {
        story_id: storyId,
        present: reactions.present,
        mine: reactions.mine
      };
    }

    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/reactions`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ emoji, action })
    });
    return handleResponse(res);
  }

  // --- Story Subject Period Correction ---
  async patchStorySubject(storyId, personId, period) {
    if (this.useMock) {
      const subject = this.story?.subjects?.find(s => s.person_id === personId);
      if (subject) {
        subject.period = period;
        subject.period_source = "family";
        subject.estimated = false;
        subject.corrected_by = this.currentViewerId;
      }
      return { status: "ok", subject };
    }

    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/subjects/${personId}`, {
      method: 'PATCH',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ period })
    });
    return handleResponse(res);
  }

  // --- Story Access & Hide ---
  async patchStory(storyId, { access, hidden }) {
    if (this.useMock) {
      if (access !== undefined) {
        this.story.access = { type: access, person_ids: [] };
      }
      if (hidden !== undefined) {
        this.story.status = hidden ? 'hidden' : 'published';
      }
      return { id: storyId, status: this.story.status, access: this.story.access };
    }

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
    if (this.useMock) {
      this.story.linked_stories = (this.story.linked_stories || []).filter(l => l.link_id !== linkId);
      return { id: linkId, status: "removed" };
    }

    const res = await fetch(`${API_BASE_URL}/api/links/${linkId}`, {
      method: 'DELETE',
      headers: this.getHeaders()
    });
    return handleResponse(res);
  }

  // --- Ask Question ---
  async postQuestion(targetPersonId, text, period = null) {
    if (this.useMock) {
      await new Promise(r => setTimeout(r, 400));
      const lower = text.toLowerCase();
      const isSensitive = SENSITIVE_TOPIC_KEYWORDS.some(kw => lower.includes(kw));

      if (isSensitive) {
        return {
          status: "filtered",
          question: null,
          message: "This question touches a topic the family asked Evoca not to bring up. It was not sent."
        };
      }

      const newQuestion = {
        id: `question_${Date.now()}`,
        circle_id: this.circle.circle.id,
        target_person_id: targetPersonId,
        asker_id: this.currentViewerId,
        text,
        source: "family",
        period,
        status: "waiting",
        answer: null,
        created_at: new Date().toISOString()
      };

      this.invitation.active = true;
      this.invitation.invitation.reason = `${this.circle?.me?.name?.split(' ')[0] || 'Your family'} has a question for you.`;

      return {
        status: "waiting",
        question: newQuestion
      };
    }

    const res = await fetch(`${API_BASE_URL}/api/questions`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ target_person_id: targetPersonId, text, period })
    });
    return handleResponse(res);
  }

  // --- Story photo (POST /api/stories/{id}/photo: multipart image + caption?) ---
  async postStoryPhoto(storyId, imageFile, caption = '') {
    if (this.useMock) {
      return { story_id: storyId, photo_url: null, photo_caption: caption || null };
    }
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
    if (this.useMock) return [];
    const res = await fetch(`${API_BASE_URL}/api/admin/sensitive-topics`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  async postSensitiveTopic(text) {
    if (this.useMock) {
      return { id: `topic_${Date.now()}`, text, added_by: this.currentViewerId, created_at: new Date().toISOString() };
    }
    const res = await fetch(`${API_BASE_URL}/api/admin/sensitive-topics`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ text })
    });
    return handleResponse(res);
  }

  async deleteSensitiveTopic(topicId) {
    if (this.useMock) return { id: topicId, deleted: true };
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
    if (this.useMock) {
      Object.assign(this.circle.circle, body);
      return { id: this.circle.circle.id, chat_time: this.circle.circle.chat_time, timezone: this.circle.circle.timezone };
    }
    const res = await fetch(`${API_BASE_URL}/api/admin/circle`, {
      method: 'PATCH',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body)
    });
    return handleResponse(res);
  }

  // --- Record Memory (POST /api/recordings) ---
  async postRecording(audioBlob, access = 'circle') {
    if (this.useMock) {
      await new Promise(r => setTimeout(r, 600));
      return {
        session_id: `session_mock_rec_${Date.now()}`,
        started_by: "panel_recording",
        processing: "started"
      };
    }

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
}

export const apiClient = new EvocaApiClient();
