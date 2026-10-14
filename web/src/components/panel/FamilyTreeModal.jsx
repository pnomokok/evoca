import React from 'react';
import { X, Users, BookOpen, Clock, Heart, ArrowRight } from 'lucide-react';

export default function FamilyTreeModal({
  isOpen,
  onClose,
  circleData,
  currentViewerId,
  onSwitchViewer,
  onNavigateLifeline,
  storyCount
}) {
  if (!isOpen) return null;

  const circle = circleData?.circle || { name: 'The Yılmaz Family' };
  const members = circleData?.members || [];

  const getInitials = (name) => {
    return name
      .split(' ')
      .map(p => p[0])
      .join('')
      .toUpperCase();
  };

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="family-tree-modal-title">
      <div className="modal-sheet archival-dialog family-tree-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header-row">
          <div className="dialog-title-group">
            <span className="archival-eyebrow">Generational Heritage · {circle.name}</span>
            <h2 id="family-tree-modal-title" className="archival-dialog-title">
              The Yılmaz Family Chronicle
            </h2>
            <p className="archival-dialog-sub">
              Three living generations preserved across {storyCount} recorded memory chapters.
            </p>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close family tree dialog">
            <X size={20} />
          </button>
        </div>

        <div className="modal-tree-content">
          <div className="modal-generations-list">
            {/* Generation 1 */}
            <div className="modal-generation-card">
              <div className="gen-badge">1st Generation · Matriarch</div>
              <div className="gen-member-item">
                <div className="gen-avatar elder">
                  <span>FY</span>
                </div>
                <div className="gen-details">
                  <div className="gen-name-row">
                    <strong>Fatma Yılmaz</strong>
                    <span className="gen-year-pill">Born 1948 · Akçaabat</span>
                    <span className="gen-tag center">Storyteller</span>
                  </div>
                  <p className="gen-desc">
                    Grandmother and living memory keeper. Preserves oral histories of village childhood, moving to the coast, and family traditions through daily morning chats with Evoca.
                  </p>
                  <div className="gen-links">
                    <button
                      className="gen-action-link"
                      onClick={() => {
                        onClose();
                        onNavigateLifeline && onNavigateLifeline();
                      }}
                    >
                      <BookOpen size={14} />
                      <span>Explore Grandma's Life Chapters (1948 – Present) →</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Generation 2 */}
            <div className="modal-generation-card">
              <div className="gen-badge">2nd Generation · Daughter</div>
              <div className="gen-member-item">
                <div className="gen-avatar parent">
                  <span>AY</span>
                </div>
                <div className="gen-details">
                  <div className="gen-name-row">
                    <strong>Ayşe Yılmaz</strong>
                    <span className="gen-year-pill">Born 1975</span>
                    <span className="gen-tag admin">Archive Admin</span>
                  </div>
                  <p className="gen-desc">
                    Daughter. Helps manage family circle permissions, curates archival photographs, and organizes seasonal family gatherings.
                  </p>
                </div>
              </div>
            </div>

            {/* Generation 3 */}
            <div className="modal-generation-card">
              <div className="gen-badge">3rd Generation · Grandchildren</div>
              <div className="gen-grandchildren-row">
                <div className="gen-grandchild-card">
                  <div className="gen-avatar child">
                    <span>EY</span>
                  </div>
                  <div className="gen-details">
                    <strong>Elif Yılmaz</strong>
                    <span className="gen-sub">Granddaughter · b. 2003</span>
                    <span className="gen-note">Active listener, loves stories about Grandma's school days.</span>
                  </div>
                </div>

                <div className="gen-grandchild-card">
                  <div className="gen-avatar child">
                    <span>CY</span>
                  </div>
                  <div className="gen-details">
                    <strong>Can Yılmaz</strong>
                    <span className="gen-sub">Grandson · b. 2006</span>
                    <span className="gen-note">Asks questions about coastal fishing and childhood adventures.</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="dialog-action-bar">
          <button
            type="button"
            className="editorial-btn secondary"
            onClick={onClose}
          >
            Close
          </button>
          <button
            type="button"
            className="editorial-btn primary"
            onClick={() => {
              onClose();
              onNavigateLifeline && onNavigateLifeline();
            }}
          >
            <BookOpen size={16} />
            <span>View Grandma's Life Chapters</span>
          </button>
        </div>
      </div>
    </div>
  );
}
