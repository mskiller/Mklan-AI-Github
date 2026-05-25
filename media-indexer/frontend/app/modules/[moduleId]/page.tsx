"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { useModuleRegistry } from "@/components/module-registry-provider";

export default function ModuleAliasPage() {
  const params = useParams<{ moduleId: string }>();
  const router = useRouter();
  const { getModule, loading } = useModuleRegistry();
  const moduleItem = getModule(params.moduleId);
  const canonicalMount = moduleItem?.user_mount ?? null;

  useEffect(() => {
    if (!moduleItem || !canonicalMount) {
      return;
    }
    const aliasPath = `/modules/${params.moduleId}`;
    if (canonicalMount !== aliasPath) {
      router.replace(canonicalMount);
    }
  }, [canonicalMount, moduleItem, params.moduleId, router]);

  if (loading) {
    return (
      <AppShell title="Module" description="Resolving module entrypoint.">
        <section className="panel empty-state">
          <h2>Loading module</h2>
          <p className="subdued">Checking the installed module registry.</p>
        </section>
      </AppShell>
    );
  }

  if (!moduleItem) {
    return (
      <AppShell title="Module Not Found" description="The requested module is not installed.">
        <section className="panel empty-state">
          <h2>Unknown module</h2>
          <p className="subdued">No installed module matches {params.moduleId}.</p>
        </section>
      </AppShell>
    );
  }

  if (!moduleItem.enabled || moduleItem.status !== "active") {
    return (
      <AppShell title={moduleItem.name} description="Module status and fallback routing.">
        <section className="panel empty-state">
          <h2>{moduleItem.name} is unavailable</h2>
          <p className="subdued">{moduleItem.error ?? `Current status: ${moduleItem.status}.`}</p>
          {moduleItem.admin_mount ? (
            <p>
              <Link href={moduleItem.admin_mount} className="button small-button">Open Admin Module</Link>
            </p>
          ) : null}
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell title={moduleItem.name} description="Standardized module route alias.">
      <section className="panel empty-state">
        <h2>{moduleItem.name}</h2>
        <p className="subdued">Redirecting to the module surface.</p>
        {canonicalMount ? <Link href={canonicalMount} className="button small-button">Continue</Link> : null}
      </section>
    </AppShell>
  );
}
