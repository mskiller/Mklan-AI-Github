"use client";

import { ReactNode, useState } from "react";

interface Tab {
  id: string;
  label: string;
  icon?: string;
}

interface DetailTabsProps {
  tabs: Tab[];
  children: (activeTabId: string) => ReactNode;
}

export function DetailTabs({ tabs, children }: DetailTabsProps) {
  const [activeTab, setActiveTab] = useState(tabs[0]?.id || "");

  return (
    <div className="detail-tabs-container stack">
      <nav className="detail-tabs-nav">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`detail-tab-btn ${activeTab === tab.id ? "detail-tab-active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon && <span className="tab-icon">{tab.icon}</span>}
            {tab.label}
          </button>
        ))}
      </nav>
      <div className="detail-tab-content">
        {children(activeTab)}
      </div>
    </div>
  );
}
