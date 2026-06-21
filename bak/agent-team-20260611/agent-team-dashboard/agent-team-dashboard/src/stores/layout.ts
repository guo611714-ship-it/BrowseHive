import { create } from 'zustand';

const STORAGE_PREFIX = 'dashboard-';

const STORAGE_KEYS = {
  sidebarWidth: `${STORAGE_PREFIX}sidebar-width`,
  logWidth: `${STORAGE_PREFIX}log-width`,
  sidebarCollapsed: `${STORAGE_PREFIX}sidebar-collapsed`,
  mainCollapsed: `${STORAGE_PREFIX}main-collapsed`,
  logCollapsed: `${STORAGE_PREFIX}log-collapsed`,
  headerCollapsed: `${STORAGE_PREFIX}header-collapsed`,
};

function loadState<T>(key: string, defaultValue: T): T {
  try {
    const stored = localStorage.getItem(key);
    return stored !== null ? JSON.parse(stored) : defaultValue;
  } catch {
    return defaultValue;
  }
}

function saveState<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 忽略存储错误
  }
}

interface LayoutState {
  sidebarWidth: number;
  logWidth: number;
  sidebarCollapsed: boolean;
  mainCollapsed: boolean;
  logCollapsed: boolean;
  headerCollapsed: boolean;

  setSidebarWidth: (width: number) => void;
  setLogWidth: (width: number) => void;
  toggleSidebar: () => void;
  toggleMain: () => void;
  toggleLog: () => void;
  toggleHeader: () => void;
  resetLayout: () => void;
}

const DEFAULTS = {
  sidebarWidth: 280,
  logWidth: 320,
  sidebarCollapsed: false,
  mainCollapsed: false,
  logCollapsed: false,
  headerCollapsed: false,
};

export const useLayoutStore = create<LayoutState>((set) => ({
  sidebarWidth: loadState(STORAGE_KEYS.sidebarWidth, DEFAULTS.sidebarWidth),
  logWidth: loadState(STORAGE_KEYS.logWidth, DEFAULTS.logWidth),
  sidebarCollapsed: loadState(STORAGE_KEYS.sidebarCollapsed, DEFAULTS.sidebarCollapsed),
  mainCollapsed: loadState(STORAGE_KEYS.mainCollapsed, DEFAULTS.mainCollapsed),
  logCollapsed: loadState(STORAGE_KEYS.logCollapsed, DEFAULTS.logCollapsed),
  headerCollapsed: loadState(STORAGE_KEYS.headerCollapsed, DEFAULTS.headerCollapsed),

  setSidebarWidth: (width) => {
    const clamped = Math.max(200, Math.min(400, width));
    set({ sidebarWidth: clamped, sidebarCollapsed: false });
    saveState(STORAGE_KEYS.sidebarWidth, clamped);
    saveState(STORAGE_KEYS.sidebarCollapsed, false);
  },

  setLogWidth: (width) => {
    const clamped = Math.max(200, Math.min(400, width));
    set({ logWidth: clamped, logCollapsed: false });
    saveState(STORAGE_KEYS.logWidth, clamped);
    saveState(STORAGE_KEYS.logCollapsed, false);
  },

  toggleSidebar: () =>
    set((state) => {
      const collapsed = !state.sidebarCollapsed;
      saveState(STORAGE_KEYS.sidebarCollapsed, collapsed);
      return { sidebarCollapsed: collapsed };
    }),

  toggleMain: () =>
    set((state) => {
      const collapsed = !state.mainCollapsed;
      saveState(STORAGE_KEYS.mainCollapsed, collapsed);
      return { mainCollapsed: collapsed };
    }),

  toggleLog: () =>
    set((state) => {
      const collapsed = !state.logCollapsed;
      saveState(STORAGE_KEYS.logCollapsed, collapsed);
      return { logCollapsed: collapsed };
    }),

  toggleHeader: () =>
    set((state) => {
      const collapsed = !state.headerCollapsed;
      saveState(STORAGE_KEYS.headerCollapsed, collapsed);
      return { headerCollapsed: collapsed };
    }),

  resetLayout: () => {
    set(DEFAULTS);
    Object.entries(DEFAULTS).forEach(([key, value]) => {
      saveState(STORAGE_KEYS[key as keyof typeof STORAGE_KEYS], value);
    });
  },
}));
