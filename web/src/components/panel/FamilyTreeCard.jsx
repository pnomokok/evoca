import React from 'react';
import { Maximize2, Sparkles, Mic, Plus } from 'lucide-react';

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
  const circle = circleData?.circle || { name: 'The Yılmaz Family' };
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
    const rel = member?.relation_to_center || (member?.role === 'center' ? 'Büyükanne' : member?.role === 'admin' ? 'Anne' : 'Aile');
    return member?.birth_year ? `d. ${member.birth_year} · ${rel}` : rel;
  };

  return (
    <aside className="family-tree-minimal-card" aria-labelledby="family-tree-minimal-title">
      {/* 1. Header Row */}
      <div className="minimal-tree-header">
        <div className="tree-title-left">
          <h2 id="family-tree-minimal-title" className="minimal-tree-title">
            Soy Ağacı <span className="tree-surname-tag">— {circle.name?.replace('The ', '') || 'Yılmaz'}</span>
          </h2>
        </div>

        <button
          type="button"
          className="tree-full-view-pill-btn"
          onClick={() => onOpenTreeModal && onOpenTreeModal()}
          title="Tüm soyağacı arşivini aç"
        >
          <Maximize2 size={13} />
          <span>Geniş Görünüm</span>
        </button>
      </div>

      {/* 2. Compact Story Counter Bar */}
      <div className="minimal-tree-counter-bar">
        {storyCount > 0 ? (
          <div className="counter-inline-row">
            <span className="counter-dot-active" />
            <span className="counter-count-bold">{storyCount} aile anısı koruma altında</span>
            <span className="counter-sep">·</span>
            <span className="counter-quote-italic">"Her anı bir bağı yaşatır."</span>
          </div>
        ) : (
          <div className="counter-inline-row empty">
            <Sparkles size={13} className="sparkle-mini" />
            <span>Henüz aile anısı yok</span>
            <span className="counter-sep">·</span>
            <button
              type="button"
              className="inline-record-link"
              onClick={() => onOpenRecordModal && onOpenRecordModal()}
            >
              İlkini bugün kaydedin →
            </button>
          </div>
        )}
      </div>

      {/* 3. Minimalist Visual Family Tree Diagram */}
      <div className="minimal-tree-canvas" role="region" aria-label="Aile Ağacı Şeması">
        {/* Top Node: Center Person (Grandmother / Center) */}
        {centerMember && (
          <div className="tree-node-unit level-1">
            <button
              type="button"
              className={`minimal-avatar-circle ${centerMember.id === currentViewerId ? 'active-viewer' : ''}`}
              style={{ backgroundColor: getMemberColor(centerMember, 0) }}
              onClick={() => onSwitchViewer && onSwitchViewer(centerMember.id)}
              title={`${centerMember.name} perspektifine geç`}
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
              title={`${daughterMember.name} perspektifine geç`}
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
                title={`${grandChild1.name} perspektifine geç`}
              >
                <span className="avatar-initials">{getInitials(grandChild1.name)}</span>
                {grandChild1.id === currentViewerId && <span className="active-dot-indicator" />}
              </button>
              <div className="node-caption">
                <span className="node-fullname">
                  {grandChild1.name} {grandChild1.id === currentViewerId && <em className="you-label">(Sen)</em>}
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
                title={`${grandChild2.name} perspektifine geç`}
              >
                <span className="avatar-initials">{getInitials(grandChild2.name)}</span>
                {grandChild2.id === currentViewerId && <span className="active-dot-indicator" />}
              </button>
              <div className="node-caption">
                <span className="node-fullname">
                  {grandChild2.name} {grandChild2.id === currentViewerId && <em className="you-label">(Sen)</em>}
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
          title="Anı kaydet veya hikâye ekle"
          aria-label="Anı ekle"
        >
          <Plus size={16} />
        </button>
      </div>

      {/* 4. Footer Cue */}
      <div className="minimal-tree-footer-cue">
        <span>Arşivi o kişinin gözünden görmek için üzerine tıklayın</span>
      </div>
    </aside>
  );
}
