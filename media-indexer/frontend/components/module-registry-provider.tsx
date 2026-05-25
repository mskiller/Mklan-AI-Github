"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { fetchModuleRegistry } from "@/lib/api";
import { PlatformModule } from "@/lib/types";

type ModuleRegistryContextValue = {
  modules: PlatformModule[];
  visibleUserModules: PlatformModule[];
  visibleAdminModules: PlatformModule[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  getModule: (moduleId: string) => PlatformModule | undefined;
  isModuleEnabled: (moduleId: string) => boolean;
};

const ModuleRegistryContext = createContext<ModuleRegistryContextValue | undefined>(undefined);

function sortByNavigation(left: PlatformModule, right: PlatformModule) {
  const leftOrder = left.user_visible ? left.nav_order : left.admin_nav_order;
  const rightOrder = right.user_visible ? right.nav_order : right.admin_nav_order;
  return leftOrder - rightOrder || left.name.localeCompare(right.name);
}

export function ModuleRegistryProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [modules, setModules] = useState<PlatformModule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    if (!user) {
      setModules([]);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const nextModules = await fetchModuleRegistry();
      setModules(nextModules);
      setError(null);
    } catch (nextError) {
      setModules([]);
      setError(nextError instanceof Error ? nextError.message : "Unable to load module registry.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authLoading) {
      return;
    }
    void refresh();
  }, [authLoading, user?.id, user?.role]);

  const visibleUserModules = modules
    .filter((item) => item.user_visible)
    .slice()
    .sort((left, right) => left.nav_order - right.nav_order || left.name.localeCompare(right.name));
  const visibleAdminModules = modules
    .filter((item) => item.admin_visible)
    .slice()
    .sort((left, right) => sortByNavigation(left, right));

  return (
    <ModuleRegistryContext.Provider
      value={{
        modules,
        visibleUserModules,
        visibleAdminModules,
        loading,
        error,
        refresh,
        getModule: (moduleId: string) => modules.find((item) => item.module_id === moduleId),
        isModuleEnabled: (moduleId: string) => modules.some((item) => item.module_id === moduleId && item.enabled && item.status === "active"),
      }}
    >
      {children}
    </ModuleRegistryContext.Provider>
  );
}

export function useModuleRegistry() {
  const context = useContext(ModuleRegistryContext);
  if (!context) {
    throw new Error("useModuleRegistry must be used inside ModuleRegistryProvider");
  }
  return context;
}
