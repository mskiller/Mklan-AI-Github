"use client";

import { useState, useCallback, createContext, useContext, ReactNode } from "react";

export type Toast = { id: number; message: string; type: "success" | "error" };

type ToastContextType = {
  toasts: Toast[];
  push: (message: string, type?: "success" | "error") => void;
};

const ToastContext = createContext<ToastContextType | undefined>(undefined);

let _nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((message: string, type: "success" | "error" = "success") => {
    const id = _nextId++;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3500);
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, push }}>
      {children}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
