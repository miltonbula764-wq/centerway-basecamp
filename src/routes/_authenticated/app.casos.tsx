import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";
import { CaseWorkspace } from "@/components/app/case-workspace";
export const Route = createFileRoute("/_authenticated/app/casos")({
  validateSearch: z.object({ tenant: z.string().uuid().optional().catch(undefined), subject: z.string().uuid().optional().catch(undefined), case: z.string().uuid().optional().catch(undefined), configuration: z.string().uuid().optional().catch(undefined), evaluation: z.string().uuid().optional().catch(undefined), kind: z.enum(["c04","operational","legacy"]).optional().catch(undefined) }),
  head: () => ({ meta: [
    { title: "Casos e percurso MVP — CENTERWAY" },
    { name: "description", content: "Objetivos, investigações, planos, intervenções e resultados coordenados pelo Core." },
    { property: "og:title", content: "Casos e percurso MVP — CENTERWAY" },
    { property: "og:description", content: "Objetivos, investigações, planos, intervenções e resultados coordenados pelo Core." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary" },
  ] }),
  component: CaseWorkspace,
});
