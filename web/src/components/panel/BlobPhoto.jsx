import React, { useEffect, useState } from 'react';
import { Image as ImageIcon } from 'lucide-react';
import { apiClient } from '../../api/client';

// A story photo fetched with X-Person-Id (a plain <img src> cannot send the header).
// Shows a quiet placeholder when there is no photo or it is not available.
export default function BlobPhoto({ photoUrl, alt, className = 'archival-photo' }) {
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

  const src = loaded.path === photoUrl ? loaded.src : null;
  if (!src) {
    return (
      <div className={`${className} photo-placeholder`} role="img" aria-label={alt || 'No photo yet'}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '160px', background: 'var(--bg-secondary, #f4efe6)', color: 'var(--text-muted)' }}>
        <ImageIcon size={32} />
      </div>
    );
  }
  return <img src={src} alt={alt} className={className} />;
}
