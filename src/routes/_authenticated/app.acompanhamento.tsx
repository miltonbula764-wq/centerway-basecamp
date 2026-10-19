import { createFileRoute } from "@tanstack/react-router";
import { FollowupQueue } from "@/components/app/followup-queue";
export const Route = createFileRoute("/_authenticated/app/acompanhamento")({
  component: FollowupQueue,
  head: () => ({ meta: [{ title: "Central de acompanhamento — CENTERWAY" }] }),
});
