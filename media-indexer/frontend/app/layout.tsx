import type { Metadata } from "next";

import { AuthProvider } from "@/components/auth-provider";
import { ModuleRegistryProvider } from "@/components/module-registry-provider";
import { SettingsProvider } from "@/components/settings-provider";
import { ToastProvider } from "@/components/use-toast";
import { ToastContainer } from "@/components/ToastContainer";

import "./globals.css";

export const metadata: Metadata = {
  title: "Media Indexer",
  description: "Search, compare, and review indexed media from approved roots.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <SettingsProvider>
          <ToastProvider>
            <AuthProvider>
              <ModuleRegistryProvider>{children}</ModuleRegistryProvider>
            </AuthProvider>
            <ToastContainer />
          </ToastProvider>
        </SettingsProvider>
      </body>
    </html>
  );
}
