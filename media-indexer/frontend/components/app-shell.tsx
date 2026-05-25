"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { useModuleRegistry } from "@/components/module-registry-provider";
import { useSettings } from "@/components/settings-provider";
import { useDeviceMode } from "@/hooks/use-device-mode";

function BackButton({ className = "" }: { className?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useSettings();
  // Don't show on root/dashboard
  if (pathname === "/") return null;
  return (
    <button
      type="button"
      className={`button ghost-button small-button ${className}`.trim()}
      onClick={() => router.back()}
      aria-label="Go back"
    >
      ← {t("back")}
    </button>
  );
}

export function AppShell({
  title,
  description,
  children,
  actions,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const { visibleUserModules } = useModuleRegistry();
  const { nsfwVisible, setNsfwVisible, t } = useSettings();
  const deviceMode = useDeviceMode();
  const [navOpen, setNavOpen] = useState(false);
  const [desktopNavCollapsed, setDesktopNavCollapsed] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, router, user]);

  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    setDesktopNavCollapsed(window.localStorage.getItem("media-indexer.desktop-nav-collapsed") === "true");
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("media-indexer.desktop-nav-collapsed", String(desktopNavCollapsed));
  }, [desktopNavCollapsed]);

  useEffect(() => {
    if (!navOpen) {
      document.body.style.overflow = "";
      return;
    }
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [navOpen]);

  if (loading || !user) {
    return (
      <main className="screen-center">
        <div className="panel soft-panel">
          <p className="eyebrow">Media Indexer</p>
          <h1>{t("checking.session")}</h1>
        </div>
      </main>
    );
  }

  const moduleNavItems = visibleUserModules
    .filter((item) => item.enabled && item.status === "active" && item.nav_href && item.nav_label)
    .map((item) => ({
      href: item.nav_href as string,
      label: item.nav_label as string,
      order: item.nav_order,
    }))
    .sort((left, right) => left.order - right.order || left.label.localeCompare(right.label));

  const navItems = [
    { href: "/", label: t("dashboard"), order: 0 },
    { href: "/sources", label: t("sources"), order: 10 },
    { href: "/browse-indexed", label: t("browse.indexed"), order: 20 },
    { href: "/search", label: t("search"), order: 30 },
    ...moduleNavItems,
    { href: "/timeline", label: t("timeline"), order: 80 },
    ...(user.capabilities.can_upload_assets ? [{ href: "/inbox", label: t("inbox"), order: 90 }] : []),
    ...(user.capabilities.can_upload_assets ? [{ href: "/upload", label: t("upload"), order: 100 }] : []),
    { href: "/scan-jobs", label: t("scan.jobs"), order: 110 },
    ...(user.capabilities.can_view_admin ? [{ href: "/admin", label: t("admin"), order: 120 }] : []),
    { href: "/profile", label: t("profile"), order: 130 },
  ];
  const mobileModuleItems = moduleNavItems.slice(0, 3).map((item) => ({ href: item.href, label: item.label }));
  const mobileItems = [
    { href: "/", label: t("home") },
    { href: "/sources", label: t("sources") },
    { href: "/browse-indexed", label: t("indexed") },
    { href: "/search", label: t("search") },
    ...mobileModuleItems,
    { href: "/timeline", label: t("timeline") },
  ];

  const isActive = (href: string) => {
    if (href === "/") {
      return pathname === "/";
    }
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const handleLogout = async () => {
    await logout();
    router.replace("/login");
  };

  const accountActions = (
    <>
      <Link href="/profile" className="button ghost-button small-button">
        {t("profile")}
      </Link>
      <button className="button ghost-button small-button" type="button" onClick={() => void handleLogout()}>
        {t("sign.out")}
      </button>
    </>
  );

  const nsfwAction = (
    <button
      type="button"
      className={`button small-button ${nsfwVisible ? "subtle-button" : "ghost-button"}`}
      onClick={() => setNsfwVisible(!nsfwVisible)}
      title={nsfwVisible ? "Hide NSFW content" : "Show NSFW content"}
    >
      {t(nsfwVisible ? "nsfw.on" : "nsfw.off")}
    </button>
  );

  return (
    <div className={`shell shell-${deviceMode} ${desktopNavCollapsed ? "shell-desktop-nav-collapsed" : ""} ${navOpen ? "shell-nav-open" : ""}`.trim()}>
      <div className="mobile-topbar">
        <button className="button ghost-button small-button mobile-nav-toggle" type="button" onClick={() => setNavOpen((value) => !value)}>
          {navOpen ? t("close") : "Menu"}
        </button>
        <BackButton className="mobile-back-btn" />
        <div>
          <p className="eyebrow">{t("app.name")}</p>
          <p className="mobile-topbar-title">{title}</p>
        </div>
        <div className="mobile-topbar-actions">
          <span className="pill">{user.role}</span>
          <button className="button ghost-button small-button" type="button" onClick={() => void handleLogout()}>
            {t("sign.out")}
          </button>
        </div>
      </div>
      <button
        type="button"
        aria-label="Close navigation"
        className={`shell-scrim ${navOpen ? "shell-scrim-visible" : ""}`}
        onClick={() => setNavOpen(false)}
      />
      <button
        type="button"
        aria-label="Show navigation"
        className="button ghost-button small-button desktop-nav-reveal"
        onClick={() => setDesktopNavCollapsed(false)}
      >
        {t("show.menu")}
      </button>
      <aside className={`side-nav ${navOpen ? "side-nav-open" : ""}`}>
        <div className="stack">
          <div className="side-nav-header">
            <div className="side-nav-brand">
              <p className="eyebrow">{t("app.name")}</p>
              <h2>Approved Media</h2>
            </div>
            <button
              type="button"
              className="button ghost-button small-button desktop-nav-toggle"
              onClick={() => setDesktopNavCollapsed(true)}
            >
              {t("hide")}
            </button>
          </div>
          <div className="stack account-panel">
            <div>
              <p className="asset-name">{user.username}</p>
              <p className="subdued">{t("signed.in.as")} {user.role}</p>
            </div>
            <div className="card-actions">{accountActions}</div>
          </div>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-link ${isActive(item.href) ? "nav-link-active" : ""}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="side-nav-spacer" aria-hidden="true" />
      </aside>
      <main className="content">
        <header className="page-header">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.25rem" }}>
              <BackButton />
              <p className="eyebrow" style={{ margin: 0 }}>{user.username} · {user.role}</p>
            </div>
            <h1>{title}</h1>
            {description ? <p className="subdued">{description}</p> : null}
          </div>
          <div className="page-actions">
            {nsfwAction}
            {actions}
            {accountActions}
          </div>
        </header>
        {children}
      </main>
      <nav className="mobile-bottom-nav">
        {mobileItems.map((item) => (
          <Link key={item.href} href={item.href} className={`mobile-bottom-link ${isActive(item.href) ? "mobile-bottom-link-active" : ""}`}>
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
