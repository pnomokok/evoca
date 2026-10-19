import React, { useCallback, useRef, useState } from 'react';
import { useApp } from '../context/useApp';
import { LANDING } from '../utils/routes';
import { useMediaQuery } from '../utils/useMediaQuery';
import { useDismiss } from '../utils/useDismiss';
import DemoControls from './DemoControls';
import PersonPicker from './PersonPicker';
import Avatar from './Avatar';
import { useDemoArchiving } from '../utils/useDemoArchiving';
import { ChevronDown, Compass, LogOut, MonitorSmartphone } from 'lucide-react';

// The demo layer: one thin strip above the product on every demo page (never on the landing page,
// never when signed in). The only place to switch person, open the stage, move the clock or leave the demo.
// Below 768 px it collapses to one "Demo" button that opens the same controls.
export default function DemoStrip() {
  const { activeTab, navigate, circleData, peopleList, currentViewerId, startTour } = useApp();
  const wide = useMediaQuery('(min-width: 769px)');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const panelRef = useRef(null);
  // Compact strip: the controls (and their "writing up" line) are folded away, so it shows here too.
  const archiving = useDemoArchiving(!wide && !panelOpen);
  const closePanel = useCallback(() => setPanelOpen(false), []);
  useDismiss(panelOpen, panelRef, closePanel);

  const onStage = activeTab === 'stage';
  const viewer = circleData?.members?.find(m => m.id === currentViewerId)
    || peopleList.find(p => p.id === currentViewerId);
  const viewerFirst = viewer?.name?.split(' ')[0] || '...';

  const go = (route) => { setPanelOpen(false); navigate(route); };
  const openPicker = () => { setPanelOpen(false); setPickerOpen(true); };
  // The guided tour lives on the stage: open it there; it starts the demo over first.
  const openGuide = () => { go({ tab: 'stage' }); startTour(); };

  const controls = <>
    <button type="button" className="demo-strip-btn viewer" onClick={openPicker} aria-haspopup="dialog">
      {viewer && <Avatar person={viewer} size={20} />}
      <span>Viewing as <strong>{viewerFirst}</strong></span>
      <ChevronDown size={13} />
    </button>
    {wide && <span className="demo-strip-spacer" />}
    <button
      type="button"
      className={`demo-strip-btn ${onStage ? 'active' : ''}`}
      onClick={() => go({ tab: 'stage' })}
      aria-current={onStage ? 'page' : undefined}
    >
      <MonitorSmartphone size={14} />
      <span>Watch the loop</span>
    </button>
    <button type="button" className="demo-strip-btn" onClick={openGuide}>
      <Compass size={14} />
      <span>Guide</span>
    </button>
    <DemoControls inline={onStage || !wide} />
    <button type="button" className="demo-strip-btn quiet" onClick={() => go(LANDING)}>
      <LogOut size={13} />
      <span>Exit demo</span>
    </button>
  </>;

  return (
    <div className="demo-strip" role="region" aria-label="Demo">
      <div className="demo-strip-inner">
        {wide ? <>
          <span className="demo-strip-label">Demo</span>
          {controls}
        </> : (
          <div className="demo-strip-compact" ref={panelRef}>
            <button
              type="button"
              className="demo-strip-label as-button"
              onClick={() => setPanelOpen(open => !open)}
              aria-expanded={panelOpen}
              aria-controls="demo-strip-panel"
              data-tour="demo-menu"
            >
              Demo <ChevronDown size={12} />
            </button>
            {archiving && (
              <span className="demo-archiving" role="status" data-tour="archiving">
                <span className="demo-spinner" aria-hidden="true" />
                Evoca is writing up the story...
              </span>
            )}
            {panelOpen && <div id="demo-strip-panel" className="demo-strip-panel">{controls}</div>}
          </div>
        )}
      </div>
      {pickerOpen && <PersonPicker onClose={() => setPickerOpen(false)} />}
    </div>
  );
}
