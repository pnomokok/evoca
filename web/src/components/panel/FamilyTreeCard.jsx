import React from 'react';
import { Maximize2 } from 'lucide-react';

const LATEST_LIMIT = 3;

const getMemberColor = (member, index) => {
  if (member?.role === 'center') return '#B06543';
  if (member?.role === 'admin' || member?.relation_to_center === 'daughter') return '#5F7355';
  if (member?.relation_to_center === 'granddaughter') return '#4C7285';
  if (member?.relation_to_center === 'grandson') return '#A85A52';
  const palette = ['#B06543', '#5F7355', '#4C7285', '#A85A52'];
  return palette[index % palette.length];
};

const getInitials = (name) => {
  return name
    ? name.split(' ').map(p => p[0]).join('').toUpperCase()
    : '??';
};

const firstName = (name) => (name || '').split(' ')[0];

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// One quiet line with a person's part in the archive, from what the viewer can see:
// the center's own stories; for the others stories about them, else (the viewer only) the questions they asked.
function archivePart(member, { centerId, stories, viewerId, myQuestionCount }) {
  if (!member) return null;
  if (member.id === centerId) {
    const told = stories.filter(s => s.teller?.id === member.id).length;
    return told > 0 ? plural(told, 'story', 'stories') : null;
  }
  const about = stories.filter(s => (s.subjects || []).some(sub => sub.person_id === member.id)).length;
  if (about > 0) return `${plural(about, 'story', 'stories')} about them`;
  // Only the viewer's own questions are visible to the viewer.
  if (member.id === viewerId && myQuestionCount > 0) return `asked ${plural(myQuestionCount, 'question', 'questions')}`;
  return null;
}

// The newest things in the feed, one line each. The feed holds only what the viewer can see
// (published stories, answers to the viewer's own questions), so nothing pending or hidden shows here.
function latestItems(feedItems, members, viewerId) {
  const byFirst = (name) => members.find(m => firstName(m.name) === name);
  const actor = (person) => person?.id === viewerId ? 'You' : firstName(person?.name);
  const items = [];
  const seenStories = new Set();
  const photoLine = (storyId, title, addedBy) => {
    const person = byFirst(addedBy);
    if (!person) return;
    items.push({ key: `photo-${storyId}`, person, text: `${actor(person)} added a photo to`, title });
  };
  for (const item of feedItems) {
    if (item.type === 'question_answered' && item.answer) {
      const a = item.answer;
      if (seenStories.has(a.story_id)) continue;
      seenStories.add(a.story_id);
      items.push({ key: `answer-${a.story_id}`, person: a.teller, text: `${actor(a.teller)} answered your question in`, title: a.story_title });
      if (a.photo_added_by) photoLine(a.story_id, a.story_title, a.photo_added_by);
    } else if (item.type === 'story_published' && item.story) {
      const s = item.story;
      if (seenStories.has(s.id)) continue;
      seenStories.add(s.id);
      items.push({ key: `story-${s.id}`, person: s.teller, text: `${actor(s.teller)} told`, title: s.title });
      if (s.photo_added_by) photoLine(s.id, s.title, s.photo_added_by);
    }
    if (items.length >= LATEST_LIMIT) break;
  }
  return items.slice(0, LATEST_LIMIT);
}

function TreeNode({ member, level, color, isViewer, part }) {
  return (
    <div className={`tree-node-unit level-${level}`}>
      <span
        className={`minimal-avatar-circle ${isViewer ? 'active-viewer' : ''}`}
        style={{ backgroundColor: color }}
        title={member.name}
      >
        <span className="avatar-initials">{getInitials(member.name)}</span>
        {isViewer && <span className="active-dot-indicator" />}
      </span>
      <div className="node-caption">
        <span className="node-fullname">
          {member.name} {level === 3 && isViewer && <em className="you-label">(you)</em>}
        </span>
        <span className="node-year-sub">{getSub(member)}</span>
        {part && <span className="node-archive-part">{part}</span>}
      </div>
    </div>
  );
}

const getSub = (member) => {
  const rel = member?.relation_to_center || (member?.role === 'center' ? 'Storyteller' : 'Family');
  return member?.birth_year ? `b. ${member.birth_year} · ${rel}` : rel;
};

// Informative only: who is in the family, their part in the archive and the latest family moments
// ("Full view" opens the whole tree). stories are the unique stories the viewer can see.
export default function FamilyTreeCard({
  circleData,
  currentViewerId,
  storyCount = 0,
  stories = [],
  feedItems = [],
  myQuestionCount = 0,
  onOpenTreeModal
}) {
  const circle = circleData?.circle;
  const members = circleData?.members || [];

  // Match dynamically by role and relation without hardcoding IDs
  const centerMember = members.find(m => m.role === 'center') || members[0];
  const daughterMember = members.find(m => m !== centerMember && (m.relation_to_center === 'daughter' || m.role === 'admin'))
    || members.find(m => m !== centerMember);
  const grandChildren = members.filter(m => m !== centerMember && m !== daughterMember);
  const grandChild1 = grandChildren[0];
  const grandChild2 = grandChildren[1];
  // Connector lines only where someone is below them: none lead nowhere.
  const bottomCount = [grandChild1, grandChild2].filter(Boolean).length;

  const tree = [centerMember, daughterMember, grandChild1, grandChild2];
  const colorOf = (person) => {
    const index = tree.findIndex(m => m && m.id === person?.id);
    const member = members.find(m => m.id === person?.id);
    return getMemberColor(member, index >= 0 ? index : members.indexOf(member));
  };
  const partContext = { centerId: centerMember?.id, stories, viewerId: currentViewerId, myQuestionCount };
  const node = (member, level) => member && (
    <TreeNode
      member={member}
      level={level}
      color={colorOf(member)}
      isViewer={member.id === currentViewerId}
      part={archivePart(member, partContext)}
    />
  );

  const latest = latestItems(feedItems, members, currentViewerId);

  return (
    <aside className="family-tree-minimal-card" aria-labelledby="family-tree-minimal-title">
      <div className="minimal-tree-header">
        <div className="tree-title-left">
          <h2 id="family-tree-minimal-title" className="minimal-tree-title">
            Family tree {circle?.name && <span className="tree-surname-tag">— {circle.name}</span>}
          </h2>
          <p className="minimal-tree-count">
            {storyCount > 0
              ? `${plural(storyCount, 'family story', 'family stories')} kept safe`
              : 'No family stories yet'}
          </p>
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

      <div className="minimal-tree-canvas" role="region" aria-label="Family tree">
        {node(centerMember, 1)}

        {/* Stem 1: From Center to Daughter */}
        {centerMember && daughterMember && (
          <div className="minimal-stem-single" aria-hidden="true">
            <span className="stem-vertical-line" />
          </div>
        )}

        {node(daughterMember, 2)}

        {/* Stem 2: one line to a single grandchild, a fork to two */}
        {daughterMember && bottomCount === 1 && (
          <div className="minimal-stem-single" aria-hidden="true">
            <span className="stem-vertical-line" />
          </div>
        )}
        {daughterMember && bottomCount === 2 && (
          <div className="minimal-stem-fork" aria-hidden="true">
            <span className="fork-trunk" />
            <span className="fork-crossbar" />
            <div className="fork-droplines">
              <span className="fork-drop left" />
              <span className="fork-drop right" />
            </div>
          </div>
        )}

        {bottomCount > 0 && <div className="tree-nodes-tier-bottom">
          {node(grandChild1, 3)}
          {node(grandChild2, 3)}
        </div>}
      </div>

      {latest.length > 0 && (
        <section className="tree-latest" aria-labelledby="tree-latest-title">
          <h3 id="tree-latest-title" className="tree-latest-title">Latest in the family</h3>
          <ul className="tree-latest-list">
            {latest.map(item => (
              <li key={item.key} className="tree-latest-item">
                <span className="tree-latest-avatar" style={{ backgroundColor: colorOf(item.person) }} aria-hidden="true">
                  {getInitials(members.find(m => m.id === item.person?.id)?.name || item.person?.name)}
                </span>
                <span className="tree-latest-text">
                  {item.text} <em className="tree-latest-story">{item.title}</em>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  );
}
