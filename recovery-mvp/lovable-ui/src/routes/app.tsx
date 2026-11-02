import { Outlet, createFileRoute } from "@tanstack/react-router";
import { LiveBoundary } from "@/components/cw/live-session";
import { AppShell } from "@/components/cw/app-shell";
import { BackToOverview, ErrorStateFrom, LoadingState } from "@/components/cw/states";

export const Route = createFileRoute("/app")({
  ssr: false,
  component: () => (
    <AppShell>
      <LiveBoundary><Outlet /></LiveBoundary>
    </AppShell>
  ),
  pendingComponent: () => (
    <AppShell>
      <LoadingState />
    </AppShell>
  ),
  errorComponent: ({ error }) => (
    <AppShell>
      <LiveBoundary><ErrorStateFrom error={error} action={<BackToOverview />} /></LiveBoundary>
    </AppShell>
  ),
});

