import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '../api/client';
import { AppContext } from './useApp';

// People, the center, a verified viewer id, then circle and invitation with that id.
// Nothing that needs X-Person-Id is requested before the stored viewer id is checked
// against GET /api/people (a stale id from another database would 403).
async function fetchInitialData() {
  const people = (await apiClient.getPeople()) || [];
  const centerId = people.find(p => p.circles?.some(c => c.role === 'center'))?.id || null;

  let viewerId = apiClient.currentViewerId;
  if (!people.some(p => p.id === viewerId)) {
    const preferred = people.find(p => p.circles?.some(c => c.role === 'member')) || people[0];
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

export function AppProvider({ children }) {
  const [activeTab, setActiveTab] = useState('panel'); // 'device' | 'panel'
  const [panelSubTab, setPanelSubTab] = useState('feed'); // 'feed' | 'lifeline' | 'story'
  const [selectedStoryId, setSelectedStoryId] = useState(null);
  const [currentViewerId, setCurrentViewerId] = useState(apiClient.currentViewerId);
  // False until the stored viewer id has been checked (see fetchInitialData).
  const [viewerReady, setViewerReady] = useState(false);
  const [useMock, setUseMock] = useState(apiClient.useMock);

  const [peopleList, setPeopleList] = useState([]);
  const [centerPersonId, setCenterPersonId] = useState(null);
  const [circleData, setCircleData] = useState(null);
  const [invitationData, setInvitationData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const toastTimerRef = useRef(null);

  const showToast = useCallback((message, type = 'info') => {
    setToast({ message, type });
    clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 3800);
  }, []);

  const applyInitialData = useCallback(({ people, centerId, viewerId, circle, invitation }) => {
    setPeopleList(people);
    setCenterPersonId(centerId || circle?.circle?.center_person_id || null);
    setCurrentViewerId(viewerId);
    setViewerReady(Boolean(viewerId));
    setCircleData(circle);
    setInvitationData(invitation);
    setLoading(false);
  }, []);

  const handleLoadError = useCallback((err) => {
    console.error("Failed to load initial Evoca data", err);
    showToast("We couldn't reach Evoca. Please try again in a moment.", "error");
    setLoading(false);
  }, [showToast]);

  const loadInitialData = useCallback(
    () => fetchInitialData().then(applyInitialData, handleLoadError),
    [applyInitialData, handleLoadError]
  );

  useEffect(() => {
    let cancelled = false;
    fetchInitialData().then(
      result => { if (!cancelled) applyInitialData(result); },
      err => { if (!cancelled) handleLoadError(err); }
    );
    return () => { cancelled = true; };
  }, [applyInitialData, handleLoadError, useMock]);

  // When the viewer changes, reload circle data
  const switchViewer = async (personId) => {
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

  const toggleMock = (flag) => {
    apiClient.setUseMock(flag);
    setViewerReady(false);
    setUseMock(apiClient.useMock);
    showToast(apiClient.useMock ? "Showing sample data" : "Showing live data", "info");
  };

  return (
    <AppContext.Provider value={{
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
      useMock,
      toggleMock,
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
