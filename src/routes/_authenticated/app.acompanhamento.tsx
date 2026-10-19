import { createFileRoute } from "@tanstack/react-router";
import { FollowupQueue } from "@/components/app/followup-queue";
export const Route = createFileRoute("/_authenticated/app/acompanhamento")({
  component: FollowupQueue,
  head: () => ({ meta: [
    { title: "Central de acompanhamento — CENTERWAY" },
    { name: "description", content: "Estados persistidos, pendências e revisão humana de avaliações e casos CENTERWAY." },
    { property: "og:title", content: "Central de acompanhamento — CENTERWAY" },
    { property: "og:description", content: "Estados persistidos, pendências e revisão humana de avaliações e casos CENTERWAY." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary" },
  ] }),
});
