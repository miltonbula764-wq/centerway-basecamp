import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useTenant } from "@/lib/tenant";
import {
  onboardingQuery,
  indicatorSetup,
  setupActions,
  type SetupIndicator,
} from "@/lib/onboarding";
import { translateIssue } from "@/lib/profile";
import { c02StatusLabel, translateReason, type C02Status } from "@/lib/c02";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading, NativeSelect, Panel, formatDate } from "./ui-bits";
type Target = {
  tenant?: string | undefined;
  subject?: string | undefined;
  collection?: "csv" | "api" | undefined;
};
export function OperationalOnboarding({ target }: { target: Target }) {
  const { tenant } = useTenant();
  return <Setup key={`${tenant.id}:${tenant.role}:${target.subject || ""}`} target={target} />;
}
function Setup({ target }: { target: Target }) {
  const { tenant, isAdmin, canWrite } = useTenant();
  const nav = useNavigate();
  const [clients, setClients] = useState([""]);
  const [indicators, setIndicators] = useState([""]);
  const incomplete = !!target.subject && !target.tenant;
  const mismatch = !!target.tenant && target.tenant !== tenant.id;
  const q = useQuery({
    ...onboardingQuery(
      tenant.id,
      tenant.role,
      target.tenant === tenant.id ? target.subject : undefined,
      clients.at(-1)!,
      indicators.at(-1)!,
    ),
    enabled: !mismatch && !incomplete,
  });
  if (incomplete)
    return <ErrorState message="Ligação incompleta: indique a empresa do cliente selecionado." />;
  if (mismatch)
    return (
      <ErrorState message="Esta configuração pertence a outra empresa. Selecione a empresa correta ou volte à visão geral sem os parâmetros da ligação." />
    );
  const data = q.data;
  const subject = data?.subject;
  return (
    <section
      id="configuracao-inicial"
      aria-label="Configuração operacional inicial"
      className="mb-6"
    >
      <Panel title="Da conta à primeira avaliação">
        <p className="text-sm mb-3">
          Progresso derivado dos registos persistidos. Pode sair e regressar; não são criados
          clientes, medições ou aprovações automaticamente.
        </p>
        <Button variant="secondary" disabled={q.isFetching} onClick={() => q.refetch()}>
          Atualizar configuração inicial
        </Button>
        {q.isPending && !mismatch && <Loading />}
        {q.error && (
          <ErrorState
            message={`Configuração indisponível (requer migração 0025). ${q.error.message === "subject_unavailable" ? "Cliente não encontrado nesta empresa ou sem acesso." : q.error.message}`}
            onRetry={() => q.refetch()}
          />
        )}
        {data && (
          <div className="space-y-4 mt-4 text-sm">
            <p>
              Empresa ativa: {tenant.name} ·{" "}
              {isAdmin ? "Administrador" : canWrite ? "Operador" : "Leitor"} · Consultado no
              servidor: {formatDate(data.server_now)}
            </p>
            <ol className="list-decimal pl-5 space-y-3">
              <li>
                <strong>Empresa criada/selecionada · Concluída</strong>
                <p>
                  Identidade e acesso confirmados no servidor.{" "}
                  <Link to="/app/configuracoes" className="underline">
                    Consultar equipa e convites
                  </Link>{" "}
                  ·{" "}
                  <Link to="/onboarding" className="underline">
                    Criar outra empresa
                  </Link>
                </p>
              </li>
              <li>
                <strong>
                  Promessa, indicadores e aprovação ·{" "}
                  {data.approved_profile
                    ? `Perfil aprovado v${data.approved_profile.version}`
                    : "Pendente"}
                </strong>
                {!data.approved_profile && (
                  <p>
                    {data.draft_profile
                      ? "Rascunho persistido; aguarda validação e aprovação."
                      : "Ainda não existe um perfil. Registe a promessa e indicadores documentados."}
                  </p>
                )}
                {data.draft_profile && (
                  <div>
                    <p>
                      Rascunho v{data.draft_profile.version}:{" "}
                      {data.draft_profile.issues.length
                        ? "configuração incompleta/incompatível"
                        : "validação documental do perfil sem pendências técnicas; aprovação humana necessária"}
                      .
                    </p>
                    <ul className="list-disc pl-4">
                      {data.draft_profile.issues.map((x) => (
                        <li key={x}>{translateIssue(x)}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <p>
                  {isAdmin
                    ? "Um administrador decide a aprovação."
                    : canWrite
                      ? "Pode preparar o perfil; a aprovação exige administrador."
                      : "Consulta apenas. A configuração exige administrador ou operador; a aprovação exige administrador."}
                </p>
                <Link to="/app/perfil" className="underline">
                  Abrir promessa, indicadores e aprovação
                </Link>
                <p className="text-xs">
                  Perfil aprovado não demonstra valor nem compatibilidade de um objetivo individual.
                </p>
              </li>
              <li>
                <strong>Cliente acompanhado · {subject ? "Registo persistido" : "Pendente"}</strong>
                <label className="block mt-2">
                  Cliente da configuração
                  <NativeSelect
                    aria-label="Cliente da configuração"
                    value={subject?.id || ""}
                    onChange={(e) =>
                      nav({
                        to: "/app",
                        search: {
                          tenant: tenant.id,
                          subject: e.target.value,
                          collection: target.collection,
                        },
                      })
                    }
                  >
                    <option value="" disabled>
                      Ainda não há clientes
                    </option>
                    {subject && !data.subjects.some((s) => s.id === subject.id) && (
                      <option value={subject.id}>
                        {subject.display_name || subject.external_ref}
                      </option>
                    )}
                    {data.subjects.map((s) => (
                      <option value={s.id} key={s.id}>
                        {s.display_name || s.external_ref} · {s.external_ref}
                      </option>
                    ))}
                  </NativeSelect>
                </label>
                <div className="flex flex-wrap gap-2 my-2">
                  <Button
                    variant="secondary"
                    disabled={clients.length === 1 || q.isFetching}
                    onClick={() => setClients((x) => x.slice(0, -1))}
                  >
                    Clientes anteriores na configuração
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={!data.has_more_subjects || q.isFetching}
                    onClick={() => setClients((x) => [...x, data.subjects.at(-1)!.id])}
                  >
                    Mais clientes na configuração
                  </Button>
                </div>
                <Link to="/app/clientes" className="underline">
                  {canWrite
                    ? "Registar ou consultar cliente"
                    : "Consultar clientes · criação exige administrador ou operador"}
                </Link>
              </li>
              <li>
                <strong>Fonte de medições · Escolha uma via de recolha</strong>
                <label className="block">
                  Via de recolha
                  <NativeSelect
                    aria-label="Via de recolha"
                    value={target.collection || ""}
                    onChange={(e) =>
                      nav({
                        to: "/app",
                        search: {
                          tenant: tenant.id,
                          subject: subject?.id,
                          collection: e.target.value as "csv" | "api",
                        },
                      })
                    }
                  >
                    <option value="" disabled>
                      Selecionar CSV ou API
                    </option>
                    <option value="csv">CSV C01</option>
                    <option value="api">API C01</option>
                  </NativeSelect>
                </label>
                <p>
                  A escolha orienta a navegação; a fonte exata, unidades e cobertura continuam
                  sujeitas ao contrato C01 e ao objetivo documentado.
                </p>
                {target.collection !== "api" && (
                  <p>
                    <Link to="/app/dados" className="underline">
                      Abrir importação CSV e histórico C01
                    </Link>{" "}
                    ·{" "}
                    {canWrite
                      ? "Administrador ou operador importa dados reais documentados."
                      : "Leitor não pode importar."}
                  </p>
                )}
                {target.collection !== "csv" && (
                  <p>
                    <Link to="/app/configuracoes" className="underline">
                      Abrir credenciais e instruções da API C01
                    </Link>{" "}
                    ·{" "}
                    {isAdmin
                      ? "Crie uma credencial e use o endpoint instalado."
                      : "Criar ou revogar credenciais exige administrador."}
                  </p>
                )}
              </li>
            </ol>
            {!subject && (
              <p>
                Próxima etapa: registar o primeiro cliente. Sem cliente não há objetivo, observações
                ou avaliação individual.
              </p>
            )}
            {!data.approved_profile && (
              <p>
                Próxima etapa: completar o perfil e solicitar aprovação humana. Os objetivos C04
                exigem um indicador de resultado aprovado.
              </p>
            )}
            {data.approved_profile && !data.indicators.length && (
              <p>
                Sem indicadores de resultado nesta página. Consulte o perfil ou volte aos
                indicadores anteriores.
              </p>
            )}
            {subject &&
              data.indicators.map((i) => <IndicatorProgress key={i.indicator_key} item={i} />)}
            <div className="flex flex-wrap gap-3">
              <Button
                variant="secondary"
                disabled={indicators.length === 1 || q.isFetching}
                onClick={() => setIndicators((x) => x.slice(0, -1))}
              >
                Indicadores anteriores na configuração
              </Button>
              <Button
                variant="secondary"
                disabled={!data.has_more_indicators || q.isFetching}
                onClick={() => setIndicators((x) => [...x, data.indicators.at(-1)!.indicator_key])}
              >
                Mais indicadores na configuração
              </Button>
            </div>
            <Link to="/app/acompanhamento" className="underline">
              Consultar resultados e Central de Acompanhamento
            </Link>
            <p className="text-xs">
              Importação não significa melhoria. Integridade C03 não prova promessa cumprida. Uma
              avaliação C04 não abre casos automaticamente. Sem avaliação suficiente, a pendência
              mantém-se explícita.
            </p>
          </div>
        )}
      </Panel>
    </section>
  );
}
function IndicatorProgress({ item: i }: { item: SetupIndicator }) {
  const { tenant, isAdmin, canWrite } = useTenant();
  const p = indicatorSetup(i);
  const config = i.configuration;
  const a = i.evaluation;
  return (
    <article data-testid="onboarding-indicator" className="rounded border p-3 space-y-2">
      <h3 className="font-semibold">
        {i.name} · {i.indicator_key}
      </h3>
      <p>
        {p.valid
          ? "Primeira avaliação válida disponível para revisão humana"
          : "Percurso individual pendente"}
      </p>
      <p>
        Objetivo C04: {config ? `configuração v${config.version} persistida` : "não documentado"}.{" "}
        {isAdmin
          ? "Pode documentar/rever a configuração."
          : "Documentação do objetivo exige administrador."}
      </p>
      {!!config?.pending_fields.length && (
        <p>Documentação insuficiente · Campos pendentes: {config.pending_fields.join(", ")}</p>
      )}
      {config?.compatibility === "contradiction" && (
        <p>
          Contradição documentada na configuração. Rever com administrador; não iniciar intervenção
          por este motivo.
        </p>
      )}
      {config?.compatibility === "not_checkable" && (
        <p>Compatibilidade ainda não verificável; necessita revisão documental.</p>
      )}
      {i.profile_changed && (
        <p>
          O objetivo usa uma versão histórica do perfil. Rever antes de combinar com o perfil
          aprovado atual; não atualizar casos históricos automaticamente.
        </p>
      )}
      <p>
        Medições C01:{" "}
        {i.has_observations
          ? "existem registos persistidos; a quantidade não prova suficiência"
          : "ainda não existem medições para este indicador"}
        .
      </p>
      <p>
        C02:{" "}
        {i.run
          ? c02StatusLabel[i.run.status as C02Status] ||
            i.run.status ||
            "sem resultado para este indicador"
          : "análise ainda não executada"}
        .
      </p>
      {i.run &&
        !i.new_observations &&
        ["no_deterioration", "deterioration_candidate", "persistent_condition"].includes(
          i.run.status || "",
        ) && (
          <p>
            Dados suficientes segundo a análise C02 persistida. A suficiência para o objetivo
            continua dependente de C03/C04.
          </p>
        )}
      {!!i.run?.reasons?.length && (
        <ul className="list-disc pl-5">
          {i.run.reasons.map((r, n) => (
            <li key={n}>{translateReason(r)}</li>
          ))}
        </ul>
      )}
      <p>
        C03:{" "}
        {i.bundle
          ? i.bundle.status === "complete"
            ? "evidência íntegra e completa para este indicador; ainda não prova valor"
            : "evidência insuficiente ou indisponível para este indicador"
          : "pacote ainda não construído para a última análise"}
        .
      </p>
      {i.bundle?.reasons?.length ? <p>Fundamento C03: {i.bundle.reasons.join(", ")}</p> : null}
      <p>
        C04:{" "}
        {a
          ? `${a.result} · ${a.evidence} · ${a.configuration_state}`
          : "avaliação ainda não executada"}
        .
      </p>
      {a?.reasons?.length ? <p>Fundamento C04: {a.reasons.join(", ")}</p> : null}
      {p.stale && (
        <p>
          Há novas medições, uma revisão do perfil ou outro pacote. Rever atualidade; as avaliações
          históricas mantêm-se.
        </p>
      )}
      <p>
        <strong>Próxima orientação: {setupActions[p.stage]}.</strong>{" "}
        {canWrite
          ? "O servidor volta a validar os dados e permissões na operação existente."
          : "A execução C02/C03/C04 exige administrador ou operador; pode consultar os registos."}
      </p>
      <div className="flex flex-wrap gap-3">
        <Link
          to="/app/casos"
          search={{
            tenant: tenant.id,
            subject: i.subject_id!,
            kind: "c04",
            configuration: config?.id,
            evaluation: a?.id,
          }}
          hash="C04-configurable"
          className="underline"
        >
          Abrir objetivo e avaliação deste indicador
        </Link>
        <Link
          to="/app/clientes/$subjectId"
          params={{ subjectId: i.subject_id! }}
          hash="analise-e-evidencias"
          className="underline"
        >
          Abrir análise C02 e evidência C03 deste cliente
        </Link>
        <Link to="/app/dados" className="underline">
          Fornecer ou corrigir medições C01
        </Link>
      </div>
    </article>
  );
}
