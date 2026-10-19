import React, { useState, useEffect, useRef } from 'react';
import PhotoCaption from './PhotoCaption';
import { useApp } from '../../context/useApp';
import { useAudioElement } from '../../utils/useAudioElement';
import { apiClient } from '../../api/client';
import {
  Play,
  Pause,
  RotateCcw,
  Sparkles,
  ArrowLeft,
  Heart,
  MessageSquare,
  Headphones,
  ChevronRight,
  EyeOff,
  Lock,
  Users,
  AlertTriangle,
  X,
  Edit3,
  ImagePlus
} from 'lucide-react';
import { PERIOD_LABELS, periodLabel } from '../../utils/periods';
import { formatDuration } from '../../utils/format';
import BlobPhoto from './BlobPhoto';
import AddPhotoModal from './AddPhotoModal';
import Modal from '../Modal';
import { announceChange } from '../../utils/stageChannel';
import { punctuateWords } from '../../utils/transcript';
import { BACK_LABELS, BACK_SHORT, JOURNAL } from '../../utils/routes';

const REACTIONS = [
  { key: 'heart', emoji: '❤️', label: 'Love it' },
  { key: 'laugh', emoji: '😂', label: 'Made me laugh' },
  { key: 'sad', emoji: '😢', label: 'Moved me' },
  { key: 'pray', emoji: '🙏', label: 'Grateful' }
];

// Lay audio pieces end to end: each piece gets its offset in the continuous getPlayer().
function buildTimeline(ranges) {
  let offset = 0;
  return (ranges || []).map(r => {
    const duration = Math.max(0, (r.end_ms ?? 0) - (r.start_ms ?? 0));
    const piece = { ...r, duration, offset };
    offset += duration;
    return piece;
  });
}

function findPiece(pieces, startMs, endMs, hint) {
  const fits = p => p.start_ms <= startMs && endMs <= p.end_ms;
  for (let i = hint; i < pieces.length; i++) if (fits(pieces[i])) return i;
  for (let i = 0; i < hint; i++) if (fits(pieces[i])) return i;
  return -1;
}

// Word times are session times; turn them into player times
// (word.start_ms - piece.start_ms + offset of that piece).
function mapTranscript(transcript, pieces) {
  let hint = 0;
  return (transcript || []).map(seg => {
    const words = (seg.words || []).map(w => {
      const idx = findPiece(pieces, w.start_ms, w.end_ms, hint);
      if (idx < 0) return { ...w, playStart: null, playEnd: null };
      hint = idx;
      const p = pieces[idx];
      return {
        ...w,
        playStart: w.start_ms - p.start_ms + p.offset,
        playEnd: w.end_ms - p.start_ms + p.offset
      };
    });
    return { ...seg, words: punctuateWords(words, seg.text) };
  });
}

async function fetchQueue(ranges, viewerId) {
  const pieces = buildTimeline(ranges);
  const blobUrls = await Promise.all(pieces.map(p => apiClient.fetchBlobUrl(p.url, viewerId)));
  return pieces.map((p, i) => ({ ...p, blobUrl: blobUrls[i] }));
}

function revokeQueue(queue) {
  (queue || []).forEach(p => p.blobUrl?.startsWith('blob:') && URL.revokeObjectURL(p.blobUrl));
}

export default function StoryView() {
  const {
    selectedStoryId,
    storyBack,
    openStory,
    closeStory,
    navigate,
    currentViewerId,
    viewerReady,
    showToast,
    refreshData,
    circleData,
    dataVersion
  } = useApp();

  // Everything loaded for one story; `loading` is derived from data.storyId.
  const [data, setData] = useState({ storyId: null, viewerId: null, story: null, playlist: null, queue: [], audioDisabled: true, error: null });
  const story = data.story;
  const setStory = (updater) => setData(prev => ({ ...prev, story: typeof updater === 'function' ? updater(prev.story) : updater }));

  const [showPlaylist, setShowPlaylist] = useState(true);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentMs, setCurrentMs] = useState(0);
  const [mode, setMode] = useState('story'); // 'story' | 'playlist'
  const [playlistIndex, setPlaylistIndex] = useState(-1);

  const [showHideConfirm, setShowHideConfirm] = useState(false);
  const [isHiding, setIsHiding] = useState(false);
  const [showPeriodEditor, setShowPeriodEditor] = useState(false);
  const [selectedPeriod, setSelectedPeriod] = useState('');
  const [showPhotoModal, setShowPhotoModal] = useState(false);

  const getPlayer = useAudioElement();
  // What the single <audio> element is playing: a queue of pieces and the current index.
  const engineRef = useRef({ mode: 'story', queue: [], index: 0, loaded: false, playlistQueue: null });

  // Load story, playlist and every audio piece (fetched with X-Person-Id)
  useEffect(() => {
    if (!viewerReady || !selectedStoryId) return;
    let cancelled = false;
    let createdQueue = null;
    const engine = engineRef.current;

    async function loadStoryData() {
      let storyData;
      let playlistData = null;
      try {
        [storyData, playlistData] = await Promise.all([
          apiClient.getStory(selectedStoryId),
          apiClient.getStoryPlaylist(selectedStoryId).catch(() => null)
        ]);
      } catch (err) {
        console.error('Failed to load story:', err);
        if (!cancelled) {
          setData({
            storyId: selectedStoryId, viewerId: currentViewerId, story: null, playlist: null, queue: [], audioDisabled: true,
            error: err.status === 404 ? 'This story could not be found.' : 'Not available.'
          });
        }
        return;
      }

      let queue = buildTimeline(storyData?.audio);
      let audioDisabled = queue.length === 0;
      if (!audioDisabled) {
        try {
          queue = await fetchQueue(storyData.audio, currentViewerId);
          createdQueue = queue;
          audioDisabled = queue.some(p => !p.blobUrl);
        } catch (audioErr) {
          // Audio we may not hear: the play button is simply disabled, without a reason.
          console.warn('Audio not available:', audioErr);
          audioDisabled = true;
        }
      }
      if (cancelled) {
        revokeQueue(createdQueue);
        return;
      }
      Object.assign(engine, { mode: 'story', queue, index: 0, loaded: false });
      setData({ storyId: selectedStoryId, viewerId: currentViewerId, story: storyData, playlist: playlistData, queue, audioDisabled, error: null });
      setCurrentMs(0);
      setMode('story');
      setPlaylistIndex(-1);
    }

    loadStoryData();

    return () => {
      cancelled = true;
      getPlayer().pause();
      getPlayer().removeAttribute('src');
      engine.loaded = false;
      revokeQueue(createdQueue);
      revokeQueue(engine.playlistQueue);
      engine.playlistQueue = null;
    };
  }, [selectedStoryId, currentViewerId, viewerReady, getPlayer, dataVersion]);

  // Load piece `index` of `queue`, seek to `offsetMs` inside it, optionally play.
  const loadPiece = (queue, index, offsetMs, autoplay) => {
    const engine = engineRef.current;
    engine.queue = queue;
    engine.index = index;
    engine.loaded = true;
    getPlayer().src = queue[index].blobUrl;
    getPlayer().defaultPlaybackRate = playbackSpeed;
    getPlayer().playbackRate = playbackSpeed;
    getPlayer().addEventListener('loadedmetadata', () => {
      getPlayer().currentTime = Math.max(0, offsetMs) / 1000;
      if (autoplay) getPlayer().play().catch(e => console.warn('Audio play prevented:', e));
    }, { once: true });
  };

  // The event handler below needs the latest loadPiece (it reads playbackSpeed).
  const loadPieceRef = useRef(loadPiece);
  useEffect(() => {
    loadPieceRef.current = loadPiece;
  });

  // Player events: continue into the next piece, keep the player-time clock.
  useEffect(() => {
    const engine = engineRef.current;
    const handleTimeUpdate = () => {
      const piece = engine.queue[engine.index];
      if (piece) setCurrentMs(Math.round(piece.offset + getPlayer().currentTime * 1000));
    };
    const handleEnded = () => {
      if (engine.index + 1 < engine.queue.length) {
        loadPieceRef.current(engine.queue, engine.index + 1, 0, true);
        if (engine.mode === 'playlist') setPlaylistIndex(engine.index);
        return;
      }
      setIsPlaying(false);
      setCurrentMs(0);
      engine.loaded = false;
      if (engine.mode === 'playlist') {
        engine.mode = 'story';
        setMode('story');
        setPlaylistIndex(-1);
      }
    };
    const handlePause = () => setIsPlaying(false);
    const handlePlay = () => setIsPlaying(true);

    getPlayer().addEventListener('timeupdate', handleTimeUpdate);
    getPlayer().addEventListener('ended', handleEnded);
    getPlayer().addEventListener('pause', handlePause);
    getPlayer().addEventListener('play', handlePlay);
    return () => {
      getPlayer().removeEventListener('timeupdate', handleTimeUpdate);
      getPlayer().removeEventListener('ended', handleEnded);
      getPlayer().removeEventListener('pause', handlePause);
      getPlayer().removeEventListener('play', handlePlay);
    };
  }, [getPlayer]);

  const storyQueue = data.queue;
  const durationMs = storyQueue.reduce((sum, p) => sum + p.duration, 0);
  const audioDisabled = data.audioDisabled;

  const switchToStoryMode = () => {
    const engine = engineRef.current;
    if (engine.mode !== 'story') {
      engine.mode = 'story';
      engine.loaded = false;
      setMode('story');
      setPlaylistIndex(-1);
    }
  };

  // Seek in story (player) time; finds the piece that holds `ms`.
  const seekTo = (ms, autoplay) => {
    if (audioDisabled || storyQueue.length === 0) return;
    switchToStoryMode();
    const engine = engineRef.current;
    const target = Math.max(0, Math.min(ms, durationMs - 1));
    let index = storyQueue.findIndex(p => target >= p.offset && target < p.offset + p.duration);
    if (index < 0) index = storyQueue.length - 1;
    const inPiece = target - storyQueue[index].offset;
    setCurrentMs(target);
    if (!engine.loaded || engine.index !== index || engine.queue !== storyQueue) {
      loadPiece(storyQueue, index, inPiece, autoplay);
    } else {
      getPlayer().currentTime = inPiece / 1000;
      if (autoplay) getPlayer().play().catch(e => console.warn(e));
    }
  };

  const togglePlay = () => {
    if (isPlaying) {
      getPlayer().pause();
      return;
    }
    const engine = engineRef.current;
    if (engine.loaded) {
      getPlayer().play().catch(e => console.warn('Audio play prevented:', e));
    } else {
      seekTo(mode === 'story' ? currentMs : 0, true);
    }
  };

  const handleSpeedChange = () => {
    const nextSpeed = playbackSpeed === 1.0 ? 0.85 : playbackSpeed === 0.85 ? 1.15 : 1.0;
    setPlaybackSpeed(nextSpeed);
    getPlayer().defaultPlaybackRate = nextSpeed;
    getPlayer().playbackRate = nextSpeed;
  };

  // "Listen from the start": the playlist items, played back to back.
  const playPlaylistFrom = async (index) => {
    const items = data.playlist?.items || [];
    if (!items[index]) return;
    const engine = engineRef.current;
    try {
      if (!engine.playlistQueue) {
        engine.playlistQueue = await fetchQueue(items, currentViewerId);
      }
      const queue = engine.playlistQueue;
      if (queue.some(p => !p.blobUrl)) throw new Error('missing audio');
      engine.mode = 'playlist';
      setMode('playlist');
      setPlaylistIndex(index);
      setCurrentMs(queue[index].offset);
      loadPiece(queue, index, 0, true);
    } catch (err) {
      console.warn('Could not play the playlist:', err);
      showToast("This recording can't be played right now.", "error");
    }
  };

  // Reactions: present and mine, NO counts
  const handleToggleReaction = async (emojiKey) => {
    if (!story) return;
    const isMine = (story.reactions?.mine || []).includes(emojiKey);
    const action = isMine ? 'remove' : 'add';

    try {
      const res = await apiClient.postStoryReaction(story.id, emojiKey, action);
      setStory(prev => ({
        ...prev,
        reactions: { present: res.present || [], mine: res.mine || [] }
      }));
      announceChange('reaction');
    } catch (err) {
      console.error(err);
      showToast("Your reaction couldn't be saved.", 'error');
    }
  };

  // Change access: "circle" | "private"
  const handleChangeAccess = async (newAccess) => {
    try {
      await apiClient.patchStory(story.id, { access: newAccess });
      setStory(prev => ({ ...prev, access: { ...prev.access, type: newAccess } }));
      showToast(newAccess === 'private' ? 'Now only you can see this story.' : 'Now the whole family can see this story.', 'info');
    } catch (err) {
      console.error(err);
      showToast("Who can see this story couldn't be changed.", 'error');
    }
  };

  // Hide story: PATCH {"hidden": true}, then back to the journal
  const handleConfirmHide = async () => {
    setIsHiding(true);
    try {
      await apiClient.patchStory(story.id, { hidden: true });
      showToast('The story is hidden.', 'info');
      setShowHideConfirm(false);
      // The story is gone for everyone: the journal takes its place in the history.
      navigate(JOURNAL, { replace: true });
    } catch (err) {
      console.error(err);
      showToast("The story couldn't be hidden.", 'error');
    } finally {
      setIsHiding(false);
    }
  };

  // Wrong link: DELETE /api/links/{link_id}
  const handleDeleteLink = async (linkId) => {
    try {
      await apiClient.deleteLink(linkId);
      setStory(prev => ({
        ...prev,
        linked_stories: (prev.linked_stories || []).filter(l => l.link_id !== linkId)
      }));
      showToast('Thanks, that link is removed.', 'info');
    } catch (err) {
      console.error(err);
      showToast("The link couldn't be removed.", 'error');
    }
  };

  // Correct period: PATCH /api/stories/{id}/subjects/{person_id}
  const handleSavePeriod = async () => {
    const subject = story.subjects?.[0];
    if (!subject || !selectedPeriod) return;

    try {
      await apiClient.patchStorySubject(story.id, subject.person_id, selectedPeriod);
      setStory(prev => ({
        ...prev,
        subjects: (prev.subjects || []).map(s =>
          s.person_id === subject.person_id
            ? { ...s, period: selectedPeriod, period_source: 'family', estimated: false }
            : s
        )
      }));
      setShowPeriodEditor(false);
      showToast('Thanks! The chapter is updated.', 'info');
      if (refreshData) refreshData();
    } catch (err) {
      console.error(err);
      showToast("The chapter couldn't be changed.", 'error');
    }
  };

  if (!selectedStoryId) {
    return (
      <div className="story-loading-state" style={{ padding: '60px 20px', textAlign: 'center' }}>
        <p>Choose a story from the journal or the life chapters.</p>
      </div>
    );
  }

  // Still loading, or loaded for another viewer: show nothing of the old story.
  if (data.storyId !== selectedStoryId || data.viewerId !== currentViewerId) {
    return (
      <div className="story-loading-state" role="status">
        <div className="loading-spinner" />
        <p>Opening the story...</p>
      </div>
    );
  }

  if (data.error) {
    return (
      <div className="story-loading-state" style={{ padding: '60px 20px', textAlign: 'center' }} role="alert">
        <AlertTriangle size={36} color="var(--accent-terracotta)" style={{ marginBottom: '16px' }} />
        <h2 style={{ fontSize: '20px', marginBottom: '24px' }}>{data.error}</h2>
        <button className="editorial-btn primary" onClick={() => navigate(JOURNAL, { replace: true })}>
          <ArrowLeft size={16} /> Back to the journal
        </button>
      </div>
    );
  }

  if (!story) return null;

  const transcript = mapTranscript(story.transcript, buildTimeline(story.audio));
  const speakerIds = new Set(transcript.map(s => s.speaker?.id).filter(Boolean));
  const showSpeakers = speakerIds.size > 1;
  const primarySubject = story.subjects?.[0];
  // Whose life chapters this story is on: its subjects who are in the family (first names).
  const chapterPeople = [...new Set((story.subjects || [])
    .filter(s => circleData?.members?.some(m => m.id === s.person_id))
    .map(s => s.name?.split(' ')[0])
    .filter(Boolean))];
  const isEstimated = primarySubject?.estimated || primarySubject?.period_source === 'ai';
  const periodDisplay = periodLabel(primarySubject?.period) || 'Family archive';
  const tellerFirst = story.teller?.name?.split(' ')[0] || '';
  const playlistItems = data.playlist?.items || [];
  const storyMode = mode === 'story';
  // Anyone who sees the story may add a photo; replacing one is for the teller, a subject or an admin.
  const canReplacePhoto = Boolean(currentViewerId) && (
    story.teller?.id === currentViewerId
    || (story.subjects || []).some(s => s.person_id === currentViewerId)
    || circleData?.me?.role === 'admin'
  );
  const canAddPhoto = Boolean(currentViewerId) && (!story.photo_url || canReplacePhoto);

  return (
    <div className="story-archive-page">
      <nav className="story-breadcrumb-nav" aria-label="Story navigation">
        <div className="breadcrumb-left">
          <button type="button" className="btn-story-back" onClick={closeStory}>
            <ArrowLeft size={16} />
            <span className="back-long">{BACK_LABELS[storyBack] || BACK_LABELS.feed}</span>
            <span className="back-short" aria-hidden="true">{BACK_SHORT[storyBack] || BACK_SHORT.feed}</span>
          </button>
          <span className="breadcrumb-separator">/</span>
          <span className="breadcrumb-active-period">{periodDisplay}</span>
          {isEstimated && (
            <span className="meta-info-pill" style={{ marginLeft: '8px', fontSize: '11px', background: 'rgba(217, 119, 6, 0.15)', color: '#d97706', borderColor: 'rgba(217, 119, 6, 0.3)' }}>
              estimated
            </span>
          )}
        </div>

        <div className="breadcrumb-right">
          {story.can_change_access ? (
            <div className="access-select-wrapper" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label htmlFor="story-access-select" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Who can see it:
              </label>
              <select
                id="story-access-select"
                className="archival-select"
                value={story.access?.type || 'circle'}
                onChange={(e) => handleChangeAccess(e.target.value)}
                style={{ fontSize: '12px', padding: '4px 10px' }}
              >
                <option value="circle">Family circle</option>
                <option value="private">Only me</option>
              </select>
            </div>
          ) : (
            <span className="story-access-tag">
              {story.access?.type === 'private' ? <Lock size={14} /> : <Users size={14} />}
              <span>{story.access?.type === 'private' ? 'Only the teller' : 'Family circle'}</span>
            </span>
          )}

          {story.can_hide && (
            <button
              type="button"
              className="editorial-btn secondary"
              style={{ padding: '6px 12px', fontSize: '12px', borderColor: 'rgba(239, 68, 68, 0.4)', color: '#ef4444' }}
              onClick={() => setShowHideConfirm(true)}
              title="Hide this story"
            >
              <EyeOff size={14} />
              <span>Hide</span>
            </button>
          )}
        </div>
      </nav>

      {showHideConfirm && (
        <Modal onClose={() => !isHiding && setShowHideConfirm(false)} labelledBy="hide-dialog-title" sheetStyle={{ maxWidth: '440px' }}>
            <div className="modal-title-row">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444' }}>
                <AlertTriangle size={20} />
                <h3 id="hide-dialog-title" className="archival-dialog-title" style={{ margin: 0 }}>Hide this story?</h3>
              </div>
              <button className="close-btn" onClick={() => setShowHideConfirm(false)} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            <p style={{ fontSize: '14px', lineHeight: '1.6', margin: '16px 0', color: 'var(--text-secondary)' }}>
              The family will no longer see this story. <strong>This can't be undone.</strong>
            </p>
            <div className="dialog-action-bar">
              <button
                type="button"
                className="editorial-btn secondary"
                onClick={() => setShowHideConfirm(false)}
                disabled={isHiding}
              >
                Keep it
              </button>
              <button
                type="button"
                className="editorial-btn primary"
                style={{ backgroundColor: '#dc2626', borderColor: '#b91c1c', color: '#fff' }}
                onClick={handleConfirmHide}
                disabled={isHiding}
              >
                {isHiding ? "Hiding..." : "Yes, hide it"}
              </button>
            </div>
        </Modal>
      )}

      {showPeriodEditor && (
        <Modal onClose={() => setShowPeriodEditor(false)} labelledBy="period-dialog-title" sheetStyle={{ maxWidth: '440px' }}>
            <div className="modal-title-row">
              <h3 id="period-dialog-title" className="archival-dialog-title">Change the chapter</h3>
              <button className="close-btn" onClick={() => setShowPeriodEditor(false)} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '14px' }}>
              Which chapter of life does this story belong to?
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '20px' }}>
              {Object.entries(PERIOD_LABELS).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  className={`period-select-option ${selectedPeriod === k ? 'selected' : ''}`}
                  onClick={() => setSelectedPeriod(k)}
                  style={{ textAlign: 'left', padding: '10px 14px', borderRadius: '8px' }}
                >
                  <span className="opt-label">{label}</span>
                </button>
              ))}
            </div>
            <div className="dialog-action-bar">
              <button type="button" className="editorial-btn secondary" onClick={() => setShowPeriodEditor(false)}>
                Cancel
              </button>
              <button type="button" className="editorial-btn primary" onClick={handleSavePeriod} disabled={!selectedPeriod}>
                Save
              </button>
            </div>
        </Modal>
      )}

      {showPhotoModal && (
        <AddPhotoModal
          storyId={story.id}
          hasPhoto={Boolean(story.photo_url)}
          onClose={() => setShowPhotoModal(false)}
          onSaved={(res) => {
            setStory(prev => ({ ...prev, photo_url: res.photo_url, photo_caption: res.photo_caption, photo_added_by: res.photo_added_by }));
            setShowPhotoModal(false);
            showToast('The photo is added to the story.', 'info');
          }}
        />
      )}

      <header className="story-hero-header">
        <div className="story-header-eyebrow">
          <span>FAMILY STORY</span>
          <span className="eyebrow-sep">·</span>
          <span>{periodDisplay}</span>
          {isEstimated && (
            <>
              <span className="eyebrow-sep">·</span>
              <span style={{ color: '#d97706' }}>estimated</span>
            </>
          )}
          {story.place && <span className="eyebrow-sep">·</span>}
          {story.place && <span>{story.place}</span>}
          {story.stated_year && <span className="eyebrow-sep">·</span>}
          {story.stated_year && <span>{story.stated_year}</span>}
        </div>

        <h1 className="story-main-heading">{story.title}</h1>

        {story.has_private_part && (
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              margin: '8px 0 16px',
              padding: '6px 12px',
              background: 'rgba(120, 53, 15, 0.15)',
              border: '1px solid rgba(180, 83, 9, 0.3)',
              borderRadius: '6px',
              fontSize: '13px',
              color: '#b45309'
            }}
          >
            <Lock size={14} />
            <span>Part of this story is private.</span>
          </div>
        )}

        <div className="story-byline-meta-row">
          <div className="teller-info-badge">
            <div className="teller-avatar-circle" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--accent-terracotta)', color: '#fff', fontWeight: 600 }} aria-hidden="true">
              {story.teller?.name?.charAt(0) || '?'}
            </div>
            <div className="teller-text">
              {story.teller?.name && <span className="teller-name">{story.teller.name}</span>}
              <span className="teller-role">{story.kind === 'retelling' ? 'Retelling' : 'Storyteller'}</span>
            </div>
          </div>

          <div className="story-meta-pills-cluster">
            {primarySubject && (
              <button
                type="button"
                className="meta-info-pill"
                onClick={() => {
                  setSelectedPeriod(primarySubject.period);
                  setShowPeriodEditor(true);
                }}
                title="Change the chapter"
                style={{ cursor: 'pointer' }}
              >
                <Edit3 size={12} />
                <span>{periodDisplay}{isEstimated ? ' (estimated)' : ''}</span>
              </button>
            )}
          </div>
        </div>
        {chapterPeople.length > 0 && (
          <p className="story-on-chapters">On the life chapters of: {chapterPeople.join(', ')}</p>
        )}
      </header>

      <div className="story-two-column-showcase">
        <div className="story-listen-column">
          <section className="bespoke-audio-station" aria-label="Story audio player">
            <div className="station-top-bar">
              <div className="station-left">
                <button
                  type="button"
                  className={`station-play-btn ${isPlaying ? 'playing' : ''}`}
                  onClick={togglePlay}
                  disabled={audioDisabled && storyMode}
                  aria-label={audioDisabled && storyMode ? "Audio not available" : isPlaying ? "Pause" : "Play"}
                  title={audioDisabled && storyMode ? "Audio not available" : isPlaying ? "Pause" : "Play"}
                  style={{ opacity: audioDisabled && storyMode ? 0.45 : 1, cursor: audioDisabled && storyMode ? 'not-allowed' : 'pointer' }}
                >
                  {isPlaying ? <Pause size={22} /> : <Play size={22} style={{ marginLeft: '3px' }} />}
                </button>

                <div className="station-track-info">
                  <div className="station-track-title">
                    {storyMode
                      ? (tellerFirst ? `${tellerFirst}'s recording` : 'Recording')
                      : `Listening from the start · ${playlistItems[playlistIndex]?.title || ''}`}
                  </div>
                  {storyMode && (
                    <div className="station-time-readout">
                      <span className="time-current">{formatDuration(currentMs) || '0:00'}</span>
                      <span className="time-sep">/</span>
                      <span className="time-total">{formatDuration(durationMs) || '0:00'}</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="station-controls-right">
                <button
                  type="button"
                  className="station-speed-btn"
                  onClick={handleSpeedChange}
                  disabled={audioDisabled}
                  title="Playback speed"
                  aria-label={`Playback speed ${playbackSpeed}x`}
                >
                  {playbackSpeed}x
                </button>

                <button
                  type="button"
                  className="station-restart-btn"
                  onClick={() => seekTo(0, isPlaying)}
                  disabled={audioDisabled}
                  title="Back to the beginning"
                >
                  <RotateCcw size={14} />
                  <span>Restart</span>
                </button>
              </div>
            </div>

            <div
              className="station-scrubber-track"
              role="slider"
              aria-label="Position in the recording"
              aria-valuemin={0}
              aria-valuemax={durationMs}
              aria-valuenow={storyMode ? currentMs : 0}
              onClick={(e) => {
                if (audioDisabled) return;
                const rect = e.currentTarget.getBoundingClientRect();
                const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                seekTo(Math.round(pct * durationMs), isPlaying);
              }}
              style={{ opacity: audioDisabled ? 0.4 : 1, cursor: audioDisabled ? 'not-allowed' : 'pointer' }}
            >
              <div
                className="station-scrubber-fill"
                style={{ width: `${storyMode ? Math.min(100, (currentMs / (durationMs || 1)) * 100) : 0}%` }}
              >
                <div className="station-scrubber-pin" />
              </div>
            </div>
          </section>

          <section className="story-transcript-parchment" aria-label="Transcript">
            <div className="transcript-parchment-header">
              <div className="parchment-title-group">
                <span className="parchment-tag">TRANSCRIPT</span>
                <h3 className="parchment-title">In {tellerFirst ? `${tellerFirst}'s` : 'their'} own words</h3>
              </div>
              {!audioDisabled && (
                <span className="parchment-interactive-hint">
                  Tap a word to listen from there
                </span>
              )}
            </div>

            <div className="transcript-spoken-content">
              {transcript.length === 0 && (
                <p className="fallback-transcript-text">No transcript yet.</p>
              )}
              {transcript.map((seg) => (
                <p key={seg.segment_id} className="transcript-piece" style={{ marginBottom: '14px' }}>
                  {showSpeakers && seg.speaker?.name && (
                    <strong className="transcript-speaker">{seg.speaker.name}: </strong>
                  )}
                  {seg.words.length > 0 ? (
                    seg.words.map((item, idx) => {
                      const seekable = !audioDisabled && item.playStart != null;
                      const isActive = storyMode && item.playStart != null && currentMs >= item.playStart && currentMs <= item.playEnd;
                      return (
                        <span
                          key={idx}
                          className={`spoken-word ${isActive ? 'word-active' : ''}`}
                          onClick={seekable ? () => seekTo(item.playStart, true) : undefined}
                          title={seekable ? `Listen from ${formatDuration(item.playStart) || '0:00'}` : undefined}
                          style={{ cursor: seekable ? 'pointer' : 'default' }}
                        >
                          {item.display}{' '}
                        </span>
                      );
                    })
                  ) : (
                    <span className="fallback-transcript-text">{seg.text}</span>
                  )}
                </p>
              ))}
            </div>
          </section>
        </div>

        <aside className="story-side-showcase" aria-label="About this story">
          {story.photo_url && (
            <figure className="photo-matte-frame card-frame">
              <BlobPhoto
                photoUrl={story.photo_url}
                alt={story.photo_caption || story.title}
                fallback={{ title: story.title, period: primarySubject?.period, teller: story.teller?.name }}
              />
              {story.photo_caption && (
                <figcaption className="photo-caption"><PhotoCaption caption={story.photo_caption} addedBy={story.photo_added_by} /></figcaption>
              )}
            </figure>
          )}

          {canAddPhoto && (
            <button
              type="button"
              className="editorial-btn secondary"
              onClick={() => setShowPhotoModal(true)}
            >
              <ImagePlus size={15} />
              <span>{story.photo_url ? 'Replace the photo' : 'Add a photo'}</span>
            </button>
          )}

          {story.ai_summary && (
            <div className="side-archival-card curator-card">
              <div className="side-card-header">
                <div className="side-card-icon-gold">
                  <Sparkles size={16} />
                </div>
                <h4 className="side-card-heading">AI summary</h4>
              </div>
              <p className="curator-summary-text">{story.ai_summary}</p>
            </div>
          )}

          {/* Reactions: which are present and which are mine, never counts */}
          <div className="side-archival-card reactions-card">
            <div className="side-card-header">
              <div className="side-card-icon-terracotta">
                <Heart size={16} />
              </div>
              <h4 className="side-card-heading">Family reactions</h4>
            </div>
            <p className="reactions-instruction">
              Evoca shares your reactions in the next morning chat.
            </p>

            <div className="reaction-emojis-grid">
              {REACTIONS.map(r => {
                const isPresent = story.reactions?.present?.includes(r.key);
                const isMine = story.reactions?.mine?.includes(r.key);

                return (
                  <button
                    key={r.key}
                    type="button"
                    className={`reaction-heartbeat-btn ${isMine ? 'has-reacted' : ''} ${isPresent ? 'is-present' : ''}`}
                    onClick={() => handleToggleReaction(r.key)}
                    title={isMine ? 'Remove my reaction' : `React: ${r.label}`}
                    aria-pressed={isMine}
                    style={{
                      borderWidth: isMine ? '2px' : '1px',
                      borderColor: isMine ? 'var(--accent-terracotta)' : isPresent ? 'rgba(217, 119, 6, 0.4)' : undefined,
                      backgroundColor: isMine ? 'rgba(194, 65, 12, 0.12)' : isPresent ? 'rgba(217, 119, 6, 0.05)' : undefined
                    }}
                  >
                    <span className="reaction-emoji" aria-hidden="true">{r.emoji}</span>
                    <span className="reaction-label">{r.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* "Listen from the start": played in order, no skipped count */}
          {playlistItems.length > 0 && (
            <div className="side-archival-card playlist-card">
              <div className="side-card-header with-toggle">
                <div className="header-left">
                  <div className="side-card-icon-sage">
                    <Headphones size={16} />
                  </div>
                  <h4 className="side-card-heading">Listen from the start</h4>
                </div>
                <button
                  type="button"
                  className="btn-toggle-playlist"
                  onClick={() => setShowPlaylist(!showPlaylist)}
                >
                  {showPlaylist ? "Show less" : "Show more"}
                </button>
              </div>

              <p className="playlist-subtext">
                This story and the ones linked to it, one after another.
              </p>

              {showPlaylist && (
                <div className="playlist-episodes-list">
                  {playlistItems.map((item, idx) => {
                    const isCurrent = mode === 'playlist' && playlistIndex === idx;
                    return (
                      <div
                        key={idx}
                        className={`playlist-episode-row ${isCurrent ? 'episode-current' : ''}`}
                        onClick={() => playPlaylistFrom(idx)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => e.key === 'Enter' && playPlaylistFrom(idx)}
                        style={{ cursor: 'pointer' }}
                      >
                        <span className="episode-index">{String(idx + 1).padStart(2, '0')}</span>
                        <div className="episode-details">
                          <span className="episode-title">{item.title}</span>
                          <span className="episode-dur">{formatDuration(item.end_ms - item.start_ms)}</span>
                        </div>
                        {isCurrent ? (
                          <span className="episode-badge">Playing</span>
                        ) : (
                          <ChevronRight size={14} className="episode-arrow" />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {story.linked_stories && story.linked_stories.length > 0 && (
            <div className="side-archival-card" style={{ padding: '16px', background: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <div className="side-card-header" style={{ marginBottom: '12px' }}>
                <h4 className="side-card-heading" style={{ fontSize: '14px', fontWeight: 600 }}>Linked stories</h4>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {story.linked_stories.map((l) => (
                  <div
                    key={l.link_id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '8px 12px',
                      background: 'var(--bg-primary)',
                      borderRadius: '8px',
                      border: '1px solid var(--border-color)',
                      fontSize: '13px'
                    }}
                  >
                    <div>
                      <div
                        style={{ fontWeight: 500, cursor: 'pointer', color: 'var(--text-primary)' }}
                        onClick={() => l.story?.id && openStory(l.story.id)}
                      >
                        {l.story?.title || 'Linked story'}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        {l.reason === 'same_place' ? 'Same place' : l.reason === 'same_event' ? 'Same event' : 'Related'}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="editorial-btn secondary"
                      style={{ fontSize: '11px', padding: '4px 8px', borderColor: 'rgba(239, 68, 68, 0.3)', color: '#ef4444' }}
                      onClick={() => handleDeleteLink(l.link_id)}
                      title="Remove this link"
                    >
                      Not related
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {story.retellings && story.retellings.length > 0 && (
            <div className="side-archival-card retellings-card">
              <div className="side-card-header">
                <div className="side-card-icon-purple">
                  <MessageSquare size={16} />
                </div>
                <h4 className="side-card-heading">Told again by the family</h4>
              </div>

              <div className="retellings-stack">
                {story.retellings.map(ret => (
                  <div key={ret.id} className="retelling-bubble">
                    <h5
                      className="retelling-title"
                      style={{ cursor: 'pointer' }}
                      onClick={() => openStory(ret.id)}
                    >
                      “{ret.title}”
                    </h5>
                    <div className="retelling-byline">
                      Told by <strong>{ret.teller?.name}</strong> {ret.teller?.relation_to_center ? `(${ret.teller.relation_to_center})` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
