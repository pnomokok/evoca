import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useApp } from '../context/useApp';
import { apiClient } from '../api/client';
import { listenForChanges } from '../utils/stageChannel';
import AnswerNotice from './panel/AnswerNotice';
import { useNewAnswers } from './panel/useNewAnswers';
import GuidedTour from './GuidedTour';
import { TOUR_ANSWER_STEP } from '../utils/tour';
import PersonPicker from './PersonPicker';
import { useShowMcpCalls } from '../utils/mcpCalls';
import '../styles/stage.css';

const CLOCK_REFRESH_MS = 30_000;

// The phone's status bar time: the demo clock in the family's time zone ("10:05").
function phoneTime(iso, timeZone) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone });
}

// "Watch the loop" (demo only): Fatma's device and Elif's phone side by side, under the demo strip
// (DemoStrip: the clock, the person picker and "Exit demo").
// Each pane is the app itself in an iframe with its own fixed identity in the URL
// (?embed=device|panel&person=<id>); the panes tell each other about changes (utils/stageChannel.js).
// When the phone's person gets an answer, the phone shows a notification banner; tapping it opens
// the answer in My questions inside the phone (a message to the panel's iframe).
// The guided tour (GuidedTour) opens by itself on the first visit; "Guide" in the strip opens it again.
export default function StageView() {
  const { peopleList, centerPersonId, circleData, currentViewerId, viewerReady, tourRun, startTour } = useApp();
  const phoneRef = useRef(null);
  const [clock, setClock] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [showMcpCalls] = useShowMcpCalls();

  useEffect(() => {
    if (!apiClient.tourSeen) startTour();
  }, [startTour]);

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

  const loadClock = useCallback(() => apiClient.getDemoClock().then(c => setClock(c), () => {}), []);
  useEffect(() => {
    loadClock();
    const timer = setInterval(loadClock, CLOCK_REFRESH_MS);
    const stop = listenForChanges(loadClock);
    return () => { clearInterval(timer); stop(); };
  }, [loadClock]);

  const { notice, dismiss } = useNewAnswers({
    circleId: circleData?.circle?.id, personId: asker?.id, enabled: Boolean(ready)
  });
  const openAnswer = useCallback((questionId) => {
    phoneRef.current?.contentWindow?.postMessage({ type: 'evoca-open-answer', questionId }, window.location.origin);
  }, []);

  // On the tour's listening step the banner would cover the answer card: close it and open the answer.
  const [tourStep, setTourStep] = useState(null);
  useEffect(() => {
    if (tourStep !== TOUR_ANSWER_STEP || !notice) return;
    openAnswer(notice.questionId);
    dismiss();
  }, [tourStep, notice, openAnswer, dismiss]);

  const time = phoneTime(clock?.now, circleData?.circle?.timezone);

  return (
    <div className={`stage-page ${tourRun ? 'tour-open' : ''} ${showMcpCalls ? '' : 'mcp-hidden'}`}>
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
          {/* A phone drawn in CSS: bezel, notch, status bar, screen, home indicator. */}
          <div className="stage-phone">
            <div className="phone-screen">
              <div className="phone-status" aria-hidden="true">
                <span className="phone-time">{time}</span>
                <span className="phone-notch" />
                <span className="phone-icons">
                  <span className="phone-signal"><i /><i /><i /><i /></span>
                  <span className="phone-battery"><i /></span>
                </span>
              </div>
              {panelSrc ? (
                <iframe
                  key={panelSrc}
                  ref={phoneRef}
                  className="stage-frame phone-frame"
                  src={panelSrc}
                  title={`${askerFirst || 'A family member'}'s family panel`}
                  allow="microphone; autoplay"
                />
              ) : <div className="stage-frame phone-frame stage-loading" role="status">Loading...</div>}
              <div className="phone-home" aria-hidden="true" />
              <AnswerNotice
                notice={notice}
                centerFirst={centerFirst}
                onOpen={openAnswer}
                onDismiss={dismiss}
                variant="banner"
              />
            </div>
          </div>
        </section>
      </main>
      {/* Not only while ready: the tour resets the demo, and must outlive the panes reloading. */}
      {tourRun && (
        <GuidedTour
          key={tourRun.run}
          skipReset={tourRun.skipReset}
          centerId={ready ? centerPersonId : null}
          askerId={ready ? asker.id : null}
          onExplore={() => setPickerOpen(true)}
          onStep={setTourStep}
        />
      )}
      {pickerOpen && <PersonPicker onClose={() => setPickerOpen(false)} />}
    </div>
  );
}
