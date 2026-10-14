import React from 'react';
import { Users, Sparkles, Mic, ArrowRight } from 'lucide-react';

export default function FamilyTreeCard({
  circleData,
  currentViewerId,
  onSwitchViewer,
  storyCount = 0,
  onOpenRecordModal,
  onOpenTreeModal,
  onNavigateLifeline
}) {
  const circle = circleData?.circle || { name: 'The Yılmaz Family' };
  const members = circleData?.members || [
    { id: "person_fatma", name: "Fatma Yılmaz", birth_year: 1948, role: "center", relation_to_center: null, avatar: "👵" },
    { id: "person_ayse",  name: "Ayşe Yılmaz",  birth_year: 1975, role: "admin",  relation_to_center: "daughter", avatar: "👩" },
    { id: "person_elif",  name: "Elif Yılmaz",  birth_year: 2003, role: "member", relation_to_center: "granddaughter", avatar: "👧" },
    { id: "person_can",   name: "Can Yılmaz",   birth_year: 2006, role: "member", relation_to_center: "grandson", avatar: "👦" }
  ];

  // Separate generations strictly: Grandparents at top, Children in middle, Grandchildren below
  const grandparents = members.filter(m => m.role === 'center' || m.relation_to_center === null || m.birth_year < 1960);
  const parents = members.filter(m => m.relation_to_center === 'daughter' || m.relation_to_center === 'son' || (m.birth_year >= 1960 && m.birth_year < 1990));
  const grandchildren = members.filter(m => m.relation_to_center === 'granddaughter' || m.relation_to_center === 'grandson' || m.birth_year >= 1990);

  // Helper for initials
  const getInitials = (name) => {
    return name
      .split(' ')
      .map(p => p[0])
      .join('')
      .toUpperCase();
  };

  // Helper for relation badge label
  const getRelationLabel = (member) => {
    if (member.role === 'center' || member.relation_to_center === null) return 'Grandmother · Storyteller';
    if (member.relation_to_center === 'daughter') return 'Daughter · Archive Admin';
    if (member.relation_to_center === 'son') return 'Son';
    if (member.relation_to_center === 'granddaughter') return 'Granddaughter';
    if (member.relation_to_center === 'grandson') return 'Grandson';
    return member.relation_to_center || member.role || 'Family Member';
  };

  return (
    <aside className="family-tree-preview-card" aria-labelledby="family-tree-card-heading">
      {/* 1. Card Header */}
      <div className="tree-card-header">
        <div className="tree-eyebrow-row">
          <span className="tree-botanical-ornament">❦</span>
          <span className="tree-eyebrow">Our Family</span>
        </div>
        <h2 id="family-tree-card-heading" className="tree-family-title">
          {circle.name || "The Yılmaz Family"}
        </h2>
        <p className="tree-supporting-text">
          Explore the people, relationships, and stories that make our family unique.
        </p>
      </div>

      {/* 2. Story Counter (Dynamic & Deduplicated) */}
      <div className="tree-story-counter-container">
        {storyCount > 0 ? (
          <div className="story-counter-pill has-stories">
            <div className="counter-main-row">
              <span className="counter-pulse-dot" />
              <span className="counter-count-label">
                <strong>{storyCount}</strong> {storyCount === 1 ? 'family story preserved' : 'family stories preserved'}
              </span>
            </div>
            <p className="counter-sub-quote">"Every story keeps a memory alive."</p>
          </div>
        ) : (
          <div className="story-counter-pill empty-stories">
            <div className="counter-empty-badge">
              <Sparkles size={14} className="sparkle-icon" />
              <span className="counter-empty-title">No family stories yet</span>
            </div>
            <p className="counter-empty-desc">
              Every family has a story worth keeping. Preserve the first one today.
            </p>
            <button
              type="button"
              className="tree-record-first-btn"
              onClick={() => onOpenRecordModal && onOpenRecordModal()}
            >
              <Mic size={13} />
              <span>Record the First Memory</span>
            </button>
          </div>
        )}
      </div>

      {/* 3. Primary "View Family Tree" Button */}
      <button
        type="button"
        className="view-family-tree-btn"
        onClick={() => onOpenTreeModal ? onOpenTreeModal() : onNavigateLifeline && onNavigateLifeline()}
        title="View full family tree and generational archive"
      >
        <Users size={16} />
        <span>View Family Tree</span>
        <ArrowRight size={14} className="tree-btn-arrow" />
      </button>

      {/* 4. Compact Top-to-Bottom Vertical Family Tree */}
      <div className="vertical-family-tree-canvas" role="region" aria-label="Generational Family Tree">
        {/* Tier 1: Grandparents (Top) */}
        <div className="tree-tier tier-grandparents">
          <div className="tier-label">Grandparent Generation</div>
          <div className="tier-nodes-row">
            {grandparents.map(member => {
              const isSelected = member.id === currentViewerId;
              return (
                <div
                  key={member.id}
                  className={`tree-person-node center-elder ${isSelected ? 'active-viewer' : ''}`}
                  onClick={() => onSwitchViewer && onSwitchViewer(member.id)}
                  title={`Click to view family archive as ${member.name}`}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && onSwitchViewer && onSwitchViewer(member.id)}
                >
                  <div className="cameo-portrait-circle elder-cameo">
                    <span className="cameo-monogram">{getInitials(member.name)}</span>
                    <span className="cameo-emoji-tag" aria-hidden="true">{member.avatar || '👵'}</span>
                  </div>
                  <div className="node-text-content">
                    <div className="node-name-row">
                      <span className="node-person-name">{member.name}</span>
                      {isSelected && <span className="viewer-active-tag">Active</span>}
                    </div>
                    <span className="node-relationship">{getRelationLabel(member)}</span>
                    <span className="node-birth-year">b. {member.birth_year || 1948}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Vertical Connector Line from Tier 1 to Tier 2 */}
        <div className="tree-vertical-stem" aria-hidden="true">
          <div className="stem-line" />
          <div className="stem-leaf-node">❦</div>
          <div className="stem-line" />
        </div>

        {/* Tier 2: Children / Parents (Middle) */}
        <div className="tree-tier tier-children">
          <div className="tier-label">Children Generation</div>
          <div className="tier-nodes-row">
            {parents.map(member => {
              const isSelected = member.id === currentViewerId;
              return (
                <div
                  key={member.id}
                  className={`tree-person-node parent-node ${isSelected ? 'active-viewer' : ''}`}
                  onClick={() => onSwitchViewer && onSwitchViewer(member.id)}
                  title={`Click to view family archive as ${member.name}`}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && onSwitchViewer && onSwitchViewer(member.id)}
                >
                  <div className="cameo-portrait-circle parent-cameo">
                    <span className="cameo-monogram">{getInitials(member.name)}</span>
                    <span className="cameo-emoji-tag" aria-hidden="true">{member.avatar || '👩'}</span>
                  </div>
                  <div className="node-text-content">
                    <div className="node-name-row">
                      <span className="node-person-name">{member.name}</span>
                      {isSelected && <span className="viewer-active-tag">Active</span>}
                    </div>
                    <span className="node-relationship">{getRelationLabel(member)}</span>
                    <span className="node-birth-year">b. {member.birth_year || 1975}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Vertical Connector Line with Fork from Tier 2 to Tier 3 */}
        <div className="tree-vertical-fork-stem" aria-hidden="true">
          <div className="stem-line-upper" />
          <div className="fork-horizontal-bar" />
          <div className="fork-down-legs">
            <span className="fork-leg left" />
            <span className="fork-leg right" />
          </div>
        </div>

        {/* Tier 3: Grandchildren (Below) */}
        <div className="tree-tier tier-grandchildren">
          <div className="tier-label">Grandchildren Generation</div>
          <div className="tier-nodes-grid-split">
            {grandchildren.map(member => {
              const isSelected = member.id === currentViewerId;
              return (
                <div
                  key={member.id}
                  className={`tree-person-node grandchild-node ${isSelected ? 'active-viewer' : ''}`}
                  onClick={() => onSwitchViewer && onSwitchViewer(member.id)}
                  title={`Click to view family archive as ${member.name}`}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && onSwitchViewer && onSwitchViewer(member.id)}
                >
                  <div className="cameo-portrait-circle grandchild-cameo">
                    <span className="cameo-monogram">{getInitials(member.name)}</span>
                    <span className="cameo-emoji-tag" aria-hidden="true">{member.avatar || (member.relation_to_center === 'grandson' ? '👦' : '👧')}</span>
                  </div>
                  <div className="node-text-content compact">
                    <div className="node-name-row">
                      <span className="node-person-name">{member.name.split(' ')[0]}</span>
                      {isSelected && <span className="viewer-active-tag">You</span>}
                    </div>
                    <span className="node-relationship">{member.relation_to_center === 'grandson' ? 'Grandson' : 'Granddaughter'}</span>
                    <span className="node-birth-year">b. {member.birth_year}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 5. Subtle Family Tree Footer Cue */}
      <div className="tree-card-footer-cue">
        <span className="cue-dot" />
        <span className="cue-text">Click any member to view archive through their lens</span>
      </div>
    </aside>
  );
}
