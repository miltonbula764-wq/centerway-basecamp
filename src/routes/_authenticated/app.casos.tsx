import { createFileRoute } from "@tanstack/react-router";
import { CaseWorkspace } from "@/components/app/case-workspace";
export const Route = createFileRoute("/_authenticated/app/casos")({
  head: () => ({ meta: [
    { title: "Casos e percurso MVP — CENTERWAY" },
    { name: "description", content: "Objetivos, investigações, planos, intervenções e resultados coordenados pelo Core." },
  ] }),
  component: CaseWorkspace,
});
