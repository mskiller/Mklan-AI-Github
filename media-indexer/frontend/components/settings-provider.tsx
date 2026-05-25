"use client";

import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";

type Language = "en" | "fr";
type Theme = "dark" | "light";

type SettingsContextValue = {
  nsfwVisible: boolean;
  setNsfwVisible: (visible: boolean) => void;
  language: Language;
  setLanguage: (language: Language) => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  t: (key: string) => string;
};

const SettingsContext = createContext<SettingsContextValue | undefined>(undefined);

const translations: Record<Language, Record<string, string>> = {
  en: {
    "app.name": "Media Indexer",
    dashboard: "Dashboard",
    sources: "Sources",
    "browse.indexed": "Browse Indexed",
    search: "Search",
    timeline: "Timeline",
    inbox: "Inbox",
    upload: "Upload",
    "scan.jobs": "Scan Jobs",
    admin: "Admin",
    profile: "Profile",
    home: "Home",
    indexed: "Indexed",
    "sign.out": "Sign Out",
    "show.menu": "Show Menu",
    hide: "Hide",
    close: "Close",
    back: "Back",
    "checking.session": "Checking session",
    "signed.in.as": "Signed in as",
    "nsfw.on": "NSFW: ON",
    "nsfw.off": "NSFW: OFF",
    "settings.preferences": "Preferences",
    "settings.language": "Language",
    "settings.theme": "Theme",
    "theme.dark": "Dark",
    "theme.light": "Light",
  },
  fr: {
    "app.name": "Indexeur Media",
    dashboard: "Tableau de bord",
    sources: "Sources",
    "browse.indexed": "Index parcouru",
    search: "Recherche",
    timeline: "Chronologie",
    inbox: "Boite de reception",
    upload: "Importer",
    "scan.jobs": "Scans",
    admin: "Admin",
    profile: "Profil",
    home: "Accueil",
    indexed: "Index",
    "sign.out": "Se deconnecter",
    "show.menu": "Afficher le menu",
    hide: "Masquer",
    close: "Fermer",
    back: "Retour",
    "checking.session": "Verification de la session",
    "signed.in.as": "Connecte en tant que",
    "nsfw.on": "NSFW : ON",
    "nsfw.off": "NSFW : OFF",
    "settings.preferences": "Preferences",
    "settings.language": "Langue",
    "settings.theme": "Theme",
    "theme.dark": "Sombre",
    "theme.light": "Clair",
  },
};

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [nsfwVisible, setNsfwVisibleState] = useState<boolean>(false);
  const [language, setLanguageState] = useState<Language>("en");
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem("media-indexer.nsfw-visible");
      if (stored === "true") {
        setNsfwVisibleState(true);
      }
      const storedLanguage = window.localStorage.getItem("media-indexer.language");
      if (storedLanguage === "fr" || storedLanguage === "en") {
        setLanguageState(storedLanguage);
      }
      const storedTheme = window.localStorage.getItem("media-indexer.theme");
      if (storedTheme === "light" || storedTheme === "dark") {
        setThemeState(storedTheme);
      }
    }
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    document.documentElement.lang = language;
  }, [language]);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const setNsfwVisible = (visible: boolean) => {
    setNsfwVisibleState(visible);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("media-indexer.nsfw-visible", String(visible));
    }
  };

  const setLanguage = (nextLanguage: Language) => {
    setLanguageState(nextLanguage);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("media-indexer.language", nextLanguage);
    }
  };

  const setTheme = (nextTheme: Theme) => {
    setThemeState(nextTheme);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("media-indexer.theme", nextTheme);
    }
  };

  const value = useMemo<SettingsContextValue>(
    () => ({
      nsfwVisible,
      setNsfwVisible,
      language,
      setLanguage,
      theme,
      setTheme,
      t: (key: string) => translations[language][key] ?? translations.en[key] ?? key,
    }),
    [language, nsfwVisible, theme]
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used inside SettingsProvider");
  }
  return context;
}
