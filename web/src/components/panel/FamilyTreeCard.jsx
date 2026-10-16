import React from 'react';
import { Maximize2, Sparkles, Mic, Plus } from 'lucide-react';

const MEMBER_STYLES = {
  person_fatma: { bg: '#B06543', defaultRelation: 'Grandmother' },
  person_ayse:  { bg: '#5F7355', defaultRelation: 'Daughter' },
  person_elif:  { bg: '#4C7285', defaultRelation: 'Granddaughter' },
  person_can:   { bg: '#A85A52', defaultRelation: 'Grandson' }
};

export default function FamilyTreeCard({
  circleData,
  currentViewerId,
  onSwitchViewer,
  storyCount = 0,
  onOpenRecordModal,
  onOpenTreeModal,
  onOpenAskModal
}) {
  const circle = circleData?.circle || { name: 'The Yılmaz Family' };
  const members = circleData?.members || [
    { id: "person_fatma", name: "Fatma Yılmaz", birth_year: 1948, role: "center", relation_to_center: null },
    { id: "person_ayse",  name: "Ayşe Yılmaz",  birth_year: 1975, role: "admin",  relation_to_center: "daughter" },
    { id: "person_elif",  name: "Elif Yılmaz",  birth_year: 2003, role: "member", relation_to_center: "granddaughter" },
    { id: "person_can",   name: "Can Yılmaz",   birth_year: 2006, role: "member", relation_to_center: "grandson" }
  ];

  const fatma = members.find(m => m.id === 'person_fatma') || members[0];
  const ayse  = members.find(m => m.id === 'person_ayse')  || members[1];
  const elif  = members.find(m => m.id === 'person_elif')  || members[2];
  const can   = members.find(m => m.id === 'person_can')   || members[3];

  const getInitials = (name) => {
    return name
      ? name.split(' ').map(p => p[0]).join('').toUpperCase()
      : '??';
  };

  const getSub = (member) => {
    const rel = MEMBER_STYLES[member?.id]?.defaultRelation || member?.relation_to_center || 'Family';
    return member?.birth_year ? `b. ${member.birth_year} · ${rel}` : rel;
  };

  return (
    <aside className="family-tree-minimal-card" aria-labelledby="family-tree-minimal-title">
      {/* 1. Header Row (Matching reference image) */}
      <div className="minimal-tree-header">
        <div className="tree-title-left">
          <h2 id="family-tree-minimal-title" className="minimal-tree-title">
            Family Tree <span className="tree-surname-tag">— {circle.name?.replace('The ', '') || 'Yılmaz'}</span>
          </h2>
        </div>

        <button
          type="button"
          className="tree-full-view-pill-btn"
          onClick={() => onOpenTreeModal && onOpenTreeModal()}
          title="Open full family genealogical archive"
        >
          <Maximize2 size={13} />
          <span>Full View</span>
        </button>
      </div>

      {/* 2. Compact Story Counter Bar */}
      <div className="minimal-tree-counter-bar">
        {storyCount > 0 ? (
          <div className="counter-inline-row">
            <span className="counter-dot-active" />
            <span className="counter-count-bold">{storyCount} family stories preserved</span>
            <span className="counter-sep">·</span>
            <span className="counter-quote-italic">"Every story keeps a memory alive."</span>
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
              Preserve the first one today →
            </button>
          </div>
        )}
      </div>

      {/* 3. Minimalist Visual Family Tree Diagram */}
      <div className="minimal-tree-canvas" role="region" aria-label="Family Tree Diagram">
        {/* Top Node: Fatma Yılmaz (Patriarch / Center) */}
        {fatma && (
          <div className="tree-node-unit level-1">
            <button
              type="button"
              className={`minimal-avatar-circle ${fatma.id === currentViewerId ? 'active-viewer' : ''}`}
              style={{ backgroundColor: MEMBER_STYLES[fatma.id]?.bg || '#B06543' }}
              onClick={() => onSwitchViewer && onSwitchViewer(fatma.id)}
              title={`Switch viewer to ${fatma.name}`}
            >
              <span className="avatar-initials">{getInitials(fatma.name)}</span>
              {fatma.id === currentViewerId && <span className="active-dot-indicator" />}
            </button>
            <div className="node-caption">
              <span className="node-fullname">{fatma.name}</span>
              <span className="node-year-sub">{getSub(fatma)}</span>
            </div>
          </div>
        )}

        {/* Stem 1: From Fatma to Ayşe */}
        <div className="minimal-stem-single" aria-hidden="true">
          <span className="stem-vertical-line" />
        </div>

        {/* Middle Node: Ayşe Yılmaz (Daughter) */}
        {ayse && (
          <div className="tree-node-unit level-2">
            <button
              type="button"
              className={`minimal-avatar-circle ${ayse.id === currentViewerId ? 'active-viewer' : ''}`}
              style={{ backgroundColor: MEMBER_STYLES[ayse.id]?.bg || '#5F7355' }}
              onClick={() => onSwitchViewer && onSwitchViewer(ayse.id)}
              title={`Switch viewer to ${ayse.name}`}
            >
              <span className="avatar-initials">{getInitials(ayse.name)}</span>
              {ayse.id === currentViewerId && <span className="active-dot-indicator" />}
            </button>
            <div className="node-caption">
              <span className="node-fullname">{ayse.name}</span>
              <span className="node-year-sub">{getSub(ayse)}</span>
            </div>
          </div>
        )}

        {/* Stem 2: Fork branching down to Elif and Can */}
        <div className="minimal-stem-fork" aria-hidden="true">
          <span className="fork-trunk" />
          <span className="fork-crossbar" />
          <div className="fork-droplines">
            <span className="fork-drop left" />
            <span className="fork-drop right" />
          </div>
        </div>

        {/* Bottom Tier: Grandchildren (Elif and Can) */}
        <div className="tree-nodes-tier-bottom">
          {elif && (
            <div className="tree-node-unit level-3">
              <button
                type="button"
                className={`minimal-avatar-circle ${elif.id === currentViewerId ? 'active-viewer' : ''}`}
                style={{ backgroundColor: MEMBER_STYLES[elif.id]?.bg || '#4C7285' }}
                onClick={() => onSwitchViewer && onSwitchViewer(elif.id)}
                title={`Switch viewer to ${elif.name}`}
              >
                <span className="avatar-initials">{getInitials(elif.name)}</span>
                {elif.id === currentViewerId && <span className="active-dot-indicator" />}
              </button>
              <div className="node-caption">
                <span className="node-fullname">
                  {elif.name} {elif.id === currentViewerId && <em className="you-label">(You)</em>}
                </span>
                <span className="node-year-sub">{getSub(elif)}</span>
              </div>
            </div>
          )}

          {can && (
            <div className="tree-node-unit level-3">
              <button
                type="button"
                className={`minimal-avatar-circle ${can.id === currentViewerId ? 'active-viewer' : ''}`}
                style={{ backgroundColor: MEMBER_STYLES[can.id]?.bg || '#A85A52' }}
                onClick={() => onSwitchViewer && onSwitchViewer(can.id)}
                title={`Switch viewer to ${can.name}`}
              >
                <span className="avatar-initials">{getInitials(can.name)}</span>
                {can.id === currentViewerId && <span className="active-dot-indicator" />}
              </button>
              <div className="node-caption">
                <span className="node-fullname">{can.name}</span>
                <span className="node-year-sub">{getSub(can)}</span>
              </div>
            </div>
          )}
        </div>

        {/* Circular Dashed Action Button (from reference image) */}
        <button
          type="button"
          className="minimal-add-action-btn"
          onClick={() => onOpenRecordModal && onOpenRecordModal()}
          title="Record a family memory or add story"
          aria-label="Add memory"
        >
          <Plus size={16} />
        </button>
      </div>

      {/* 4. Subtle Clean Footer Help */}
      <div className="minimal-tree-footer-cue">
        <span>Click any person to view the archive from their perspective</span>
      </div>
    </aside>
  );
}
