// The app's pages and their URLs (docs/web-navigation.md). A route is
// { tab: 'landing' | 'stage' | 'panel' | 'device', subTab, storyId }; subTab only for 'panel':
// 'feed' | 'lifeline' | 'questions' | 'settings' | 'story'.

const PANEL_PATHS = {
  feed: '/archive/journal',
  lifeline: '/archive/chapters',
  questions: '/archive/questions',
  settings: '/archive/settings'
};

export const LANDING = { tab: 'landing', subTab: 'feed', storyId: null };
export const JOURNAL = { tab: 'panel', subTab: 'feed', storyId: null };

// Where a story's back button goes, and what it says.
export const BACK_LABELS = {
  feed: 'Back to the journal',
  lifeline: 'Back to life chapters',
  questions: 'Back to my questions'
};

// The same, on a phone: just the destination, so the button stays on one line.
export const BACK_SHORT = {
  feed: 'Journal',
  lifeline: 'Life chapters',
  questions: 'My questions'
};

export function pathFor(route) {
  if (route.tab === 'stage') return '/demo/loop';
  if (route.tab === 'device') return '/device';
  if (route.tab === 'panel') {
    if (route.subTab === 'story' && route.storyId) return `/archive/story/${encodeURIComponent(route.storyId)}`;
    return PANEL_PATHS[route.subTab] || PANEL_PATHS.feed;
  }
  return '/';
}

// The route for a path, or null for a path the app does not know (the stage is demo only).
export function routeFromPath(pathname, isSignedIn) {
  const path = pathname.replace(/\/+$/, '') || '/';
  if (path === '/') return LANDING;
  if (path === '/demo/loop') return isSignedIn ? null : { tab: 'stage', subTab: 'feed', storyId: null };
  if (path === '/device') return { tab: 'device', subTab: 'feed', storyId: null };
  if (path === '/archive') return JOURNAL;
  const story = /^\/archive\/story\/([^/]+)$/.exec(path);
  if (story) return { tab: 'panel', subTab: 'story', storyId: decodeURIComponent(story[1]) };
  const subTab = Object.keys(PANEL_PATHS).find(k => PANEL_PATHS[k] === path);
  return subTab ? { tab: 'panel', subTab, storyId: null } : null;
}
