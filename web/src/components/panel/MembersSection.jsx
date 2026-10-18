import React, { useState } from 'react';
import { useApp } from '../../context/useApp';
import { apiClient } from '../../api/client';
import Modal from '../Modal';
import CopyLink from '../CopyLink';
import { forgetLinked, fullInviteUrl, linkedPersonIds, markLinked } from '../../utils/inviteLinks';
import { AlertTriangle, Link2, Pencil, Plus, Trash2, Tv } from 'lucide-react';

const ROLE_LABELS = { center: 'Storyteller', admin: 'Admin', member: 'Member' };
const EMPTY_NEW = { name: '', birth_year: '', relation_to_center: '', role: 'member' };

// Members of the circle for its admin (/api/admin/members, /api/admin/invites): add, change
// relation or role, remove, and make each person's personal link. The center is never changed.
export default function MembersSection() {
  const { circleData, currentViewerId, isSignedIn, refreshData, showToast } = useApp();
  const circleId = circleData?.circle?.id;
  const members = circleData?.members || [];
  const [linked, setLinked] = useState(() => linkedPersonIds(circleId));
  const [links, setLinks] = useState({});        // person id -> full link made just now
  const [editing, setEditing] = useState(null);  // { id, relation_to_center, role, error }
  const [confirm, setConfirm] = useState(null);  // { kind: 'remove' | 'relink', member }
  const [newMember, setNewMember] = useState(EMPTY_NEW);
  const [addError, setAddError] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async (fn) => {
    setBusy(true);
    try {
      return await fn();
    } finally {
      setBusy(false);
    }
  };

  const makeLink = (member) => run(async () => {
    setConfirm(null);
    try {
      const invite = await apiClient.createInvite(member.id);
      markLinked(circleId, member.id);
      setLinked(linkedPersonIds(circleId));
      setLinks(l => ({ ...l, [member.id]: fullInviteUrl(invite.invite_url_path) }));
    } catch (err) {
      console.error('Could not make the link:', err);
      showToast("Couldn't make the link. Please try again.", 'error');
    }
  });

  const askLink = (member) => {
    if (linked.includes(member.id)) setConfirm({ kind: 'relink', member });
    else makeLink(member);
  };

  const saveEdit = () => run(async () => {
    const member = members.find(m => m.id === editing.id);
    const changes = {};
    if (editing.relation_to_center.trim() !== (member.relation_to_center || '')) changes.relation_to_center = editing.relation_to_center.trim();
    if (editing.role !== member.role) changes.role = editing.role;
    if (Object.keys(changes).length === 0) {
      setEditing(null);
      return;
    }
    try {
      await apiClient.patchMember(editing.id, changes);
      setEditing(null);
      await refreshData();
    } catch (err) {
      setEditing(e => ({ ...e, error: err.status === 400 ? err.message : 'That did not work. Please try again.' }));
    }
  });

  const remove = (member) => run(async () => {
    setConfirm(null);
    try {
      await apiClient.removeMember(member.id);
      forgetLinked(circleId, member.id);
      setLinked(linkedPersonIds(circleId));
      setLinks(l => ({ ...l, [member.id]: undefined }));
      showToast(`${member.name} was removed from the family.`, 'info');
      await refreshData();
    } catch (err) {
      showToast(err.status === 400 ? err.message : "Couldn't remove them. Please try again.", 'error');
    }
  });

  const add = (e) => {
    e.preventDefault();
    run(async () => {
      setAddError(null);
      const year = newMember.birth_year.trim();
      try {
        const member = await apiClient.addMember({
          name: newMember.name.trim(),
          birth_year: year === '' ? null : Number(year),
          relation_to_center: newMember.relation_to_center.trim(),
          role: newMember.role,
        });
        setNewMember(EMPTY_NEW);
        showToast(`${member.name} was added. Make their invite link next.`, 'info');
        await refreshData();
      } catch (err) {
        setAddError(err.status === 400 ? err.message : 'That did not work. Please try again.');
      }
    });
  };

  return (
    <section className="side-archival-card" aria-labelledby="members-heading" style={{ marginBottom: '24px' }}>
      <h2 id="members-heading" className="side-card-heading">Members</h2>
      <p className="section-desc">
        Everyone opens the family with their own personal link. A link works like a password: share it only with that person.
      </p>

      <ul className="members-list">
        {members.map(m => {
          const isCenter = m.role === 'center';
          const isMe = m.id === currentViewerId;
          const hasLink = linked.includes(m.id);
          const isEditing = editing?.id === m.id;
          const linkLabel = isCenter ? 'Connect her device' : hasLink ? 'New link' : 'Invite link';
          return (
            <li key={m.id} className="member-row" data-testid={`member-${m.name}`}>
              <div className="member-main">
                <div className="member-text">
                  <strong>{m.name}{isMe ? ' (you)' : ''}</strong>
                  <div className="section-desc">
                    {[isCenter ? null : m.relation_to_center, ROLE_LABELS[m.role] || m.role, m.birth_year && `b. ${m.birth_year}`]
                      .filter(Boolean).join(' · ')}
                  </div>
                </div>
                <div className="member-actions">
                  {/* Your own new link would sign this browser out at once, so it is made by another admin. */}
                  {!(isSignedIn && isMe) && (
                    <button type="button" className="editorial-btn secondary" onClick={() => askLink(m)} disabled={busy}>
                      {isCenter ? <Tv size={14} /> : <Link2 size={14} />}
                      <span>{linkLabel}</span>
                    </button>
                  )}
                  {!isCenter && !isEditing && (
                    <button
                      type="button"
                      className="editorial-btn secondary"
                      onClick={() => setEditing({ id: m.id, relation_to_center: m.relation_to_center || '', role: m.role, error: null })}
                      disabled={busy}
                      aria-label={`Change ${m.name}`}
                    >
                      <Pencil size={14} />
                      <span>Change</span>
                    </button>
                  )}
                  {!isCenter && !isMe && (
                    <button
                      type="button"
                      className="editorial-btn secondary"
                      onClick={() => setConfirm({ kind: 'remove', member: m })}
                      disabled={busy}
                      aria-label={`Remove ${m.name}`}
                    >
                      <Trash2 size={14} />
                      <span>Remove</span>
                    </button>
                  )}
                </div>
              </div>

              {isEditing && (
                <form className="member-edit" onSubmit={(e) => { e.preventDefault(); saveEdit(); }}>
                  <label className="form-label" htmlFor={`rel-${m.id}`}>Relation</label>
                  <input
                    id={`rel-${m.id}`}
                    className="archival-input-select"
                    value={editing.relation_to_center}
                    onChange={(e) => setEditing(ed => ({ ...ed, relation_to_center: e.target.value, error: null }))}
                    maxLength={60}
                  />
                  <label className="form-label" htmlFor={`role-${m.id}`}>Role</label>
                  <select
                    id={`role-${m.id}`}
                    className="archival-input-select"
                    value={editing.role}
                    onChange={(e) => setEditing(ed => ({ ...ed, role: e.target.value, error: null }))}
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                  </select>
                  <button type="submit" className="editorial-btn primary" disabled={busy}>Save</button>
                  <button type="button" className="editorial-btn secondary" onClick={() => setEditing(null)} disabled={busy}>Cancel</button>
                  {editing.error && <p className="field-error" role="alert">{editing.error}</p>}
                </form>
              )}

              {links[m.id] && (
                <div className="member-link">
                  <CopyLink url={links[m.id]} label={`${m.name}'s personal link`} />
                  <p className="section-desc" style={{ margin: '6px 0 0' }}>
                    {isCenter
                      ? 'Open this link once on the device in her home.'
                      : `Send it to ${m.name.split(' ')[0]} only. It opens the family as them.`}
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <form onSubmit={add} className="archival-form member-add">
        <h3 className="form-label" style={{ margin: 0 }}>Add a member</h3>
        <div className="member-add-fields">
          <input
            className="archival-input-select"
            aria-label="Name"
            placeholder="Name"
            value={newMember.name}
            onChange={(e) => { setNewMember(n => ({ ...n, name: e.target.value })); setAddError(null); }}
            maxLength={60}
          />
          <input
            className="archival-input-select"
            aria-label="Birth year"
            placeholder="Birth year"
            type="number"
            inputMode="numeric"
            value={newMember.birth_year}
            onChange={(e) => { setNewMember(n => ({ ...n, birth_year: e.target.value })); setAddError(null); }}
          />
          <input
            className="archival-input-select"
            aria-label="Relation to the storyteller"
            placeholder="Relation (granddaughter...)"
            value={newMember.relation_to_center}
            onChange={(e) => { setNewMember(n => ({ ...n, relation_to_center: e.target.value })); setAddError(null); }}
            maxLength={60}
          />
          <select
            className="archival-input-select"
            aria-label="Role"
            value={newMember.role}
            onChange={(e) => setNewMember(n => ({ ...n, role: e.target.value }))}
          >
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>
          <button
            type="submit"
            className="editorial-btn primary"
            disabled={busy || !newMember.name.trim() || !newMember.relation_to_center.trim()}
          >
            <Plus size={14} />
            <span>Add</span>
          </button>
        </div>
        {addError && <p className="field-error" role="alert">{addError}</p>}
      </form>

      {confirm && (
        <Modal onClose={() => setConfirm(null)} labelledBy="member-confirm-title" sheetStyle={{ maxWidth: '460px' }}>
          <div className="modal-title-row dialog-title-flex">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-terracotta)' }}>
              <AlertTriangle size={20} />
              <h3 id="member-confirm-title" className="archival-dialog-title" style={{ margin: 0 }}>
                {confirm.kind === 'remove' ? `Remove ${confirm.member.name}?` : `A new link for ${confirm.member.name}?`}
              </h3>
            </div>
          </div>
          <p style={{ fontSize: '14px', lineHeight: '1.6', margin: '16px 0', color: 'var(--text-charcoal-muted)' }}>
            {confirm.kind === 'remove'
              ? 'They leave the family; their stories stay. Their link and every device that used it stop working.'
              : 'The old link and every device that used it stop working. They will need the new link.'}
          </p>
          <div className="dialog-action-bar">
            <button type="button" className="editorial-btn secondary" onClick={() => setConfirm(null)}>Cancel</button>
            <button
              type="button"
              className="editorial-btn primary"
              onClick={() => (confirm.kind === 'remove' ? remove(confirm.member) : makeLink(confirm.member))}
            >
              {confirm.kind === 'remove' ? 'Remove' : 'Make a new link'}
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
