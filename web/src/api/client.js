import {
  initialCircle,
  initialDeviceInvitation,
  initialDeviceTurn,
  initialFeed,
  initialLifeline,
  initialStoryMulberry,
  initialFeaturedStory,
  initialStoryMulberryPlaylist,
  SENSITIVE_TOPIC_KEYWORDS
} from './mockData';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

class EvocaApiClient {
  constructor() {
    this.useMock = localStorage.getItem('evoca_use_mock') !== 'false';
    this.currentViewerId = localStorage.getItem('evoca_viewer_id') || 'person_elif';

    // In-memory mock store
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
    localStorage.setItem('evoca_viewer_id', personId);
    const member = this.circle.members.find(m => m.id === personId);
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

  getHeaders(customHeaders = {}) {
    return {
      'X-Person-Id': this.currentViewerId,
      ...customHeaders
    };
  }

  // --- API Endpoints ---

  async getCircle() {
    if (this.useMock) {
      return { ...this.circle };
    }
    const res = await fetch(`${API_BASE_URL}/api/circle`, { headers: this.getHeaders() });
    return res.json();
  }

  async getDeviceInvitation() {
    if (this.useMock) {
      return { ...this.invitation };
    }
    const res = await fetch(`${API_BASE_URL}/api/device/invitation`, { headers: this.getHeaders() });
    return res.json();
  }

  async postDeviceTurn(audioBlob, textPrompt = null, sessionId = 'session_demo1') {
    if (this.useMock) {
      // Simulate speech-to-text response
      await new Promise(r => setTimeout(r, 800));
      const turn = {
        ...initialDeviceTurn,
        session_id: sessionId,
        heard_text: textPrompt || "I was thinking about the old days...",
        reply_text: textPrompt?.toLowerCase().includes("school") 
          ? "You were talking about school! You told us about the snowy path to the village schoolhouse."
          : initialDeviceTurn.reply_text
      };
      this.deviceTurns.push(turn);
      return turn;
    }

    const formData = new FormData();
    if (audioBlob) formData.append('audio', audioBlob);
    if (sessionId) formData.append('session_id', sessionId);
    if (textPrompt) formData.append('text', textPrompt);

    const res = await fetch(`${API_BASE_URL}/api/device/turn`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: formData
    });
    return res.json();
  }

  async postDeviceSessionEnd(sessionId = 'session_demo1') {
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
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ session_id: sessionId })
    });
    return res.json();
  }

  async getFeed() {
    if (this.useMock) {
      return { ...this.feed };
    }
    const res = await fetch(`${API_BASE_URL}/api/feed`, { headers: this.getHeaders() });
    return res.json();
  }

  async getLifeline(personId = 'person_fatma') {
    if (this.useMock) {
      return { ...this.lifeline };
    }
    const res = await fetch(`${API_BASE_URL}/api/lifeline/${personId}`, { headers: this.getHeaders() });
    return res.json();
  }

  async getFeaturedStory() {
    if (this.useMock) {
      return { ...this.featuredStory };
    }
    return { ...this.featuredStory };
  }

  async getStory(storyId = 'story_mulberry') {
    if (this.useMock) {
      return { ...this.story };
    }
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}`, { headers: this.getHeaders() });
    return res.json();
  }

  async getStoryPlaylist(storyId = 'story_mulberry') {
    if (this.useMock) {
      return { ...this.playlist };
    }
    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/playlist`, { headers: this.getHeaders() });
    return res.json();
  }

  async postQuestion(targetPersonId, text, period = null) {
    if (this.useMock) {
      await new Promise(r => setTimeout(r, 600));
      // Check for sensitive topics simulation
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

      // Add to device turn preview for demo continuity
      this.invitation.active = true;
      this.invitation.invitation.reason = `${this.circle.me.name.split(' ')[0]} has a question for you.`;

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
    return res.json();
  }

  async postRecording(audioBlob) {
    if (this.useMock) {
      await new Promise(r => setTimeout(r, 700));
      return {
        session_id: `session_${Date.now()}`,
        started_by: "panel_recording",
        processing: "started"
      };
    }

    const formData = new FormData();
    formData.append('audio', audioBlob);

    const res = await fetch(`${API_BASE_URL}/api/recordings`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: formData
    });
    return res.json();
  }

  async postStoryReaction(storyId, emoji, action = 'add') {
    if (this.useMock) {
      const reactions = this.story.reactions;
      if (action === 'add') {
        if (!reactions.mine.includes(emoji)) {
          reactions.mine.push(emoji);
          reactions.counts[emoji] = (reactions.counts[emoji] || 0) + 1;
        }
      } else {
        reactions.mine = reactions.mine.filter(e => e !== emoji);
        reactions.counts[emoji] = Math.max(0, (reactions.counts[emoji] || 1) - 1);
      }
      return {
        story_id: storyId,
        counts: reactions.counts,
        mine: reactions.mine
      };
    }

    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/reactions`, {
      method: 'POST',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ emoji, action })
    });
    return res.json();
  }

  async patchStorySubject(storyId, personId, period) {
    if (this.useMock) {
      // Update local lifeline & story
      const subject = this.story.subjects.find(s => s.person_id === personId);
      if (subject) {
        subject.period = period;
        subject.period_source = "family";
        subject.corrected_by = this.currentViewerId;
      }
      return { status: "ok", story: this.story };
    }

    const res = await fetch(`${API_BASE_URL}/api/stories/${storyId}/subjects/${personId}`, {
      method: 'PATCH',
      headers: this.getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ period })
    });
    return res.json();
  }

  async deleteLink(linkId) {
    if (this.useMock) {
      this.story.linked_stories = this.story.linked_stories.filter(l => l.link_id !== linkId);
      return { status: "ok" };
    }

    const res = await fetch(`${API_BASE_URL}/api/links/${linkId}`, {
      method: 'DELETE',
      headers: this.getHeaders()
    });
    return res.json();
  }
}

export const apiClient = new EvocaApiClient();
