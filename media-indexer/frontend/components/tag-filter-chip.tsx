"use client";

import { usePathname, useRouter } from "next/navigation";

import { appendTagFilter, buildSearchQuery, parseSearchFilterState } from "@/lib/search-filters";

export function TagFilterChip({
  tag,
  prompt,
  className = "",
}: {
  tag: string;
  prompt?: boolean;
  className?: string;
}) {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <button
      type="button"
      className={className || `chip ${prompt ? "chip-prompt" : ""}`}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (pathname === "/search") {
          const nextFilters = parseSearchFilterState(new URLSearchParams(window.location.search));
          nextFilters.tags = appendTagFilter(nextFilters.tags, tag);
          const query = buildSearchQuery(nextFilters);
          router.push(`/search${query ? `?${query}` : ""}`);
          return;
        }
        const params = new URLSearchParams();
        params.set("tags", tag);
        router.push(`/search?${params.toString()}`);
      }}
      title={`Filter search by ${tag}`}
    >
      {tag}
    </button>
  );
}
