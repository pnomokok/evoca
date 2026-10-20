import React, { useEffect, useRef, useState } from 'react';
import PhotoCaption from './PhotoCaption';
import { useApp } from '../../context/useApp';
import { useAudioElement } from '../../utils/useAudioElement';
import { apiClient } from '../../api/client';
import { announceChange } from '../../utils/stageChannel';
import { formatDuration, formatWhen } from '../../utils/format';
import Avatar from '../Avatar';
import BlobPhoto from './BlobPhoto';
import { Loader2, Pause, Play } from 'lucide-react';
import '../../styles/journal.css';

const REACTIONS = [
  { key: 'heart', emoji: '❤️', label: 'Love it' },
  { key: 'laugh', emoji: '😂', label: 'Made me laugh' },
  { key: 'sad', emoji: '😢', label: 'Moved me' },
  { key: 'pray', emoji: '🙏', label: 'Grateful' }
];

// An answer to the viewer's question (a "question_answered" feed item): the story's photo if it has one,
// otherwise the designed card; then her voice, "Maybe give her a call.", the reactions (never counts)
// and a link to the whole story. tourMark: the guided tour may ring its play button and reactions.
// The play button shows at once: loading while the audio is fetched, then play.
export default function AnswerCard({ id, item, showQuestion = true, tourMark = false }) {
  const { showToast, circleData, openStory } = useApp();
  const a = item.answer;
  const [story, setStory] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [posMs, setPosMs] = useState(0);
  const getPlayer = useAudioElement();
  // Every piece of the answer, fetched as blobs and played back to back as one recording.
  const audioRef = useRef({ urls: [], durations: [], index: 0 });
  const [audioState, setAudioState] = useState('loading');   // loading | ready | error
  const playWhenReady = useRef(false);

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
  const piecesKey = pieces.map(p => p.url).join('|');

  // Fetch the audio as soon as the card shows, so the button can say when it is ready.
  useEffect(() => {
    if (!piecesKey) return undefined;
    let cancelled = false;
    const list = a.audio?.length ? a.audio : [{ url: a.audio_url, start_ms: a.start_ms, end_ms: a.end_ms }];
    setAudioState('loading');
    Promise.all(list.map(p => apiClient.fetchBlobUrl(p.url)))
      .then(urls => {
        if (urls.some(u => !u)) throw new Error('missing audio');
        if (cancelled) { urls.forEach(u => URL.revokeObjectURL(u)); return; }
        audioRef.current.urls.forEach(u => URL.revokeObjectURL(u));
        audioRef.current = { urls, durations: list.map(p => Math.max(0, (p.end_ms ?? 0) - (p.start_ms ?? 0))), index: 0 };
        setAudioState('ready');
      })
      .catch(err => {
        if (cancelled) return;
        console.warn('Answer audio not available:', err);
        setAudioState('error');
      });
    return () => { cancelled = true; };
  }, [piecesKey]);
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

  const startPlaying = () => playPiece(0).then(() => setPlaying(true)).catch(err => console.warn(err));

  // Pressed while loading: play as soon as the audio is in.
  useEffect(() => {
    if (audioState === 'ready' && playWhenReady.current) {
      playWhenReady.current = false;
      startPlaying();
    }
  }, [audioState]);

  const togglePlay = () => {
    if (audioState === 'loading') { playWhenReady.current = true; return; }
    if (audioState === 'error') { showToast('This recording is not available.', 'error'); return; }
    const player = getPlayer();
    if (!player.paused) {
      player.pause();
      setPlaying(false);
    } else if (player.ended || posMs === 0) {
      startPlaying();
    } else {
      player.play().then(() => setPlaying(true)).catch(err => console.warn(err));
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
    <article id={id} className="answer-card" data-testid="answer-card">
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
        {a.photo_url && a.photo_caption && (
          <p className="answer-photo-caption"><PhotoCaption caption={a.photo_caption} addedBy={a.photo_added_by} /></p>
        )}

        {pieces.length > 0 && (
          <div className="answer-player">
            <button
              type="button"
              className="answer-play"
              onClick={togglePlay}
              aria-label={audioState === 'loading' ? 'Loading the answer' : playing ? 'Pause the answer' : 'Listen to the answer'}
              aria-busy={audioState === 'loading'}
              data-state={audioState}
              data-pieces={pieces.length}
              data-tour={tourMark ? 'answer-card' : undefined}
            >
              {audioState === 'loading'
                ? <Loader2 size={18} className="answer-play-spinner" />
                : playing ? <Pause size={18} /> : <Play size={18} style={{ marginLeft: 2 }} />}
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

        {/* Shown at once (the tour points at them); usable once the story page has loaded. */}
        <div className="answer-reactions" role="group" aria-label="React to this story" data-tour={tourMark ? 'answer-card' : undefined}>
          {REACTIONS.map(r => {
            const mine = story?.reactions?.mine?.includes(r.key);
            const present = story?.reactions?.present?.includes(r.key);
            return (
              <button
                key={r.key}
                type="button"
                className={`answer-reaction ${mine ? 'mine' : ''} ${present && !mine ? 'present' : ''}`}
                onClick={() => toggleReaction(r.key)}
                disabled={!story}
                aria-pressed={Boolean(mine)}
                title={mine ? 'Remove my reaction' : `React: ${r.label}`}
              >
                <span aria-hidden="true">{r.emoji}</span>
                <span className="sr-only">{r.label}</span>
              </button>
            );
          })}
        </div>

        {story && (
          <button type="button" className="editorial-btn quiet answer-open" onClick={() => openStory(a.story_id)}>
            Open the story →
          </button>
        )}

        {item.created_at && <p className="answer-when">{formatWhen(item.created_at)}</p>}
      </div>
    </article>
  );
}
