import React, { useEffect, useState } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import { Trash2, Plus, Clock } from 'lucide-react';
import { formatWhen } from '../../utils/format';
import MembersSection from './MembersSection';

// Family settings for the circle's admin (/api/admin/*): sensitive topics and the chat time.
// FamilyPanel shows it only when me.role is "admin"; everyone else would get a 403.
export default function FamilySettings() {
  const { circleData, currentViewerId, showToast, refreshData } = useApp();
  const [loaded, setLoaded] = useState({ viewerId: null, topics: [], failed: false });
  const [newTopic, setNewTopic] = useState('');
  const [topicError, setTopicError] = useState(null);
  const [busy, setBusy] = useState(false);
  const savedChatTime = circleData?.circle?.chat_time || '';
  const [chatTime, setChatTime] = useState(savedChatTime);
  const [chatTimeError, setChatTimeError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    apiClient.getSensitiveTopics()
      .then(topics => { if (!cancelled) setLoaded({ viewerId: currentViewerId, topics: topics || [], failed: false }); })
      .catch(err => {
        console.error('Could not load the sensitive topics:', err);
        if (!cancelled) setLoaded({ viewerId: currentViewerId, topics: [], failed: true });
      });
    return () => { cancelled = true; };
  }, [currentViewerId]);

  const topics = loaded.viewerId === currentViewerId ? loaded.topics : [];
  const memberName = (id) => circleData?.members?.find(m => m.id === id)?.name || '';

  const handleAddTopic = async (e) => {
    e.preventDefault();
    const text = newTopic.trim();
    if (!text) return;
    setBusy(true);
    setTopicError(null);
    try {
      const topic = await apiClient.postSensitiveTopic(text);
      setLoaded(prev => ({
        ...prev,
        topics: prev.topics.some(t => t.id === topic.id) ? prev.topics : [...prev.topics, topic]
      }));
      setNewTopic('');
      showToast('Evoca will not bring this topic up.', 'info');
    } catch (err) {
      setTopicError(err.status === 400 ? err.message : "The topic couldn't be added.");
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteTopic = async (topicId) => {
    setBusy(true);
    try {
      await apiClient.deleteSensitiveTopic(topicId);
      setLoaded(prev => ({ ...prev, topics: prev.topics.filter(t => t.id !== topicId) }));
      showToast('The topic is removed.', 'info');
    } catch (err) {
      console.error(err);
      showToast("The topic couldn't be removed.", 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveChatTime = async (e) => {
    e.preventDefault();
    if (!chatTime) return;
    setBusy(true);
    setChatTimeError(null);
    try {
      const res = await apiClient.patchAdminCircle({ chat_time: chatTime });
      setChatTime(res.chat_time || chatTime);
      showToast(`The morning chat is now at ${res.chat_time || chatTime}.`, 'info');
      if (refreshData) refreshData();
    } catch (err) {
      setChatTimeError(err.status === 400 ? err.message : "The chat time couldn't be changed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="lifeline-archive-page family-settings-page">
      <header className="section-header-editorial">
        <span className="section-eyebrow">Admin</span>
        <h1 className="section-title-serif">Family settings</h1>
        <p className="section-desc">Only you, as the family's admin, can see this page.</p>
      </header>

      <MembersSection />

      <section className="side-archival-card" aria-labelledby="topics-heading" style={{ marginBottom: '24px' }}>
        <h2 id="topics-heading" className="side-card-heading">Topics Evoca never brings up</h2>
        <p className="section-desc">
          Questions that touch these topics are not sent. Evoca never mentions them in a conversation.
        </p>

        {loaded.failed && <p role="alert">Not available.</p>}
        {!loaded.failed && topics.length === 0 && <p className="section-desc">No topics yet.</p>}
        <ul className="settings-topic-list" style={{ listStyle: 'none', padding: 0 }}>
          {topics.map(t => (
            <li key={t.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '8px 0' }}>
              <div>
                <strong>{t.text}</strong>
                <div className="section-desc">
                  {[memberName(t.added_by) && `Added by ${memberName(t.added_by)}`, formatWhen(t.created_at)].filter(Boolean).join(' · ')}
                </div>
              </div>
              <button
                type="button"
                className="editorial-btn secondary"
                onClick={() => handleDeleteTopic(t.id)}
                disabled={busy}
                aria-label={`Remove the topic ${t.text}`}
              >
                <Trash2 size={14} />
                <span>Remove</span>
              </button>
            </li>
          ))}
        </ul>

        <form onSubmit={handleAddTopic} className="archival-form">
          <label className="form-label" htmlFor="new-topic">Add a topic</label>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <input
              id="new-topic"
              className="archival-input-select"
              value={newTopic}
              onChange={(e) => { setNewTopic(e.target.value); setTopicError(null); }}
              placeholder="For example: Uncle Selim's debt"
              maxLength={200}
            />
            <button type="submit" className="editorial-btn primary" disabled={busy || !newTopic.trim()}>
              <Plus size={14} />
              <span>Add</span>
            </button>
          </div>
          {topicError && <p role="alert" className="section-desc">{topicError}</p>}
        </form>
      </section>

      <section className="side-archival-card" aria-labelledby="chat-time-heading">
        <h2 id="chat-time-heading" className="side-card-heading">Morning chat time</h2>
        <p className="section-desc">
          The Living Room Device lights up at this time ({circleData?.circle?.timezone || 'family time zone'}).
          A day that already has its invitation keeps it.
        </p>
        <form onSubmit={handleSaveChatTime} className="archival-form" style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="form-label" htmlFor="chat-time" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Clock size={14} /> Time
          </label>
          <input
            id="chat-time"
            type="time"
            className="archival-input-select"
            value={chatTime}
            onChange={(e) => { setChatTime(e.target.value); setChatTimeError(null); }}
            required
          />
          <button type="submit" className="editorial-btn primary" disabled={busy || !chatTime || chatTime === savedChatTime}>
            Save
          </button>
        </form>
        {chatTimeError && <p role="alert" className="section-desc">{chatTimeError}</p>}
      </section>
    </div>
  );
}
