import { useEffect, useState } from "react";

export type UiLanguage = "en" | "fr";
export type UiTheme = "dark" | "light";

const LANGUAGE_KEY = "mklan-studio.language";
const THEME_KEY = "mklan-studio.theme";
const CHANGE_EVENT = "mklan-studio.preferences";

function storedLanguage(): UiLanguage {
  if (typeof window === "undefined") return "en";
  return window.localStorage.getItem(LANGUAGE_KEY) === "fr" ? "fr" : "en";
}

function storedTheme(): UiTheme {
  if (typeof window === "undefined") return "dark";
  return window.localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
}

export function setUiLanguage(language: UiLanguage) {
  window.localStorage.setItem(LANGUAGE_KEY, language);
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

export function setUiTheme(theme: UiTheme) {
  window.localStorage.setItem(THEME_KEY, theme);
  document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

export function useUiPreferences() {
  const [language, setLanguageState] = useState<UiLanguage>(() => storedLanguage());
  const [theme, setThemeState] = useState<UiTheme>(() => storedTheme());

  useEffect(() => {
    const update = () => {
      const nextLanguage = storedLanguage();
      const nextTheme = storedTheme();
      setLanguageState(nextLanguage);
      setThemeState(nextTheme);
      document.documentElement.lang = nextLanguage;
      document.documentElement.dataset.theme = nextTheme;
    };
    update();
    window.addEventListener("storage", update);
    window.addEventListener(CHANGE_EVENT, update);
    return () => {
      window.removeEventListener("storage", update);
      window.removeEventListener(CHANGE_EVENT, update);
    };
  }, []);

  return {
    language,
    theme,
    setLanguage: setUiLanguage,
    setTheme: setUiTheme,
  };
}
