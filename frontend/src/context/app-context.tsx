"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { api } from "@/lib/api";

interface AppContextType {
  activeJDId: string | null;
  setActiveJDId: (id: string | null) => void;
  jobDescriptions: { id: string; title: string; created_at: string }[];
  refreshJDs: () => Promise<void>;
  backendConnected: boolean;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [activeJDId, setActiveJDId] = useState<string | null>(null);
  const [jobDescriptions, setJobDescriptions] = useState<{ id: string; title: string; created_at: string }[]>([]);
  const [backendConnected, setBackendConnected] = useState(false);

  const refreshJDs = useCallback(async () => {
    try {
      const jds = await api.listJobDescriptions();
      setJobDescriptions(jds);
      setBackendConnected(true);
      setActiveJDId((prev) => prev ?? (jds.length > 0 ? jds[0].id : null));
    } catch {
      setBackendConnected(false);
    }
  }, []);

  useEffect(() => {
    refreshJDs();
    let attempts = 0;
    const interval = setInterval(() => {
      attempts += 1;
      if (attempts > 10) {
        clearInterval(interval);
        return;
      }
      refreshJDs();
    }, 2000);
    return () => clearInterval(interval);
  }, [refreshJDs]);

  return (
    <AppContext.Provider value={{ activeJDId, setActiveJDId, jobDescriptions, refreshJDs, backendConnected }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
