import { createFileRoute } from "@tanstack/react-router";
import { pageHead } from "@/lib/seo";
import { PageBar, PageIntro, Section } from "@/components/cw/primitives";
import { ErrorState, LoadingState, NoDataState, ResendSameRequest, type UiErrorKind } from "@/components/cw/states";

export const Route = createFileRoute("/app/sobre")({
  head: pageHead("Sobre esta demonstração", "Rotas, contrato F06/L01, campos só de demonstração, ecrãs de estado e limites da interface CENTERWAY."),
  component: Sobre,
});

const routes = [
  ["/app", "Visão Geral (ilustrativa)"],
  ["/app/clientes", "Clientes autorizados"],
  ["/app/clientes/:id", "Percurso F06 do cliente"],
  ["/app/contratos", "Contratos de Valor (F01)"],
  ["/app/investigacoes", "Investigações (F03)"],
  ["/app/intervencoes", "Decisões e intervenções sintéticas autorizadas"],
  ["/app/recuperacao", "Recuperação (F05)"],
];

const states: UiErrorKind[] = ["401", "403", "404", "409", "422", "503", "network"];

function Sobre() {
  return (
    <>
      <PageBar title="Sobre esta demonstração" />
      <PageIntro title="Sobre esta demonstração" description="CENTERWAY — demonstração sintética ligada à API pública. Login e dados reais da API; resultados e intervenções continuam exclusivamente sintéticos." />
      <div className="grid gap-x-10 gap-y-6 px-4 pb-10 sm:px-6 lg:grid-cols-2">
        <Section title="Rotas">
          <ul className="flex flex-col gap-2">{routes.map(([r, l]) => <li key={r} className="flex justify-between gap-3"><span className="font-mono text-xs text-primary">{r}</span><span className="text-muted-foreground">{l}</span></li>)}</ul>
        </Section>
        <Section title="Contrato de dados">
          <p className="text-muted-foreground">Os dados seguem a forma da projeção F06 <span className="font-mono">client_journey</span> (f06-v1) e do transporte L01 (sessão, journey, operations). A lista de clientes vem dos scopes da sessão; o diretório devolve nomes e IDs autorizados, com paginação.</p>
        </Section>
        <Section title="Campos só de demonstração (marcados DEMO)">
          <ul className="flex list-disc flex-col gap-1 pl-4 text-muted-foreground">
            <li>Nome: diretório da API. Segmento, plano, responsável e prioridade não são inventados.</li>
            <li>Os KPIs da Visão Geral são contagens ilustrativas sobre dados sintéticos.</li>
            <li>Não existe "cobertura" de fontes na API; a qualidade é declarada por evidência.</li>
          </ul>
        </Section>
        <Section title="Limites">
          <ul className="flex list-disc flex-col gap-1 pl-4 text-muted-foreground">
            <li>Sessão apenas em memória; atualizar a página exige novo login. Os registos persistem na API.</li>
            <li>Pedidos sintéticos exigem confirmação explícita e autorização do servidor. Formulários de criação de contratos/evidências não estão incluídos nesta integração.</li>
            <li>Nunca há repetição automática de intervenção ou reversão.</li>
            <li>Recuperação observada não comprova causalidade.</li>
          </ul>
        </Section>
        <Section title="Ecrãs de estado (pré-visualização local)" className="lg:col-span-2">
          <div className="grid gap-px overflow-hidden rounded-md border border-border-subtle bg-border-subtle sm:grid-cols-2 xl:grid-cols-3">
            <div className="bg-background"><LoadingState /></div>
            <div className="bg-background"><NoDataState>Sem dados nesta projeção.</NoDataState></div>
            {states.map((k) => (
              <div key={k} className="bg-background">
                <ErrorState kind={k} action={k === "503" || k === "network" ? <ResendSameRequest requestId="00000000-demo" /> : undefined} />
              </div>
            ))}
          </div>
        </Section>
      </div>
    </>
  );
}

