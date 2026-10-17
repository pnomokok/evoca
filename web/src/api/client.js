import {
  initialCircle,
  initialDeviceInvitation,
  initialDeviceTurn,
  initialFeed,
  initialLifeline,
  initialStoryMulberry,
  initialFeaturedStory,
  initialStoryMulberryPlaylist,
  SENSITIVE_TOPIC_KEYWORDS,
  STORIES_DATABASE
} from './mockData';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

async function handleResponse(res) {
  if (res.ok) {
    if (res.status === 204) return null;
    return res.json();
  }

  let detail = '';
  try {
    const errJson = await res.json();
    detail = errJson?.detail || '';
  } catch {
    // Body is not JSON
  }

  if (res.status === 404) {
    throw new Error('Bu hikâye bulunamadı');
  }
  if (res.status === 403) {
    throw new Error('Bu içeriğe erişemiyorsun');
  }
  if (res.status === 400) {
    throw new Error(detail || 'Geçersiz istek');
  }
  throw new Error(detail || `İstek başarısız (${res.status})`);
}

class EvocaApiClient {
  constructor() {
    // Real mode is default; mock mode remains an option.
    this.useMock = localStorage.getItem('evoca_use_mock') === 'true';
    this.currentViewerId = localStorage.getItem('evoca_viewer_id') || '';

    // In-memory mock store for demo fallback
    this.circle = JSON.parse(JSON.stringify(initialCircle));
    this.invitation = JSON.parse(JSON.stringify(initialDeviceInvitation));
    this.feed = JSON.parse(JSON.stringify(initialFeed));
    this.lifeline = JSON.parse(JSON.stringify(initialLifeline));
    this.story = JSON.parse(JSON.stringify(initialStoryMulberry));
    this.featuredStory = JSON.parse(JSON.stringify(initialFeaturedStory));
    this.playlist = JSON.parse(JSON.stringify(initialStoryMulberryPlaylist));
    this.deviceTurns = [];
  }

  setViewer(personId) {
    this.currentViewerId = personId;
    if (personId) {
      localStorage.setItem('evoca_viewer_id', personId);
    } else {
      localStorage.removeItem('evoca_viewer_id');
    }
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
    this.useMock = flag;
    localStorage.setItem('evoca_use_mock', flag ? 'true' : 'false');
  }

  getHeaders(customHeaders = {}, overridePersonId = null) {
    const personId = overridePersonId || this.currentViewerId;
    const headers = { ...customHeaders };
    if (personId) {
      headers['X-Person-Id'] = personId;
    }
    return headers;
  }

  // --- Audio Fetch (fetch + blob URL with X-Person-Id header) ---
  async fetchAudioBlobUrl(audioPath, personId = null) {
    if (!audioPath) return null;
    if (this.useMock) {
      // In mock mode, if it's already an absolute or mock URL, return null to let speech synthesis fallback or return path
      return null;
    }
    const fullUrl = audioPath.startsWith('http') ? audioPath : `${API_BASE_URL}${audioPath}`;
    try {
      const res = await fetch(fullUrl, {
        headers: this.getHeaders({}, personId)
      });
      if (!res.ok) {
        if (res.status === 403) {
          const err = new Error('Bu içeriğe erişemiyorsun');
          err.status = 403;
          throw err;
        }
        throw new Error('Ses dosyası alınamadı');
      }
      const blob = await res.blob();
      return URL.createObjectURL(blob);
    } catch (err) {
      console.warn("fetchAudioBlobUrl error:", err);
      throw err;
    }
  }

  // --- People (Password-less Person Picker) ---
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
  async getCircle() {
    if (this.useMock) {
      return { ...this.circle };
    }
    const res = await fetch(`${API_BASE_URL}/api/circle`, { headers: this.getHeaders() });
    return handleResponse(res);
  }

  // --- Device Screen (Always operates as center person) ---
  async getDeviceInvitation(centerPersonId = null) {
    if (this.useMock) {
      return { ...this.invitation };
    }
    const res = await fetch(`${API_BASE_URL}/api/device/invitation`, {
      headers: this.getHeaders({}, centerPersonId)
    });
    return handleResponse(res);
  }

  async postDeviceSessionStart(centerPersonId = null) {
    if (this.useMock) {
      return {
        session_id: `session_mock_${Date.now()}`,
        session_open: true,
        heard_text: null,
        reply_text: "Günaydın Fatma Hanım! Elif dut ağacı anınıza çok gülmüş. Size sormak istediği güzel bir soru var: Gençliğinizde köyde kışlar nasıl geçerdi?",
        reply_audio_url: null,
        cards: [
          {
            type: "reaction",
            story_id: "story_mulberry",
            story_title: "The Mulberry Tree",
            from: { id: "person_elif", name: "Elif Yilmaz", relation_to_center: "granddaughter" },
            emoji: "laugh"
          },
          {
            type: "question",
            question_id: "question_school",
            text: "Köyde kışlar nasıl geçerdi, okula nasıl giderdiniz?",
            asker: { id: "person_elif", name: "Elif Yilmaz", relation_to_center: "granddaughter" }
          }
        ]
      };
    }

    const res = await fetch(`${API_BASE_URL}/api/device/session/start`, {
      method: 'POST',
      headers: this.getHeaders({}, centerPersonId)
    });
    return handleResponse(res);
  }

  async postDeviceTurn(audioBlob, sessionId, centerPersonId = null) {
    if (this.useMock) {
      await new Promise(r => setTimeout(r, 600));
      return {
        session_id: sessionId || `session_mock_${Date.now()}`,
        session_open: true,
        heard_text: "Dut ağacına tırmanır, ellerimiz morarıncaya kadar yerdik...",
        reply_text: "Ne kadar güzel hatırlıyorsunuz! O ağaç hala Akçaabat'taki bahçede duruyor mu?",
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

  async getFeaturedStory() {
    if (this.useMock) {
      return { ...this.featuredStory };
    }
    return { ...this.featuredStory };
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
      this.invitation.invitation.reason = `${this.circle?.me?.name?.split(' ')[0] || 'Aile'} bir soru sordu.`;

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
