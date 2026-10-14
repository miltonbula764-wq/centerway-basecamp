import { createFileRoute, redirect } from "@tanstack/react-router";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "CENTERWAY" },
      { name: "description", content: "CENTERWAY — acompanhe a realização de valor de cada cliente." },
      { property: "og:title", content: "CENTERWAY" },
      { property: "og:description", content: "Acompanhe a realização de valor de cada cliente." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  beforeLoad: async () => {
    const { data } = await supabase.auth.getSession();
    throw redirect({ to: data.session ? "/app" : "/auth", replace: true });
  },
  component: () => null,
});
