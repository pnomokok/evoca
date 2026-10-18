import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '../api/client';
import { AppContext } from './useApp';

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
async function fetchInitialData() {
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
  return fetchDemoData();
}

async function fetchDemoData() {
  const people = (await apiClient.getPeople()) || [];
  const centerId = people.find(p => p.circles?.some(c => c.role === 'center'))?.id || null;

  // The last choice (localStorage), else the oldest person with role "member".
  let viewerId = apiClient.currentViewerId;
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

// initialTab 'home': the signed-in person's own place once loaded (the device for the center,
// otherwise the family panel). restartApp(tab) remounts the app after the identity changed.
export function AppProvider({ children, initialTab = 'landing', initialToast = null, restartApp, openCreateFamily }) {
  const [activeTab, setActiveTab] = useState(initialTab === 'home' ? 'panel' : initialTab); // 'landing' | 'device' | 'panel'
  const openHomeRef = useRef(initialTab === 'home');
  const [isSignedIn] = useState(apiClient.isSignedIn);
  const [panelSubTab, setPanelSubTab] = useState('feed'); // 'feed' | 'lifeline' | 'story' | 'questions' | 'settings'
  const [selectedStoryId, setSelectedStoryId] = useState(null);
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
  // A message carried over a restart (for example after leaving a family) is shown at once.
  const [toast, setToast] = useState(() => (initialToast ? { message: initialToast, type: 'info' } : null));
  const toastTimerRef = useRef(null);

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

  const applyInitialData = useCallback(({ people, centerId, viewerId, circle, invitation, signedOut }) => {
    if (signedOut) {
      // The app was started signed in; start again in demo mode.
      restartApp?.('landing', "You're signed out of that family. Ask your family for a new link.");
      return;
    }
    if (openHomeRef.current) {
      openHomeRef.current = false;
      if (viewerId && viewerId === (centerId || circle?.circle?.center_person_id)) setActiveTab('device');
    }
    setPeopleList(people);
    setCenterPersonId(centerId || circle?.circle?.center_person_id || null);
    setCurrentViewerId(viewerId);
    setViewerReady(Boolean(viewerId));
    setCircleData(circle);
    setInvitationData(invitation);
    setLoading(false);
  }, [restartApp]);

  const handleLoadError = useCallback((err) => {
    console.error("Failed to load initial Evoca data", err);
    showToast("We couldn't reach Evoca. Please try again in a moment.", "error");
    setLoading(false);
  }, [showToast]);

  // A refresh that finishes after the viewer was switched is dropped: it would put the
  // previous viewer back (switchViewer has already loaded the new viewer's circle).
  const loadInitialData = useCallback(
    () => fetchInitialData().then(
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

  // Demo picker only: when the viewer changes, reload circle data.
  const switchViewer = async (personId) => {
    if (apiClient.isSignedIn) return;
    apiClient.setViewer(personId);
    setCurrentViewerId(personId);
    try {
      const circle = await apiClient.getCircle();
      setCircleData(circle);
      const personName = circle?.me?.name || peopleList.find(p => p.id === personId)?.name || 'someone else';
      showToast(`Now viewing as ${personName}`, 'info');
    } catch (err) {
      console.error(err);
      setCircleData(null);
      showToast("Couldn't switch to that person.", "error");
    }
  };

  // Demo controls: move the clock, then reload people, circle and invitation, and let every view refetch.
  const demoAdvance = async (hours) => {
    const clock = await apiClient.postDemoAdvance(hours);
    await loadInitialData();
    setDataVersion(v => v + 1);
    return clock;
  };

  // A reset rebuilds the database with new ids: nothing is requested with the old ones while the
  // viewer is picked again (the stored id is gone, so fetchInitialData chooses the default viewer).
  const demoReset = async () => {
    setViewerReady(false);
    setSelectedStoryId(null);
    setPanelSubTab(tab => (tab === 'story' ? 'feed' : tab));
    setResetVersion(v => v + 1);
    try {
      await apiClient.postDemoReset();
    } finally {
      await loadInitialData();
      setDataVersion(v => v + 1);
    }
  };

  // "Leave": leave the device screen first (it ends an open session while still signed in),
  // then end the session on the server and start again on the landing page.
  const leaveFamily = async () => {
    setActiveTab('landing');
    try {
      await apiClient.logout();
    } catch (err) {
      console.warn('Sign-out did not reach the server:', err);
    }
    restartApp?.('landing', 'You left your family. Open your personal link to come back.');
  };

  // The demo entry: a stored session is forgotten, then the demo family opens.
  const enterDemo = (tab = 'panel') => {
    if (apiClient.isSignedIn) {
      apiClient.clearSession();
      restartApp?.(tab);
      return;
    }
    setActiveTab(tab);
  };

  return (
    <AppContext.Provider value={{
      isSignedIn,
      leaveFamily,
      enterDemo,
      openCreateFamily,
      activeTab,
      setActiveTab,
      panelSubTab,
      setPanelSubTab,
      selectedStoryId,
      setSelectedStoryId,
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
      refreshData: loadInitialData
    }}>
      {children}
    </AppContext.Provider>
  );
}
