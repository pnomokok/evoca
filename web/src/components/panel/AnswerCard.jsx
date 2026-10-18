import React, { useEffect, useRef, useState } from 'react';
import { useApp } from '../../context/useApp';
import { useAudioElement } from '../../utils/useAudioElement';
import { apiClient } from '../../api/client';
import { announceChange } from '../../utils/stageChannel';
import { formatDuration, formatWhen } from '../../utils/format';
import Avatar from '../Avatar';
import BlobPhoto from './BlobPhoto';
import { Pause, Play } from 'lucide-react';
import '../../styles/journal.css';

const REACTIONS = [
  { key: 'heart', emoji: '❤️', label: 'Love it' },
  { key: 'laugh', emoji: '😂', label: 'Made me laugh' },
  { key: 'sad', emoji: '😢', label: 'Moved me' },
  { key: 'pray', emoji: '🙏', label: 'Grateful' }
];

// An answer to the viewer's question (a "question_answered" feed item): the story's photo if it has one,
// otherwise the designed card; then her voice, "Maybe give her a call." and the reactions (never counts).
export default function AnswerCard({ item, showQuestion = true }) {
  const { showToast, circleData } = useApp();
  const a = item.answer;
  const [story, setStory] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [posMs, setPosMs] = useState(0);
  const getPlayer = useAudioElement();
  // Every piece of the answer, fetched as blobs and played back to back as one recording.
  const audioRef = useRef({ urls: [], durations: [], index: 0 });

  // The story page gives the reactions (present, mine) and the AI summary.
  useEffect(() => {
    let cancelled = false;
    apiClient.getStory(a.story_id)
      .then(s => { if (!cancelled) setStory(s); })
      .catch(() => { if (!cancelled) setStory(null); });
    return () => { cancelled = true; };
  }, [a.story_id]);

  useEffect(() => {
    const state = audioRef;
    return () => {
      getPlayer().pause();
      state.current.urls.forEach(u => URL.revokeObjectURL(u));
    };
  }, [getPlayer]);

  // docs/api-samples/GET_feed.json; older cards only have audio_url.
  const pieces = a.audio?.length ? a.audio
    : a.audio_url ? [{ url: a.audio_url, start_ms: a.start_ms, end_ms: a.end_ms }] : [];
  const totalMs = a.duration_ms ?? pieces.reduce((sum, p) => sum + Math.max(0, p.end_ms - p.start_ms), 0);
  const duration = formatDuration(totalMs);
  const teller = circleData?.members?.find(m => m.id === a.teller?.id) || a.teller;
  const tellerFirst = teller?.name?.split(' ')[0] || '';

  const playPiece = (index) => {
    const state = audioRef.current;
    const player = getPlayer();
    state.index = index;
    player.src = state.urls[index];
    player.ontimeupdate = () => {
      const before = state.durations.slice(0, index).reduce((x, y) => x + y, 0);
      setPosMs(before + Math.round(player.currentTime * 1000));
    };
    player.onended = () => {
      if (index + 1 < state.urls.length) {
        playPiece(index + 1);
      } else {
        setPlaying(false);
        setPosMs(0);
      }
    };
    return player.play();
  };

  const togglePlay = async () => {
    const player = getPlayer();
    if (audioRef.current.urls.length) {
      if (!player.paused) {
        player.pause();
        setPlaying(false);
      } else if (player.ended || posMs === 0) {
        playPiece(0).then(() => setPlaying(true)).catch(err => console.warn(err));
      } else {
        player.play().then(() => setPlaying(true)).catch(err => console.warn(err));
      }
      return;
    }
    try {
      const urls = await Promise.all(pieces.map(p => apiClient.fetchBlobUrl(p.url)));
      if (urls.length === 0 || urls.some(u => !u)) throw new Error('missing audio');
      audioRef.current = { urls, durations: pieces.map(p => Math.max(0, (p.end_ms ?? 0) - (p.start_ms ?? 0))), index: 0 };
      await playPiece(0);
      setPlaying(true);
    } catch (err) {
      console.warn('Answer audio not available:', err);
      setPlaying(false);
      showToast('This recording is not available.', 'error');
    }
  };

  const toggleReaction = async (key) => {
    if (!story) return;
    const isMine = (story.reactions?.mine || []).includes(key);
    try {
      const res = await apiClient.postStoryReaction(story.id, key, isMine ? 'remove' : 'add');
      setStory(prev => ({ ...prev, reactions: { present: res.present || [], mine: res.mine || [] } }));
      announceChange('reaction');
    } catch (err) {
      console.error(err);
      showToast("Your reaction couldn't be saved.", 'error');
    }
  };

  const from = (
    <div className="answer-from">
      {teller && <Avatar person={teller} size={28} />}
      <span>{tellerFirst ? `${tellerFirst} answered you` : 'Your answer'}</span>
    </div>
  );

  return (
    <article className="answer-card" data-testid="answer-card">
      <div className="answer-hero">
        <BlobPhoto
          photoUrl={a.photo_url}
          alt={a.photo_caption || a.story_title}
          className="answer-hero-photo"
          fallbackNode={<div className="answer-hero-designed" aria-hidden="true"><span>❦</span></div>}
        />
        {from}
      </div>

      <div className="answer-body">
        {showQuestion && item.question?.text && (
          <p className="answer-asked">You asked: “{item.question.text}”</p>
        )}
        <h3 className="answer-title">{a.story_title}</h3>

        {pieces.length > 0 && (
          <div className="answer-player">
            <button
              type="button"
              className="answer-play"
              onClick={togglePlay}
              aria-label={playing ? 'Pause the answer' : 'Listen to the answer'}
              data-pieces={pieces.length}
            >
              {playing ? <Pause size={18} /> : <Play size={18} style={{ marginLeft: 2 }} />}
            </button>
            <div className="answer-progress" aria-hidden="true">
              <span style={{ width: totalMs ? `${Math.min(100, (posMs / totalMs) * 100)}%` : 0 }} />
            </div>
            <span className="answer-time">
              {posMs > 0 ? `${formatDuration(posMs) || '0:00'} / ${duration}` : duration}
            </span>
          </div>
        )}

        {story?.ai_summary && (
          <p className="answer-summary"><span className="card-period-tag">AI summary · </span>{story.ai_summary}</p>
        )}

        <p className="answer-call">Maybe give her a call.</p>

        {story && (
          <div className="answer-reactions" role="group" aria-label="React to this story">
            {REACTIONS.map(r => {
              const mine = story.reactions?.mine?.includes(r.key);
              const present = story.reactions?.present?.includes(r.key);
              return (
                <button
                  key={r.key}
                  type="button"
                  className={`answer-reaction ${mine ? 'mine' : ''} ${present && !mine ? 'present' : ''}`}
                  onClick={() => toggleReaction(r.key)}
                  aria-pressed={Boolean(mine)}
                  title={mine ? 'Remove my reaction' : `React: ${r.label}`}
                >
                  <span aria-hidden="true">{r.emoji}</span>
                  <span className="sr-only">{r.label}</span>
                </button>
              );
            })}
          </div>
        )}

        {item.created_at && <p className="answer-when">{formatWhen(item.created_at)}</p>}
      </div>
    </article>
  );
}
