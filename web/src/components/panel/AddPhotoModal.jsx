import React, { useState } from 'react';
import { X, AlertCircle, ImagePlus } from 'lucide-react';
import { apiClient } from '../../api/client';
import Modal from '../Modal';

const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_BYTES = 5 * 1024 * 1024;
const MAX_CAPTION = 120;

// "Add a photo": POST /api/stories/{id}/photo with image + caption (docs/api-samples/README.md).
// The server re-encodes it and removes all metadata; one photo per story, a new one replaces the old.
export default function AddPhotoModal({ storyId, hasPhoto, onClose, onSaved }) {
  const [file, setFile] = useState(null);
  const [caption, setCaption] = useState('');
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const handleFile = (e) => {
    const chosen = e.target.files?.[0] || null;
    setError(null);
    if (chosen && !ACCEPTED.includes(chosen.type)) {
      setError('Please choose a JPEG, PNG or WebP photo.');
      setFile(null);
      return;
    }
    if (chosen && chosen.size > MAX_BYTES) {
      setError('That photo is larger than 5 MB.');
      setFile(null);
      return;
    }
    setFile(chosen);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;
    setSaving(true);
    setError(null);
    try {
      const res = await apiClient.postStoryPhoto(storyId, file, caption);
      onSaved(res);
    } catch (err) {
      setError(err.status === 400 ? err.message : "The photo couldn't be added.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal onClose={() => !saving && onClose()} labelledBy="photo-dialog-title" sheetStyle={{ maxWidth: '480px' }}>
      <div className="modal-title-row">
        <div>
          <h2 id="photo-dialog-title" className="archival-dialog-title">{hasPhoto ? 'Replace the photo' : 'Add a photo'}</h2>
          <p className="archival-dialog-sub">One photo per story. Location and other details are removed from the file.</p>
        </div>
        <button className="close-btn" onClick={onClose} aria-label="Close" disabled={saving}>
          <X size={20} />
        </button>
      </div>

      <form onSubmit={handleSubmit} className="archival-form">
        <div className="form-group">
          <label className="form-label" htmlFor="photo-file">Photo (JPEG, PNG or WebP, up to 5 MB)</label>
          <input id="photo-file" type="file" accept={ACCEPTED.join(',')} onChange={handleFile} />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="photo-caption">Caption (optional)</label>
          <input
            id="photo-caption"
            className="archival-input-select"
            value={caption}
            maxLength={MAX_CAPTION}
            onChange={(e) => setCaption(e.target.value)}
            placeholder="For example: The garden in Akcaabat, summer 1956"
          />
        </div>

        {error && (
          <div role="alert" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444', fontSize: '13px' }}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <div className="dialog-action-bar">
          <button type="button" className="editorial-btn secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="editorial-btn primary" disabled={saving || !file}>
            <ImagePlus size={15} />
            <span>{saving ? 'Saving...' : 'Save the photo'}</span>
          </button>
        </div>
      </form>
    </Modal>
  );
}
