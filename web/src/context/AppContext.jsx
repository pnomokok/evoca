import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';

const AppContext = createContext();

export function AppProvider({ children }) {
  const [activeTab, setActiveTab] = useState('panel'); // 'device' | 'panel' | 'gathering'
  const [panelSubTab, setPanelSubTab] = useState('feed'); // 'feed' | 'lifeline' | 'story'
  const [selectedStoryId, setSelectedStoryId] = useState(null);
  const [currentViewerId, setCurrentViewerId] = useState(apiClient.currentViewerId);
  const [useMock, setUseMock] = useState(apiClient.useMock);

  const [peopleList, setPeopleList] = useState([]);
  const [centerPersonId, setCenterPersonId] = useState(null);
  const [circleData, setCircleData] = useState(null);
  const [invitationData, setInvitationData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3800);
  };

  const loadInitialData = useCallback(async () => {
    try {
      setLoading(true);

      // 1. Fetch people list (no header required, demo password-less picker)
      const people = await apiClient.getPeople();
      setPeopleList(people || []);

      // 2. Identify the center person (role == "center")
      let centerId = null;
      for (const p of people || []) {
        if (p.circles?.some(c => c.role === 'center')) {
          centerId = p.id;
          break;
        }
      }
      setCenterPersonId(centerId);

      // 3. Validate current viewer ID from localStorage against people list
      let validViewerId = apiClient.currentViewerId;
      const isKnown = people?.some(p => p.id === validViewerId);
      if (!isKnown && people && people.length > 0) {
        // Reset to first member (preferably role == "member" like Elif, or first)
        const preferred = people.find(p => p.circles?.some(c => c.role === 'member')) || people[0];
        validViewerId = preferred.id;
        apiClient.setViewer(validViewerId);
        setCurrentViewerId(validViewerId);
      } else if (!validViewerId && people && people.length > 0) {
        validViewerId = people[0].id;
        apiClient.setViewer(validViewerId);
        setCurrentViewerId(validViewerId);
      }

      // 4. Load circle and device invitation with verified viewer ID
      const [circle, invitation] = await Promise.all([
        apiClient.getCircle(),
        apiClient.getDeviceInvitation(centerId)
      ]);
      setCircleData(circle);
      setInvitationData(invitation);

      // Default center ID from circle if not yet found
      if (!centerId && circle?.circle?.center_person_id) {
        setCenterPersonId(circle.circle.center_person_id);
      }
    } catch (err) {
      console.error("Failed to load initial Evoca data", err);
      showToast(err.message || "Backend bağlantısı kurulamadı.", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData, useMock]);

  // When viewer changes, reload circle data
  const switchViewer = async (personId) => {
    apiClient.setViewer(personId);
    setCurrentViewerId(personId);
    try {
      const circle = await apiClient.getCircle();
      setCircleData(circle);
      const personName = circle?.me?.name || peopleList.find(p => p.id === personId)?.name || 'Kullanıcı';
      showToast(`Görünüm: ${personName}`, 'info');
    } catch (err) {
      console.error(err);
      showToast(err.message || "Kullanıcı değiştirilemedi", "error");
    }
  };

  const toggleMock = (flag) => {
    apiClient.setUseMock(flag);
    setUseMock(flag);
    showToast(flag ? "Örnek Mock Veri Moduna Geçildi" : "Canlı Backend Moduna Geçildi", "info");
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

export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used within an AppProvider");
  return context;
}
