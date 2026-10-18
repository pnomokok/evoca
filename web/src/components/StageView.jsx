import React from 'react';
import { useApp } from '../context/useApp';
import DemoControls from './DemoControls';
import { Users } from 'lucide-react';
import '../styles/stage.css';

// "Watch the loop" (demo only): Fatma's device and Elif's phone side by side, the demo clock on top.
// Each pane is the app itself in an iframe with its own fixed identity in the URL
// (?embed=device|panel&person=<id>); the panes tell each other about changes (utils/stageChannel.js).
export default function StageView() {
  const { peopleList, centerPersonId, circleData, currentViewerId, viewerReady, setActiveTab } = useApp();

  const members = circleData?.members || [];
  const center = members.find(m => m.id === centerPersonId) || peopleList.find(p => p.id === centerPersonId);
  // The family member whose phone is shown: Elif in the demo family, else the default viewer.
  const notCenter = peopleList.filter(p => p.id !== centerPersonId);
  const asker =
    notCenter.find(p => p.name?.split(' ')[0] === 'Elif') ||
    notCenter.find(p => p.id === currentViewerId) ||
    notCenter[0];
  const askerMember = members.find(m => m.id === asker?.id);
  const centerFirst = center?.name?.split(' ')[0] || '';
  const askerFirst = asker?.name?.split(' ')[0] || '';

  // While a reset runs (viewerReady is false) the panes are removed; they come back with the new ids.
  const ready = viewerReady && centerPersonId && asker;
  const deviceSrc = ready ? `/?embed=device&person=${encodeURIComponent(centerPersonId)}` : null;
  const panelSrc = ready ? `/?embed=panel&person=${encodeURIComponent(asker.id)}` : null;

  return (
    <div className="stage-page">
      <header className="stage-bar">
        <button type="button" className="stage-brand" onClick={() => setActiveTab('landing')} title="Go to Evoca Overview">
          <span className="brand-monogram">E</span>
          <span className="brand-name">Evoca</span>
        </button>
        {circleData?.circle?.name && <span className="stage-pill">Demo · {circleData.circle.name}</span>}
        <span className="stage-spacer" />
        <DemoControls inline />
        <button type="button" className="stage-btn quiet" onClick={() => setActiveTab('panel')}>
          <Users size={14} />
          Pick a role
        </button>
      </header>

      <main className="stage" aria-label="Watch the loop">
        <section className="stage-pane device-pane">
          <p className="stage-label">
            Living room device {centerFirst && <span>{centerFirst}</span>}
          </p>
          {deviceSrc ? (
            <iframe
              key={deviceSrc}
              className="stage-frame device-frame"
              src={deviceSrc}
              title={`${centerFirst || 'The storyteller'}'s living room device`}
              allow="microphone; autoplay"
            />
          ) : <div className="stage-frame device-frame stage-loading" role="status">Loading...</div>}
        </section>

        <section className="stage-pane phone-pane">
          <p className="stage-label">
            {askerFirst ? `${askerFirst}'s phone` : 'Family phone'}
            {askerMember?.relation_to_center && <span>{askerMember.relation_to_center}</span>}
          </p>
          <div className="stage-phone">
            {panelSrc ? (
              <iframe
                key={panelSrc}
                className="stage-frame phone-frame"
                src={panelSrc}
                title={`${askerFirst || 'A family member'}'s family panel`}
                allow="microphone; autoplay"
              />
            ) : <div className="stage-frame phone-frame stage-loading" role="status">Loading...</div>}
          </div>
        </section>
      </main>
    </div>
  );
}
