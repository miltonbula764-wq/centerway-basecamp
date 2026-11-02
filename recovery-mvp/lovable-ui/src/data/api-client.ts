// UI-facing data port. Built on top of an L01Transport (mock now, HTTP in L03).
import type { ActivityVM, ContractVM, CustomerVM, DecisionVM, InvestigationVM, OverviewKpis, RecoveryVM } from "@/domain/types";

export interface CenterwayApiClient {
  readonly mode: "demo" | "live";
  getOverviewKpis(): Promise<OverviewKpis>;
  listCustomers(): Promise<CustomerVM[]>;
  getCustomer(id: string): Promise<CustomerVM | null>;
  listContracts(): Promise<ContractVM[]>;
  listInvestigations(): Promise<InvestigationVM[]>;
  listDecisions(): Promise<DecisionVM[]>;
  listRecoveries(): Promise<RecoveryVM[]>;
  listActivities(): Promise<ActivityVM[]>;
}

