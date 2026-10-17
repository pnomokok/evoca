import React from 'react';
import { X, BookOpen } from 'lucide-react';

const getInitials = (name) =>
  (name || '')
    .split(' ')
    .filter(Boolean)
    .map(p => p[0])
    .join('')
    .toUpperCase() || '?';

// Members come from GET /api/circle; nothing about them is invented here.
export default function FamilyTreeModal({
  isOpen,
  onClose,
  circleData,
  onNavigateLifeline,
  storyCount
}) {
  if (!isOpen) return null;

  const circle = circleData?.circle;
  const members = circleData?.members || [];
  const center = members.find(m => m.role === 'center');
  const others = members.filter(m => m !== center);
  const centerFirst = center?.name?.split(' ')[0];

  const openLifeline = () => {
    onClose();
    if (onNavigateLifeline) onNavigateLifeline();
  };

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="family-tree-modal-title">
      <div className="modal-sheet archival-dialog family-tree-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header-row">
          <div className="dialog-title-group">
            <span className="archival-eyebrow">Family tree</span>
            <h2 id="family-tree-modal-title" className="archival-dialog-title">
              {circle?.name || 'Your family'}
            </h2>
            <p className="archival-dialog-sub">
              {storyCount > 0
                ? `${storyCount} ${storyCount === 1 ? 'story' : 'stories'} kept so far.`
                : 'No stories kept yet.'}
            </p>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close the family tree">
            <X size={20} />
          </button>
        </div>

        <div className="modal-tree-content">
          <div className="modal-generations-list">
            {center && (
              <div className="modal-generation-card">
                <div className="gen-badge">Storyteller</div>
                <div className="gen-member-item">
                  <div className="gen-avatar elder">
                    <span>{getInitials(center.name)}</span>
                  </div>
                  <div className="gen-details">
                    <div className="gen-name-row">
                      <strong>{center.name}</strong>
                      {center.birth_year && <span className="gen-year-pill">Born {center.birth_year}</span>}
                    </div>
                    <div className="gen-links">
                      <button className="gen-action-link" onClick={openLifeline}>
                        <BookOpen size={14} />
                        <span>See {centerFirst ? `${centerFirst}'s` : 'the'} life chapters →</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {others.length > 0 && (
              <div className="modal-generation-card">
                <div className="gen-badge">Family</div>
                <div className="gen-grandchildren-row">
                  {others.map(m => (
                    <div key={m.id} className="gen-grandchild-card">
                      <div className="gen-avatar child">
                        <span>{getInitials(m.name)}</span>
                      </div>
                      <div className="gen-details">
                        <strong>{m.name}</strong>
                        <span className="gen-sub">
                          {[m.relation_to_center, m.role === 'admin' ? 'admin' : null, m.birth_year ? `b. ${m.birth_year}` : null]
                            .filter(Boolean)
                            .join(' · ')}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="dialog-action-bar">
          <button type="button" className="editorial-btn secondary" onClick={onClose}>
            Close
          </button>
          <button type="button" className="editorial-btn primary" onClick={openLifeline}>
            <BookOpen size={16} />
            <span>View the life chapters</span>
          </button>
        </div>
      </div>
    </div>
  );
}
