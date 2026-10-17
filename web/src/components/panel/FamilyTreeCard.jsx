import React from 'react';
import { Maximize2, Sparkles, Plus } from 'lucide-react';

const getMemberColor = (member, index) => {
  if (member?.role === 'center') return '#B06543';
  if (member?.role === 'admin' || member?.relation_to_center === 'daughter') return '#5F7355';
  if (member?.relation_to_center === 'granddaughter') return '#4C7285';
  if (member?.relation_to_center === 'grandson') return '#A85A52';
  const palette = ['#B06543', '#5F7355', '#4C7285', '#A85A52'];
  return palette[index % palette.length];
};

export default function FamilyTreeCard({
  circleData,
  currentViewerId,
  onSwitchViewer,
  storyCount = 0,
  onOpenRecordModal,
  onOpenTreeModal
}) {
  const circle = circleData?.circle;
  const members = circleData?.members || [];

  // Match dynamically by role and relation without hardcoding IDs
  const centerMember = members.find(m => m.role === 'center') || members[0];
  const daughterMember = members.find(m => m.relation_to_center === 'daughter' || m.role === 'admin') || members[1];
  const grandChildren = members.filter(m => m !== centerMember && m !== daughterMember);
  const grandChild1 = grandChildren[0] || members[2];
  const grandChild2 = grandChildren[1] || members[3];

  const getInitials = (name) => {
    return name
      ? name.split(' ').map(p => p[0]).join('').toUpperCase()
      : '??';
  };

  const getSub = (member) => {
    const rel = member?.relation_to_center || (member?.role === 'center' ? 'Storyteller' : 'Family');
    return member?.birth_year ? `b. ${member.birth_year} · ${rel}` : rel;
  };

  return (
    <aside className="family-tree-minimal-card" aria-labelledby="family-tree-minimal-title">
      {/* 1. Header Row */}
      <div className="minimal-tree-header">
        <div className="tree-title-left">
          <h2 id="family-tree-minimal-title" className="minimal-tree-title">
            Family tree {circle?.name && <span className="tree-surname-tag">— {circle.name}</span>}
          </h2>
        </div>

        <button
          type="button"
          className="tree-full-view-pill-btn"
          onClick={() => onOpenTreeModal && onOpenTreeModal()}
          title="Open the full family tree"
        >
          <Maximize2 size={13} />
          <span>Full view</span>
        </button>
      </div>

      {/* 2. Compact Story Counter Bar */}
      <div className="minimal-tree-counter-bar">
        {storyCount > 0 ? (
          <div className="counter-inline-row">
            <span className="counter-dot-active" />
            <span className="counter-count-bold">{storyCount} family {storyCount === 1 ? 'story' : 'stories'} kept safe</span>
            <span className="counter-sep">·</span>
            <span className="counter-quote-italic">"Every story keeps a bond alive."</span>
          </div>
        ) : (
          <div className="counter-inline-row empty">
            <Sparkles size={13} className="sparkle-mini" />
            <span>No family stories yet</span>
            <span className="counter-sep">·</span>
            <button
              type="button"
              className="inline-record-link"
              onClick={() => onOpenRecordModal && onOpenRecordModal()}
            >
              Record the first one today →
            </button>
          </div>
        )}
      </div>

      {/* 3. Minimalist Visual Family Tree Diagram */}
      <div className="minimal-tree-canvas" role="region" aria-label="Family tree">
        {/* Top Node: Center Person (Grandmother / Center) */}
        {centerMember && (
          <div className="tree-node-unit level-1">
            <button
              type="button"
              className={`minimal-avatar-circle ${centerMember.id === currentViewerId ? 'active-viewer' : ''}`}
              style={{ backgroundColor: getMemberColor(centerMember, 0) }}
              onClick={() => onSwitchViewer && onSwitchViewer(centerMember.id)}
              title={`View as ${centerMember.name}`}
            >
              <span className="avatar-initials">{getInitials(centerMember.name)}</span>
              {centerMember.id === currentViewerId && <span className="active-dot-indicator" />}
            </button>
            <div className="node-caption">
              <span className="node-fullname">{centerMember.name}</span>
              <span className="node-year-sub">{getSub(centerMember)}</span>
            </div>
          </div>
        )}

        {/* Stem 1: From Center to Daughter */}
        <div className="minimal-stem-single" aria-hidden="true">
          <span className="stem-vertical-line" />
        </div>

        {/* Middle Node: Daughter */}
        {daughterMember && (
          <div className="tree-node-unit level-2">
            <button
              type="button"
              className={`minimal-avatar-circle ${daughterMember.id === currentViewerId ? 'active-viewer' : ''}`}
              style={{ backgroundColor: getMemberColor(daughterMember, 1) }}
              onClick={() => onSwitchViewer && onSwitchViewer(daughterMember.id)}
              title={`View as ${daughterMember.name}`}
            >
              <span className="avatar-initials">{getInitials(daughterMember.name)}</span>
              {daughterMember.id === currentViewerId && <span className="active-dot-indicator" />}
            </button>
            <div className="node-caption">
              <span className="node-fullname">{daughterMember.name}</span>
              <span className="node-year-sub">{getSub(daughterMember)}</span>
            </div>
          </div>
        )}

        {/* Stem 2: Fork branching down to Grandchildren */}
        <div className="minimal-stem-fork" aria-hidden="true">
          <span className="fork-trunk" />
          <span className="fork-crossbar" />
          <div className="fork-droplines">
            <span className="fork-drop left" />
            <span className="fork-drop right" />
          </div>
        </div>

        {/* Bottom Tier: Grandchildren */}
        <div className="tree-nodes-tier-bottom">
          {grandChild1 && (
            <div className="tree-node-unit level-3">
              <button
                type="button"
                className={`minimal-avatar-circle ${grandChild1.id === currentViewerId ? 'active-viewer' : ''}`}
                style={{ backgroundColor: getMemberColor(grandChild1, 2) }}
                onClick={() => onSwitchViewer && onSwitchViewer(grandChild1.id)}
                title={`View as ${grandChild1.name}`}
              >
                <span className="avatar-initials">{getInitials(grandChild1.name)}</span>
                {grandChild1.id === currentViewerId && <span className="active-dot-indicator" />}
              </button>
              <div className="node-caption">
                <span className="node-fullname">
                  {grandChild1.name} {grandChild1.id === currentViewerId && <em className="you-label">(you)</em>}
                </span>
                <span className="node-year-sub">{getSub(grandChild1)}</span>
              </div>
            </div>
          )}

          {grandChild2 && (
            <div className="tree-node-unit level-3">
              <button
                type="button"
                className={`minimal-avatar-circle ${grandChild2.id === currentViewerId ? 'active-viewer' : ''}`}
                style={{ backgroundColor: getMemberColor(grandChild2, 3) }}
                onClick={() => onSwitchViewer && onSwitchViewer(grandChild2.id)}
                title={`View as ${grandChild2.name}`}
              >
                <span className="avatar-initials">{getInitials(grandChild2.name)}</span>
                {grandChild2.id === currentViewerId && <span className="active-dot-indicator" />}
              </button>
              <div className="node-caption">
                <span className="node-fullname">
                  {grandChild2.name} {grandChild2.id === currentViewerId && <em className="you-label">(you)</em>}
                </span>
                <span className="node-year-sub">{getSub(grandChild2)}</span>
              </div>
            </div>
          )}
        </div>

        {/* Add Memory Button */}
        <button
          type="button"
          className="minimal-add-action-btn"
          onClick={() => onOpenRecordModal && onOpenRecordModal()}
          title="Record a memory"
          aria-label="Record a memory"
        >
          <Plus size={16} />
        </button>
      </div>

      {/* 4. Footer Cue */}
      <div className="minimal-tree-footer-cue">
        <span>Tap a person to see the archive through their eyes</span>
      </div>
    </aside>
  );
}
