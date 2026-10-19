import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '../api/client';
import { AppContext } from './useApp';
import { announceChange, listenForChanges } from '../utils/stageChannel';
import { JOURNAL, LANDING, pathFor, routeFromPath } from '../utils/routes';
import { SUGGESTED_QUESTION, paneTourWants } from '../utils/tour';

// Signed in (bearer): the session fixes person and circle, so GET /api/circle gives everything;
// the device invitation only for the center, the one person the device acts as.
async function fetchSignedInData() {
  const circle = await apiClient.getCircle();
  const circleId = circle?.circle?.id;
  const people = (circle?.members || []).map(m => ({ id: m.id, name: m.name, circles: [{ circle_id: circleId, role: m.role }] }));
  const centerId = circle?.circle?.center_person_id || null;
  const viewerId = apiClient.currentViewerId;
  const invitation = centerId && viewerId === centerId ? await apiClient.getDeviceInvitation(centerId) : null;
  return { people, centerId, viewerId, circle, invitation };
}

// Demo: people, the center, a verified viewer id, then circle and invitation with that id.
// Nothing that needs X-Person-Id is requested before the stored viewer id is checked
// against GET /api/people (a stale id from another database would 403).
async function fetchInitialData(options) {
  if (apiClient.isSignedIn) {
    try {
      return await fetchSignedInData();
    } catch (err) {
      if (err.status !== 401) throw err;
      // The session was revoked (a new link, a removed member) or has ended: back to the demo.
      apiClient.clearSession();
      return { ...(await fetchDemoData()), signedOut: true };
    }
  }
  return fetchDemoData(options);
}

// preferCenter: after a reset on the device, the storyteller is chosen again instead of the default member.
async function fetchDemoData({ preferCenter = false } = {}) {
  const people = (await apiClient.getPeople()) || [];
  const centerId = people.find(p => p.circles?.some(c => c.role === 'center'))?.id || null;

  // The last choice (localStorage), else the oldest person with role "member".
  let viewerId = apiClient.currentViewerId;
  // A stage pane is only ever the person in its URL; an unknown id (a stale stage) loads nothing.
  if (apiClient.embed && !people.some(p => p.id === viewerId)) {
    return { people, centerId, viewerId: '', circle: null, invitation: null };
  }
  if (!people.some(p => p.id === viewerId) && preferCenter && centerId) {
    viewerId = centerId;
    apiClient.setViewer(viewerId);
  }
  if (!people.some(p => p.id === viewerId)) {
    const members = people.filter(p => p.circles?.some(c => c.role === 'member'));
    let preferred = members[0] || people[0];
    if (members.length > 1) {
      // Birth years come from GET /api/circle, which needs a person: ask as any member,
      // without storing them as the viewer (a second run of this effect would keep them).
      const circle = await apiClient.getCircle(preferred.id);
      const oldest = (circle?.members || [])
        .filter(m => m.role === 'member' && m.birth_year != null)
        .sort((a, b) => a.birth_year - b.birth_year)[0];
      if (oldest) preferred = oldest;
    }
    viewerId = preferred?.id || '';
    apiClient.setViewer(viewerId);
  }
  if (!viewerId) {
    return { people, centerId, viewerId, circle: null, invitation: null };
  }

  const [circle, invitation] = await Promise.all([
    apiClient.getCircle(),
    centerId ? apiClient.getDeviceInvitation(centerId) : Promise.resolve(null)
  ]);
  return { people, centerId, viewerId, circle, invitation };
}

// The page in the address bar (an unknown path: the landing, or the journal when signed in) with the
// story's back target from the history entry. A stage pane starts on its own view and never uses the URL.
function initialRoute(embedTab, embedSubTab) {
  if (apiClient.embed) return { tab: embedTab, subTab: embedSubTab, storyId: null, back: null, depth: 0 };
  const route = routeFromPath(window.location.pathname, apiClient.isSignedIn) || (apiClient.isSignedIn ? JOURNAL : LANDING);
  const state = window.history.state || {};
  // A reload shows the entry as it was: in the demo, with its person (checked like any stored id).
  if (!apiClient.isSignedIn && state.viewerId) apiClient.setViewer(state.viewerId);
  return { ...route, back: state.back || null, depth: state.depth || 0 };
}

// Pages a person cannot use: the device is only for the center; in the demo the center has the device
// instead of the archive; Family settings is for the admin, My questions for those who can ask.
function redirectFor(route, { currentViewerId, centerPersonId, circleData, isSignedIn }) {
  if (!currentViewerId || !centerPersonId) return null;
  const isCenterViewer = currentViewerId === centerPersonId;
  const me = circleData?.me?.id === currentViewerId ? circleData.me : null;
  const { tab, subTab } = route;
  if (tab === 'device' && !isCenterViewer) return JOURNAL;
  if (tab === 'panel' && !isSignedIn && isCenterViewer) return { ...LANDING, tab: 'device' };
  if (tab === 'panel' && me && ((subTab === 'settings' && me.role !== 'admin') || (subTab === 'questions' && me.role === 'center'))) {
    return JOURNAL;
  }
  return null;
}

// The router: the route ({tab, subTab, storyId, back, depth}) follows window.location. navigate() pushes
// history; Back and Forward (popstate) restore the page and, in the demo, the person viewing, which is kept
// in the history entry's state, never in the URL. A stage pane (apiClient.embed) never touches history.
// startAtHome: just signed in, so the center goes to the device once loaded. restartApp(tab) remounts the app
// after the identity changed. A stage pane loads again when another pane announces a change.
export function AppProvider({ children, initialTab = 'landing', initialPanelSubTab = 'feed', startAtHome = false, initialToast = null, restartApp, openCreateFamily }) {
  const [route, setRoute] = useState(() => initialRoute(initialTab, initialPanelSubTab));
  const routeRef = useRef(route);
  const openHomeRef = useRef(startAtHome);
  const [isSignedIn] = useState(apiClient.isSignedIn);
  const [currentViewerId, setCurrentViewerId] = useState(apiClient.currentViewerId);
  // False until the stored viewer id has been checked (see fetchInitialData).
  const [viewerReady, setViewerReady] = useState(false);
  // Bumped after every demo clock action: views add it to their fetch dependencies and load again.
  const [dataVersion, setDataVersion] = useState(0);
  // Bumped after a demo reset: the device drops a session the reset has already ended.
  const [resetVersion, setResetVersion] = useState(0);

  const [peopleList, setPeopleList] = useState([]);
  const [centerPersonId, setCenterPersonId] = useState(null);
  const [circleData, setCircleData] = useState(null);
  const [invitationData, setInvitationData] = useState(null);
  const [loading, setLoading] = useState(true);
  // The archive's dialogs, opened from the header, the bottom bar or a chapter: {period, prompt} or null.
  const [askDialog, setAskDialog] = useState(null);
  const [recordOpen, setRecordOpen] = useState(false);
  // The stage's guided tour (GuidedTour) while it is open: { run, skipReset }, else null.
  // Starting it resets the demo first, unless that was just done (skipReset).
  const [tourRun, setTourRun] = useState(null);
  // A message carried over a restart (for example after leaving a family) is shown at once.
  const [toast, setToast] = useState(() => (initialToast ? { message: initialToast, type: 'info' } : null));
  const toastTimerRef = useRef(null);
  const peopleRef = useRef(peopleList);

  useEffect(() => {
    routeRef.current = route;
    peopleRef.current = peopleList;
  });

  const showToast = useCallback((message, type = 'info') => {
    setToast({ message, type });
    clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 3800);
  }, []);

  useEffect(() => {
    if (!initialToast) return;
    toastTimerRef.current = setTimeout(() => setToast(null), 3800);
    return () => clearTimeout(toastTimerRef.current);
  }, [initialToast]);

  // The same page for the same person replaces the history entry; anything else is a new entry.
  const navigate = useCallback((to, { replace = false } = {}) => {
    const next = { subTab: 'feed', storyId: null, back: null, depth: 0, ...to };
    routeRef.current = next;
    setRoute(next);
    if (apiClient.embed) return;
    const path = pathFor(next);
    const state = { back: next.back, depth: next.depth, viewerId: apiClient.isSignedIn ? null : apiClient.currentViewerId };
    const samePage = path === window.location.pathname && (window.history.state?.viewerId ?? null) === state.viewerId;
    if (replace || samePage) {
      window.history.replaceState(state, '', path);
    } else {
      window.history.pushState(state, '', path);
      window.scrollTo(0, 0);
    }
  }, []);

  // A story remembers the page it was opened from (a linked story keeps the first one) and how many
  // entries back that page is, so its back button and the browser's Back land on the same page.
  const openStory = useCallback((storyId) => {
    const cur = routeRef.current;
    const fromStory = cur.tab === 'panel' && cur.subTab === 'story';
    const origin = ['feed', 'lifeline', 'questions'].includes(cur.subTab) ? cur.subTab : 'feed';
    navigate({
      tab: 'panel',
      subTab: 'story',
      storyId,
      back: fromStory ? (cur.back || 'feed') : origin,
      depth: fromStory ? (cur.depth || 0) + 1 : 1
    });
  }, [navigate]);

  const closeStory = useCallback(() => {
    const cur = routeRef.current;
    if (!apiClient.embed && cur.depth > 0 && window.history.state?.depth === cur.depth) {
      window.history.go(-cur.depth);
    } else {
      navigate({ tab: 'panel', subTab: cur.back || 'feed' });
    }
  }, [navigate]);

  const applyInitialData = useCallback(({ people, centerId, viewerId, circle, invitation, signedOut }) => {
    if (signedOut) {
      // The app was started signed in; start again in demo mode.
      restartApp?.('landing', "You're signed out of that family. Ask your family for a new link.");
      return;
    }
    if (openHomeRef.current) {
      openHomeRef.current = false;
      if (viewerId && viewerId === (centerId || circle?.circle?.center_person_id)) navigate({ tab: 'device' }, { replace: true });
    }
    setPeopleList(people);
    setCenterPersonId(centerId || circle?.circle?.center_person_id || null);
    setCurrentViewerId(viewerId);
    setViewerReady(Boolean(viewerId));
    setCircleData(circle);
    setInvitationData(invitation);
    setLoading(false);
  }, [restartApp, navigate]);

  const handleLoadError = useCallback((err) => {
    console.error("Failed to load initial Evoca data", err);
    showToast("We couldn't reach Evoca. Please try again in a moment.", "error");
    setLoading(false);
  }, [showToast]);

  // A refresh that finishes after the viewer was switched is dropped: it would put the
  // previous viewer back (switchViewer has already loaded the new viewer's circle).
  const loadInitialData = useCallback(
    (options) => fetchInitialData(options).then(
      result => { if (result.viewerId === apiClient.currentViewerId) applyInitialData(result); },
      handleLoadError
    ),
    [applyInitialData, handleLoadError]
  );

  useEffect(() => {
    let cancelled = false;
    fetchInitialData().then(
      result => { if (!cancelled) applyInitialData(result); },
      err => { if (!cancelled) handleLoadError(err); }
    );
    return () => { cancelled = true; };
  }, [applyInitialData, handleLoadError]);

  // A stage pane: another pane changed something, so load again. After a reset the stage
  // reloads the panes with the new ids; the old ids would only give 403s here.
  useEffect(() => {
    if (!apiClient.embed) return undefined;
    return listenForChanges((reason) => {
      if (reason === 'reset') return;
      loadInitialData().then(() => setDataVersion(v => v + 1));
    });
  }, [loadInitialData]);

  // Demo only: when the viewer changes, reload circle data. quiet: no toast (Back and Forward).
  const switchViewer = useCallback(async (personId, { quiet = false } = {}) => {
    if (apiClient.isSignedIn) return;
    apiClient.setViewer(personId);
    setCurrentViewerId(personId);
    try {
      const circle = await apiClient.getCircle();
      if (apiClient.currentViewerId !== personId) return;
      setCircleData(circle);
      const personName = circle?.me?.name || peopleRef.current.find(p => p.id === personId)?.name || 'someone else';
      if (!quiet) showToast(`Now viewing as ${personName}`, 'info');
    } catch (err) {
      console.error(err);
      setCircleData(null);
      showToast("Couldn't switch to that person.", "error");
    }
  }, [showToast]);

  // Back and Forward: the page from the URL, the back target and (demo) the person from the entry's state.
  useEffect(() => {
    if (apiClient.embed) return undefined;
    const onPopState = (e) => {
      const state = e.state || {};
      const next = routeFromPath(window.location.pathname, isSignedIn) || (isSignedIn ? JOURNAL : LANDING);
      const full = { ...next, back: state.back || null, depth: state.depth || 0 };
      routeRef.current = full;
      setRoute(full);
      const viewerId = state.viewerId;
      if (!isSignedIn && viewerId && viewerId !== apiClient.currentViewerId && peopleRef.current.some(p => p.id === viewerId)) {
        switchViewer(viewerId, { quiet: true });
      }
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, [isSignedIn, switchViewer]);

  // A page the person cannot use is swapped for the right one while rendering; the effect below puts it
  // in the address bar (and the start's unknown path), keeping the history entry's state.
  const redirect = !apiClient.embed && !loading && redirectFor(route, { currentViewerId, centerPersonId, circleData, isSignedIn });
  if (redirect) setRoute(redirect);

  useEffect(() => {
    if (apiClient.embed) return;
    const path = pathFor(route);
    if (path !== window.location.pathname) {
      window.history.replaceState({ ...window.history.state, back: route.back, depth: route.depth }, '', path);
    }
  }, [route]);

  // Signed in: "Open your family" goes to the person's own place (the device for the center).
  const openHome = useCallback(() => {
    navigate(currentViewerId && currentViewerId === centerPersonId ? { tab: 'device' } : JOURNAL);
  }, [navigate, currentViewerId, centerPersonId]);

  // While the guided tour points at "Ask", the dialog opens with its suggested question.
  const openAsk = useCallback((period = null, prompt = '') => setAskDialog({
    period, prompt: prompt || (paneTourWants('ask-alt') ? SUGGESTED_QUESTION : '')
  }), []);
  const closeAsk = useCallback(() => setAskDialog(null), []);
  const openRecord = useCallback(() => setRecordOpen(true), []);
  const closeRecord = useCallback(() => setRecordOpen(false), []);
  const startTour = useCallback(({ skipReset = false } = {}) => setTourRun(t => ({ run: (t?.run ?? 0) + 1, skipReset })), []);
  const closeTour = useCallback(() => setTourRun(null), []);

  // Demo controls: move the clock, then reload people, circle and invitation, and let every view refetch.
  const demoAdvance = async (hours) => {
    const clock = await apiClient.postDemoAdvance(hours);
    announceChange('clock');
    await loadInitialData();
    setDataVersion(v => v + 1);
    return clock;
  };

  // A reset rebuilds the database with new ids: nothing is requested with the old ones while the
  // viewer is picked again (the stored id is gone, so fetchInitialData chooses the default viewer,
  // or the storyteller again when the device is open). An open story is gone: back to the journal.
  const demoReset = async () => {
    const onDevice = routeRef.current.tab === 'device';
    setViewerReady(false);
    if (routeRef.current.subTab === 'story') navigate(JOURNAL, { replace: true });
    setResetVersion(v => v + 1);
    try {
      await apiClient.postDemoReset();
      announceChange('reset');
    } finally {
      await loadInitialData({ preferCenter: onDevice });
      setDataVersion(v => v + 1);
    }
  };

  // "Leave": leave the device screen first (it ends an open session while still signed in),
  // then end the session on the server and start again on the landing page.
  const leaveFamily = async () => {
    navigate(LANDING);
    try {
      await apiClient.logout();
    } catch (err) {
      console.warn('Sign-out did not reach the server:', err);
    }
    restartApp?.('landing', 'You left your family. Open your personal link to come back.');
  };

  return (
    <AppContext.Provider value={{
      isSignedIn,
      leaveFamily,
      openCreateFamily,
      openHome,
      navigate,
      openStory,
      closeStory,
      activeTab: route.tab,
      panelSubTab: route.subTab,
      selectedStoryId: route.storyId,
      storyBack: route.back || 'feed',
      askDialog,
      openAsk,
      closeAsk,
      recordOpen,
      openRecord,
      closeRecord,
      tourRun,
      startTour,
      closeTour,
      currentViewerId,
      viewerReady,
      peopleList,
      centerPersonId,
      switchViewer,
      dataVersion,
      resetVersion,
      demoAdvance,
      demoReset,
      circleData,
      invitationData,
      setInvitationData,
      loading,
      toast,
      showToast,
      refreshData: loadInitialData,
      // Load again and let every page reload its own data (as after a stage change).
      reloadAll: () => loadInitialData().then(() => setDataVersion(v => v + 1))
    }}>
      {children}
    </AppContext.Provider>
  );
}
