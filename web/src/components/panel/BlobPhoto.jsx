import React, { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import { periodLabel } from '../../utils/periods';

// A plain text card for a story without a photo: never an empty image box.
export function StoryTextCard({ title, period, teller, className = 'archival-photo' }) {
  return (
    <div className={`${className} photo-text-card`}
      style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: '6px', minHeight: '160px', padding: '20px', background: 'var(--bg-secondary, #f4efe6)' }}>
      {period && <span className="card-period-tag">{periodLabel(period)}</span>}
      {title && <strong className="card-story-title" style={{ cursor: 'default' }}>{title}</strong>}
      {teller && <span className="card-storyteller">Told by {teller}</span>}
    </div>
  );
}

// A story photo fetched with X-Person-Id (a plain <img src> cannot send the header).
// Without a photo, or while it is not available, the story's text card (or fallbackNode) is shown instead.
export default function BlobPhoto({ photoUrl, alt, className = 'archival-photo', fallback = {}, fallbackNode = null }) {
  const [loaded, setLoaded] = useState({ path: null, src: null });

  useEffect(() => {
    if (!photoUrl) return;
    let cancelled = false;
    let blobUrl = null;
    apiClient.fetchBlobUrl(photoUrl)
      .then(src => {
        const isBlob = src?.startsWith('blob:');
        if (cancelled) {
          if (isBlob) URL.revokeObjectURL(src);
          return;
        }
        if (isBlob) blobUrl = src;
        setLoaded({ path: photoUrl, src });
      })
      .catch(() => {
        if (!cancelled) setLoaded({ path: photoUrl, src: null });
      });
    return () => {
      cancelled = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [photoUrl]);

  const src = photoUrl && loaded.path === photoUrl ? loaded.src : null;
  if (!src) return fallbackNode || <StoryTextCard {...fallback} className={className} />;
  return <img src={src} alt={alt} className={className} />;
}
