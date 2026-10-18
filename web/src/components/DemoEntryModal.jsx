import React from 'react';
import Modal from './Modal';
import { MonitorSmartphone, Users, X } from 'lucide-react';

// The demo entry: watch the whole loop side by side, or pick one person and look around.
export default function DemoEntryModal({ onClose, onWatchLoop, onPickRole }) {
  return (
    <Modal onClose={onClose} labelledBy="demo-entry-title" sheetStyle={{ maxWidth: '520px' }}>
      <div className="modal-title-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 id="demo-entry-title" className="archival-dialog-title" style={{ margin: 0 }}>Try the demo</h3>
        <button type="button" className="close-btn" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
      </div>
      <div className="demo-entry-options">
        <button type="button" className="demo-entry-option primary" onClick={onWatchLoop}>
          <MonitorSmartphone size={22} />
          <span>
            <strong>Watch the loop</strong>
            <small>Grandma's living room device and her granddaughter's phone, side by side. Ask, answer, react.</small>
          </span>
        </button>
        <button type="button" className="demo-entry-option" onClick={onPickRole}>
          <Users size={22} />
          <span>
            <strong>Pick a role</strong>
            <small>Open the family archive and choose whose eyes you see it through.</small>
          </span>
        </button>
      </div>
    </Modal>
  );
}
