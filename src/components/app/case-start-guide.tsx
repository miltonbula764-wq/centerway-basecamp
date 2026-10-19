import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";

export function CaseStartGuide({ subjectId, noSubjects }: { subjectId: string; noSubjects: boolean }) {
  const clientLink = (label: string) => subjectId ?
    <Link to="/app/clientes/$subjectId" params={{ subjectId }} className="inline-flex items-center gap-1 text-primary underline underline-offset-4">{label}<ArrowUpRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" /></Link> :
    <Link to="/app/clientes" className="inline-flex items-center gap-1 text-primary underline underline-offset-4">Escolher cliente<ArrowUpRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" /></Link>;

  return <section aria-labelledby="case-start-title" className="mb-6 border-y border-border py-5">
    <div className="max-w-3xl">
      <p className="text-xs font-medium uppercase text-primary">Preparar o primeiro caso</p>
      <h2 id="case-start-title" className="mt-2 text-lg font-semibold">Comece pelo cliente e pela evidência</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{noSubjects ? "Ainda não há clientes nem casos nesta empresa na base hospedada." : "Ainda não há casos nesta seleção."} Os seis exemplos pertencem apenas ao ambiente descartável; não estão carregados nesta base.</p>
    </div>
    <ol className="mt-5 grid gap-x-8 sm:grid-cols-2">
      <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-t border-border py-4">
        <span className="font-mono text-sm text-primary">01</span><div className="min-w-0 text-sm"><h3 className="font-medium">Registar o cliente</h3><p className="mt-1 leading-relaxed text-muted-foreground">Em Clientes, use “Novo cliente”. Administradores e operadores podem registar.</p><Link to="/app/clientes" className="mt-2 inline-block text-primary underline underline-offset-4">Abrir Clientes</Link></div>
      </li>
      <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-t border-border py-4">
        <span className="font-mono text-sm text-primary">02</span><div className="min-w-0 text-sm"><h3 className="font-medium">Configurar e aprovar o perfil</h3><p className="mt-1 leading-relaxed text-muted-foreground">Defina a promessa e os indicadores. A aprovação exige um administrador; o perfil aprovado é obrigatório para importar.</p><Link to="/app/perfil" className="mt-2 inline-block text-primary underline underline-offset-4">Abrir Perfil de valor</Link></div>
      </li>
      <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-t border-border py-4">
        <span className="font-mono text-sm text-primary">03</span><div className="min-w-0 text-sm"><h3 className="font-medium">C01 · Importar observações</h3><p className="mt-1 leading-relaxed text-muted-foreground">Importe o CSV em Dados, com a referência exata do cliente e indicadores do perfil aprovado.</p><Link to="/app/dados" className="mt-2 inline-block text-primary underline underline-offset-4">Abrir Dados</Link></div>
      </li>
      <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-t border-border py-4">
        <span className="font-mono text-sm text-primary">04</span><div className="min-w-0 text-sm"><h3 className="font-medium">C02 · Analisar as medições</h3><p className="mt-1 leading-relaxed text-muted-foreground">No detalhe do cliente, use “Analisar agora” e selecione a análise histórica. Um sinal candidato não abre um caso.</p><div className="mt-2">{clientLink("Abrir análise do cliente")}</div></div>
      </li>
      <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-t border-border py-4">
        <span className="font-mono text-sm text-primary">05</span><div className="min-w-0 text-sm"><h3 className="font-medium">C03 · Montar o pacote</h3><p className="mt-1 leading-relaxed text-muted-foreground">Na análise escolhida, um administrador ou operador pode montar explicitamente o pacote. Evidência íntegra não prova recuperação nem causa.</p><div className="mt-2">{clientLink("Abrir evidência do cliente")}</div></div>
      </li>
      <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-t border-border py-4">
        <span className="font-mono text-sm text-primary">06</span><div className="min-w-0 text-sm"><h3 className="font-medium">C04 · Voltar a Casos</h3><p className="mt-1 leading-relaxed text-muted-foreground">Selecione o cliente, configure a avaliação do indicador e avalie o pacote C03. Só uma avaliação elegível, com decisão documentada de administrador, abre um caso operacional.</p><a href="#case-client" className="mt-2 inline-block text-primary underline underline-offset-4">Ir para a escolha de cliente</a></div>
      </li>
    </ol>
  </section>;
}