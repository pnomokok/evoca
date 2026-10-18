import React from 'react';
import { useApp } from '../context/useApp';
import { apiClient } from '../api/client';
import { JOURNAL } from '../utils/routes';
import Modal from './Modal';
import Avatar from './Avatar';
import { X } from 'lucide-react';

const firstName = (name) => (name || '').split(' ')[0];

// What each person's view shows, from role and relation only.
function describe(member, centerFirst) {
  if (member.role === 'center') {
    return { line: 'the storyteller', view: 'Talks to Evoca on her living room device' };
  }
  const relation = member.relation_to_center || 'family';
  if (member.role === 'admin') {
    return { line: `${relation} · admin`, view: 'Sets sensitive topics and invites the family' };
  }
  return { line: relation, view: `Asks ${centerFirst || 'the storyteller'} questions and hears her answers` };
}

// "Who do you want to be?" (demo only): the one way to switch person. The storyteller opens the device,
// anyone else their journal. Before a first choice, Elif (or the first other member) is suggested.
export default function PersonPicker({ onClose }) {
  const { circleData, peopleList, centerPersonId, currentViewerId, switchViewer, navigate } = useApp();

  const members = circleData?.members?.length
    ? circleData.members
    : peopleList.map(p => ({ id: p.id, name: p.name, role: p.circles?.[0]?.role || 'member', relation_to_center: null }));
  const centerFirst = firstName(members.find(m => m.id === centerPersonId)?.name);
  const others = members.filter(m => m.id !== centerPersonId);
  const suggested = others.find(m => firstName(m.name) === 'Elif') || others[0] || null;
  const chosenBefore = apiClient.viewerChosen;
  const focusId = chosenBefore ? currentViewerId : suggested?.id;

  const choose = (member) => {
    apiClient.markViewerChosen();
    onClose();
    if (member.id !== currentViewerId) switchViewer(member.id);
    navigate(member.id === centerPersonId ? { tab: 'device' } : JOURNAL);
  };

  return (
    <Modal onClose={onClose} labelledBy="person-picker-title" sheetClassName="modal-sheet archival-dialog person-picker">
      <div className="modal-title-row dialog-title-flex">
        <h3 id="person-picker-title" className="archival-dialog-title" style={{ margin: 0 }}>Who do you want to be?</h3>
        <button type="button" className="close-btn" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
      </div>
      <p className="archival-dialog-sub">The demo family, seen through one person's eyes.</p>

      <ul className="person-picker-grid">
        {members.map(m => {
          const { line, view } = describe(m, centerFirst);
          const isCurrent = chosenBefore && m.id === currentViewerId;
          const isSuggested = !chosenBefore && m.id === suggested?.id;
          return (
            <li key={m.id}>
              <button
                type="button"
                className={`person-option ${isCurrent ? 'current' : ''} ${isSuggested ? 'suggested' : ''}`}
                onClick={() => choose(m)}
                aria-current={isCurrent ? 'true' : undefined}
                data-autofocus={m.id === focusId ? '' : undefined}
              >
                <Avatar person={m} size={56} ring={isCurrent || isSuggested} />
                <strong>{firstName(m.name)}</strong>
                <span className="person-line">{line}</span>
                <span className="person-view">{view}</span>
                {isCurrent && <span className="person-badge">Viewing now</span>}
                {isSuggested && <span className="person-badge">Suggested</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </Modal>
  );
}
