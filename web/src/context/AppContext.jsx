import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';

const AppContext = createContext();

export function AppProvider({ children }) {
  const [activeTab, setActiveTab] = useState('panel'); // 'device' | 'panel' | 'gathering'
  const [panelSubTab, setPanelSubTab] = useState('feed'); // 'feed' | 'lifeline' | 'story'
  const [selectedStoryId, setSelectedStoryId] = useState('story_mulberry');
  const [currentViewerId, setCurrentViewerId] = useState(apiClient.currentViewerId);
  const [useMock, setUseMock] = useState(apiClient.useMock);

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
      const [circle, invitation] = await Promise.all([
        apiClient.getCircle(),
        apiClient.getDeviceInvitation()
      ]);
      setCircleData(circle);
      setInvitationData(invitation);
    } catch (err) {
      console.error("Failed to load initial Evoca data", err);
      showToast("Connection to backend failed. Using local samples.", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData, currentViewerId, useMock]);

  const switchViewer = (personId) => {
    apiClient.setViewer(personId);
    setCurrentViewerId(personId);
    showToast(`Viewing as ${personId.replace('person_', '').toUpperCase()}`, 'info');
  };

  const toggleMock = (flag) => {
    apiClient.setUseMock(flag);
    setUseMock(flag);
    showToast(flag ? "Switched to Mock API Samples" : "Switched to Live Backend API", "info");
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
