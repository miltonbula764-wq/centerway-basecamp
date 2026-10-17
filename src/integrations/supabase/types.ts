import type { Objective, Assessment, JourneyCase, CaseEvent, ReadOnlyTable } from "@/lib/journey-types";

export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.18"
  }
  public: {
    Tables: {
      cw_objectives: ReadOnlyTable<Objective>
      cw_assessments: ReadOnlyTable<Assessment>
      cw_cases: ReadOnlyTable<JourneyCase>
      cw_case_events: ReadOnlyTable<CaseEvent>
      audit_log: {
        Row: {
          action: string
          actor_id: string | null
          created_at: string
          details: Json
          entity_id: string | null
          entity_type: string
          id: number
          tenant_id: string | null
        }
        Insert: {
          action: string
          actor_id?: string | null
          created_at?: string
          details?: Json
          entity_id?: string | null
          entity_type: string
          id?: never
          tenant_id?: string | null
        }
        Update: {
          action?: string
          actor_id?: string | null
          created_at?: string
          details?: Json
          entity_id?: string | null
          entity_type?: string
          id?: never
          tenant_id?: string | null
        }
        Relationships: []
      }
      c02_results: {
        Row: {
          baseline_value: number | null
          below_target: boolean | null
          classification: Database["public"]["Enums"]["indicator_class"]
          created_at: string
          details: Json
          id: string
          indicator_key: string
          observation_ids: string[]
          reasons: string[]
          run_id: string
          status: Database["public"]["Enums"]["c02_status"]
          subject_id: string
          tenant_id: string
        }
        Insert: {
          baseline_value?: number | null
          below_target?: boolean | null
          classification: Database["public"]["Enums"]["indicator_class"]
          created_at?: string
          details: Json
          id?: string
          indicator_key: string
          observation_ids?: string[]
          reasons?: string[]
          run_id: string
          status: Database["public"]["Enums"]["c02_status"]
          subject_id: string
          tenant_id: string
        }
        Update: {
          baseline_value?: number | null
          below_target?: boolean | null
          classification?: Database["public"]["Enums"]["indicator_class"]
          created_at?: string
          details?: Json
          id?: string
          indicator_key?: string
          observation_ids?: string[]
          reasons?: string[]
          run_id?: string
          status?: Database["public"]["Enums"]["c02_status"]
          subject_id?: string
          tenant_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "c02_results_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "c02_results_tenant_id_run_id_fkey"
            columns: ["tenant_id", "run_id"]
            isOneToOne: false
            referencedRelation: "c02_runs"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "c02_results_tenant_id_subject_id_fkey"
            columns: ["tenant_id", "subject_id"]
            isOneToOne: false
            referencedRelation: "subjects"
            referencedColumns: ["tenant_id", "id"]
          },
        ]
      }
      c02_runs: {
        Row: {
          algorithm_version: string
          as_of: string
          created_at: string
          created_by: string | null
          data_cutoff: string
          id: string
          input_hash: string
          observation_count: number
          profile_id: string
          profile_version: number
          revision_of: string | null
          subject_id: string
          summary: Json
          tenant_id: string
        }
        Insert: {
          algorithm_version: string
          as_of: string
          created_at?: string
          created_by?: string | null
          data_cutoff: string
          id?: string
          input_hash: string
          observation_count: number
          profile_id: string
          profile_version: number
          revision_of?: string | null
          subject_id: string
          summary: Json
          tenant_id: string
        }
        Update: {
          algorithm_version?: string
          as_of?: string
          created_at?: string
          created_by?: string | null
          data_cutoff?: string
          id?: string
          input_hash?: string
          observation_count?: number
          profile_id?: string
          profile_version?: number
          revision_of?: string | null
          subject_id?: string
          summary?: Json
          tenant_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "c02_runs_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "c02_runs_tenant_id_profile_id_fkey"
            columns: ["tenant_id", "profile_id"]
            isOneToOne: false
            referencedRelation: "tenant_value_profiles"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "c02_runs_tenant_id_revision_of_fkey"
            columns: ["tenant_id", "revision_of"]
            isOneToOne: false
            referencedRelation: "c02_runs"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "c02_runs_tenant_id_subject_id_fkey"
            columns: ["tenant_id", "subject_id"]
            isOneToOne: false
            referencedRelation: "subjects"
            referencedColumns: ["tenant_id", "id"]
          },
        ]
      }
      c03_attempts: {
        Row: {
          actor_id: string | null
          algorithm_version: string
          bundle_id: string | null
          code: string | null
          created_at: string
          id: string
          requested_run_id: string
          status: Database["public"]["Enums"]["c03_attempt_status"]
          tenant_id: string
        }
        Insert: {
          actor_id?: string | null
          algorithm_version: string
          bundle_id?: string | null
          code?: string | null
          created_at?: string
          id?: string
          requested_run_id: string
          status: Database["public"]["Enums"]["c03_attempt_status"]
          tenant_id: string
        }
        Update: {
          actor_id?: string | null
          algorithm_version?: string
          bundle_id?: string | null
          code?: string | null
          created_at?: string
          id?: string
          requested_run_id?: string
          status?: Database["public"]["Enums"]["c03_attempt_status"]
          tenant_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "c03_attempts_tenant_id_bundle_id_fkey"
            columns: ["tenant_id", "bundle_id"]
            isOneToOne: false
            referencedRelation: "c03_bundles"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "c03_attempts_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
        ]
      }
      c03_bundles: {
        Row: {
          algorithm_version: string
          c02_algorithm_version: string
          c02_input_hash: string
          content_hash: string
          created_at: string
          created_by: string | null
          data_cutoff: string
          id: string
          revision_of: string | null
          run_id: string
          subject_id: string
          summary: Json
          tenant_id: string
        }
        Insert: {
          algorithm_version: string
          c02_algorithm_version: string
          c02_input_hash: string
          content_hash: string
          created_at?: string
          created_by?: string | null
          data_cutoff: string
          id?: string
          revision_of?: string | null
          run_id: string
          subject_id: string
          summary: Json
          tenant_id: string
        }
        Update: {
          algorithm_version?: string
          c02_algorithm_version?: string
          c02_input_hash?: string
          content_hash?: string
          created_at?: string
          created_by?: string | null
          data_cutoff?: string
          id?: string
          revision_of?: string | null
          run_id?: string
          subject_id?: string
          summary?: Json
          tenant_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "c03_bundles_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "c03_bundles_tenant_id_revision_of_fkey"
            columns: ["tenant_id", "revision_of"]
            isOneToOne: false
            referencedRelation: "c03_bundles"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "c03_bundles_tenant_id_subject_id_fkey"
            columns: ["tenant_id", "subject_id"]
            isOneToOne: false
            referencedRelation: "subjects"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "c03_bundles_tenant_id_subject_id_run_id_fkey"
            columns: ["tenant_id", "subject_id", "run_id"]
            isOneToOne: false
            referencedRelation: "c02_runs"
            referencedColumns: ["tenant_id", "subject_id", "id"]
          },
        ]
      }
      c03_indicators: {
        Row: {
          bundle_id: string
          c02_result_id: string
          created_at: string
          id: string
          indicator_key: string
          reasons: string[]
          ref_budget: number
          ref_count: number
          snapshot: Json
          status: Database["public"]["Enums"]["c03_indicator_status"]
          stored_ref_count: number
          tenant_id: string
        }
        Insert: {
          bundle_id: string
          c02_result_id: string
          created_at?: string
          id?: string
          indicator_key: string
          reasons?: string[]
          ref_budget: number
          ref_count: number
          snapshot: Json
          status: Database["public"]["Enums"]["c03_indicator_status"]
          stored_ref_count: number
          tenant_id: string
        }
        Update: {
          bundle_id?: string
          c02_result_id?: string
          created_at?: string
          id?: string
          indicator_key?: string
          reasons?: string[]
          ref_budget?: number
          ref_count?: number
          snapshot?: Json
          status?: Database["public"]["Enums"]["c03_indicator_status"]
          stored_ref_count?: number
          tenant_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "c03_indicators_c02_result_id_fkey"
            columns: ["c02_result_id"]
            isOneToOne: false
            referencedRelation: "c02_results"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "c03_indicators_tenant_id_bundle_id_fkey"
            columns: ["tenant_id", "bundle_id"]
            isOneToOne: false
            referencedRelation: "c03_bundles"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "c03_indicators_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
        ]
      }
      c03_refs: {
        Row: {
          bundle_id: string
          corrects_observation_id: string | null
          id: number
          indicator_id: string
          indicator_key: string
          ingested_at: string
          observation_id: string
          observed_at: string
          ordinal: number
          payload_hash: string
          role: string
          source: string
          superseded_by: string | null
          tenant_id: string
          unit: string
          value_numeric: number | null
          value_text: string | null
          window_end: string | null
          window_label: string | null
          window_start: string | null
        }
        Insert: {
          bundle_id: string
          corrects_observation_id?: string | null
          id?: never
          indicator_id: string
          indicator_key: string
          ingested_at: string
          observation_id: string
          observed_at: string
          ordinal: number
          payload_hash: string
          role: string
          source: string
          superseded_by?: string | null
          tenant_id: string
          unit: string
          value_numeric?: number | null
          value_text?: string | null
          window_end?: string | null
          window_label?: string | null
          window_start?: string | null
        }
        Update: {
          bundle_id?: string
          corrects_observation_id?: string | null
          id?: never
          indicator_id?: string
          indicator_key?: string
          ingested_at?: string
          observation_id?: string
          observed_at?: string
          ordinal?: number
          payload_hash?: string
          role?: string
          source?: string
          superseded_by?: string | null
          tenant_id?: string
          unit?: string
          value_numeric?: number | null
          value_text?: string | null
          window_end?: string | null
          window_label?: string | null
          window_start?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "c03_refs_tenant_id_bundle_id_fkey"
            columns: ["tenant_id", "bundle_id"]
            isOneToOne: false
            referencedRelation: "c03_bundles"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "c03_refs_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "c03_refs_tenant_id_indicator_id_fkey"
            columns: ["tenant_id", "indicator_id"]
            isOneToOne: false
            referencedRelation: "c03_indicators"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "c03_refs_tenant_id_observation_id_fkey"
            columns: ["tenant_id", "observation_id"]
            isOneToOne: false
            referencedRelation: "observations"
            referencedColumns: ["tenant_id", "id"]
          },
        ]
      }
      indicators: {
        Row: {
          baseline: number | null
          created_at: string
          definition: string | null
          deterioration_threshold: number | null
          direction: Database["public"]["Enums"]["indicator_direction"]
          evaluation_window_days: number | null
          id: string
          key: string
          min_denominator: number | null
          name: string
          target: number | null
          tenant_id: string
          unit: string
          updated_at: string
          value_profile_id: string
        }
        Insert: {
          baseline?: number | null
          created_at?: string
          definition?: string | null
          deterioration_threshold?: number | null
          direction: Database["public"]["Enums"]["indicator_direction"]
          evaluation_window_days?: number | null
          id?: string
          key: string
          min_denominator?: number | null
          name: string
          target?: number | null
          tenant_id: string
          unit: string
          updated_at?: string
          value_profile_id: string
        }
        Update: {
          baseline?: number | null
          created_at?: string
          definition?: string | null
          deterioration_threshold?: number | null
          direction?: Database["public"]["Enums"]["indicator_direction"]
          evaluation_window_days?: number | null
          id?: string
          key?: string
          min_denominator?: number | null
          name?: string
          target?: number | null
          tenant_id?: string
          unit?: string
          updated_at?: string
          value_profile_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "indicators_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "indicators_tenant_id_value_profile_id_fkey"
            columns: ["tenant_id", "value_profile_id"]
            isOneToOne: false
            referencedRelation: "value_profiles"
            referencedColumns: ["tenant_id", "id"]
          },
        ]
      }
      ingestion_batches: {
        Row: {
          committed_at: string | null
          contract_snapshot: Json | null
          coverage_declared: boolean
          coverage_end: string | null
          coverage_start: string | null
          coverage_timezone: string
          created_at: string
          created_by: string | null
          duplicate_count: number
          errors: Json
          file_name: string | null
          id: string
          inserted_count: number
          notes: string | null
          profile_id: string | null
          profile_version: number | null
          rejected_count: number
          row_count: number
          source: string
          status: Database["public"]["Enums"]["batch_status"]
          tenant_id: string
          updated_at: string
        }
        Insert: {
          committed_at?: string | null
          contract_snapshot?: Json | null
          coverage_declared?: boolean
          coverage_end?: string | null
          coverage_start?: string | null
          coverage_timezone?: string
          created_at?: string
          created_by?: string | null
          duplicate_count?: number
          errors?: Json
          file_name?: string | null
          id?: string
          inserted_count?: number
          notes?: string | null
          profile_id?: string | null
          profile_version?: number | null
          rejected_count?: number
          row_count?: number
          source: string
          status?: Database["public"]["Enums"]["batch_status"]
          tenant_id: string
          updated_at?: string
        }
        Update: {
          committed_at?: string | null
          contract_snapshot?: Json | null
          coverage_declared?: boolean
          coverage_end?: string | null
          coverage_start?: string | null
          coverage_timezone?: string
          created_at?: string
          created_by?: string | null
          duplicate_count?: number
          errors?: Json
          file_name?: string | null
          id?: string
          inserted_count?: number
          notes?: string | null
          profile_id?: string | null
          profile_version?: number | null
          rejected_count?: number
          row_count?: number
          source?: string
          status?: Database["public"]["Enums"]["batch_status"]
          tenant_id?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "batches_profile_fkey"
            columns: ["tenant_id", "profile_id"]
            isOneToOne: false
            referencedRelation: "tenant_value_profiles"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "ingestion_batches_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
        ]
      }
      memberships: {
        Row: {
          created_at: string
          id: string
          role: Database["public"]["Enums"]["member_role"]
          tenant_id: string
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          role: Database["public"]["Enums"]["member_role"]
          tenant_id: string
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          role?: Database["public"]["Enums"]["member_role"]
          tenant_id?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "memberships_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
        ]
      }
      observations: {
        Row: {
          batch_id: string
          corrects_observation_id: string | null
          created_by: string | null
          id: string
          idempotency_key: string
          indicator_key: string
          ingested_at: string
          observed_at: string
          payload: Json
          payload_hash: string
          source: string
          subject_id: string
          tenant_id: string
          unit: string
          value_numeric: number | null
          value_text: string | null
        }
        Insert: {
          batch_id: string
          corrects_observation_id?: string | null
          created_by?: string | null
          id?: string
          idempotency_key: string
          indicator_key: string
          ingested_at?: string
          observed_at: string
          payload?: Json
          payload_hash?: string
          source: string
          subject_id: string
          tenant_id: string
          unit: string
          value_numeric?: number | null
          value_text?: string | null
        }
        Update: {
          batch_id?: string
          corrects_observation_id?: string | null
          created_by?: string | null
          id?: string
          idempotency_key?: string
          indicator_key?: string
          ingested_at?: string
          observed_at?: string
          payload?: Json
          payload_hash?: string
          source?: string
          subject_id?: string
          tenant_id?: string
          unit?: string
          value_numeric?: number | null
          value_text?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "observations_tenant_id_batch_id_fkey"
            columns: ["tenant_id", "batch_id"]
            isOneToOne: false
            referencedRelation: "ingestion_batches"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "observations_tenant_id_corrects_observation_id_fkey"
            columns: ["tenant_id", "corrects_observation_id"]
            isOneToOne: false
            referencedRelation: "observations"
            referencedColumns: ["tenant_id", "id"]
          },
          {
            foreignKeyName: "observations_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "observations_tenant_id_subject_id_fkey"
            columns: ["tenant_id", "subject_id"]
            isOneToOne: false
            referencedRelation: "subjects"
            referencedColumns: ["tenant_id", "id"]
          },
        ]
      }
      profile_indicators: {
        Row: {
          aggregation: Database["public"]["Enums"]["c02_aggregation"] | null
          baseline_method: Database["public"]["Enums"]["baseline_method"] | null
          baseline_min_period_days: number | null
          baseline_value: number | null
          classification: Database["public"]["Enums"]["indicator_class"]
          comparison_window_days: number | null
          created_at: string
          definition: string | null
          denominator_indicator_key: string | null
          denominator_mode:
            | Database["public"]["Enums"]["c02_denominator_mode"]
            | null
          deterioration_consecutive_windows: number | null
          deterioration_kind: Database["public"]["Enums"]["rule_kind"] | null
          deterioration_operator:
            | Database["public"]["Enums"]["rule_operator"]
            | null
          deterioration_value: number | null
          direction: Database["public"]["Enums"]["indicator_direction"]
          expected_cadence_days: number | null
          id: string
          key: string
          min_coverage_pct: number | null
          min_denominator: number | null
          name: string
          observation_window_days: number | null
          profile_id: string
          recovery_consecutive_windows: number | null
          recovery_kind: Database["public"]["Enums"]["rule_kind"] | null
          recovery_operator: Database["public"]["Enums"]["rule_operator"] | null
          recovery_value: number | null
          target_value: number | null
          tenant_id: string
          unit: string
          updated_at: string
          value_type: Database["public"]["Enums"]["indicator_value_type"]
        }
        Insert: {
          aggregation?: Database["public"]["Enums"]["c02_aggregation"] | null
          baseline_method?:
            | Database["public"]["Enums"]["baseline_method"]
            | null
          baseline_min_period_days?: number | null
          baseline_value?: number | null
          classification: Database["public"]["Enums"]["indicator_class"]
          comparison_window_days?: number | null
          created_at?: string
          definition?: string | null
          denominator_indicator_key?: string | null
          denominator_mode?:
            | Database["public"]["Enums"]["c02_denominator_mode"]
            | null
          deterioration_consecutive_windows?: number | null
          deterioration_kind?: Database["public"]["Enums"]["rule_kind"] | null
          deterioration_operator?:
            | Database["public"]["Enums"]["rule_operator"]
            | null
          deterioration_value?: number | null
          direction: Database["public"]["Enums"]["indicator_direction"]
          expected_cadence_days?: number | null
          id?: string
          key: string
          min_coverage_pct?: number | null
          min_denominator?: number | null
          name: string
          observation_window_days?: number | null
          profile_id: string
          recovery_consecutive_windows?: number | null
          recovery_kind?: Database["public"]["Enums"]["rule_kind"] | null
          recovery_operator?:
            | Database["public"]["Enums"]["rule_operator"]
            | null
          recovery_value?: number | null
          target_value?: number | null
          tenant_id: string
          unit: string
          updated_at?: string
          value_type?: Database["public"]["Enums"]["indicator_value_type"]
        }
        Update: {
          aggregation?: Database["public"]["Enums"]["c02_aggregation"] | null
          baseline_method?:
            | Database["public"]["Enums"]["baseline_method"]
            | null
          baseline_min_period_days?: number | null
          baseline_value?: number | null
          classification?: Database["public"]["Enums"]["indicator_class"]
          comparison_window_days?: number | null
          created_at?: string
          definition?: string | null
          denominator_indicator_key?: string | null
          denominator_mode?:
            | Database["public"]["Enums"]["c02_denominator_mode"]
            | null
          deterioration_consecutive_windows?: number | null
          deterioration_kind?: Database["public"]["Enums"]["rule_kind"] | null
          deterioration_operator?:
            | Database["public"]["Enums"]["rule_operator"]
            | null
          deterioration_value?: number | null
          direction?: Database["public"]["Enums"]["indicator_direction"]
          expected_cadence_days?: number | null
          id?: string
          key?: string
          min_coverage_pct?: number | null
          min_denominator?: number | null
          name?: string
          observation_window_days?: number | null
          profile_id?: string
          recovery_consecutive_windows?: number | null
          recovery_kind?: Database["public"]["Enums"]["rule_kind"] | null
          recovery_operator?:
            | Database["public"]["Enums"]["rule_operator"]
            | null
          recovery_value?: number | null
          target_value?: number | null
          tenant_id?: string
          unit?: string
          updated_at?: string
          value_type?: Database["public"]["Enums"]["indicator_value_type"]
        }
        Relationships: [
          {
            foreignKeyName: "profile_indicators_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "profile_indicators_tenant_id_profile_id_fkey"
            columns: ["tenant_id", "profile_id"]
            isOneToOne: false
            referencedRelation: "tenant_value_profiles"
            referencedColumns: ["tenant_id", "id"]
          },
        ]
      }
      subjects: {
        Row: {
          created_at: string
          created_by: string | null
          display_name: string | null
          external_ref: string
          id: string
          tenant_id: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          created_by?: string | null
          display_name?: string | null
          external_ref: string
          id?: string
          tenant_id: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          created_by?: string | null
          display_name?: string | null
          external_ref?: string
          id?: string
          tenant_id?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "subjects_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
        ]
      }
      tenant_value_profiles: {
        Row: {
          approved_at: string | null
          approved_by: string | null
          created_at: string
          created_by: string | null
          expected_outcome: string | null
          id: string
          notes: string | null
          promise: string
          status: Database["public"]["Enums"]["profile_status"]
          tenant_id: string
          updated_at: string
          version: number
        }
        Insert: {
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          created_by?: string | null
          expected_outcome?: string | null
          id?: string
          notes?: string | null
          promise: string
          status?: Database["public"]["Enums"]["profile_status"]
          tenant_id: string
          updated_at?: string
          version: number
        }
        Update: {
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          created_by?: string | null
          expected_outcome?: string | null
          id?: string
          notes?: string | null
          promise?: string
          status?: Database["public"]["Enums"]["profile_status"]
          tenant_id?: string
          updated_at?: string
          version?: number
        }
        Relationships: [
          {
            foreignKeyName: "tenant_value_profiles_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
        ]
      }
      tenants: {
        Row: {
          created_at: string
          created_by: string
          id: string
          name: string
          subject_unit_type: Database["public"]["Enums"]["subject_unit_type"]
        }
        Insert: {
          created_at?: string
          created_by: string
          id?: string
          name: string
          subject_unit_type: Database["public"]["Enums"]["subject_unit_type"]
        }
        Update: {
          created_at?: string
          created_by?: string
          id?: string
          name?: string
          subject_unit_type?: Database["public"]["Enums"]["subject_unit_type"]
        }
        Relationships: []
      }
      value_profiles: {
        Row: {
          approved_at: string | null
          approved_by: string | null
          created_at: string
          created_by: string | null
          expected_value: string
          id: string
          notes: string | null
          status: Database["public"]["Enums"]["profile_status"]
          subject_id: string
          tenant_id: string
          updated_at: string
          version: number
        }
        Insert: {
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          created_by?: string | null
          expected_value: string
          id?: string
          notes?: string | null
          status?: Database["public"]["Enums"]["profile_status"]
          subject_id: string
          tenant_id: string
          updated_at?: string
          version?: number
        }
        Update: {
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          created_by?: string | null
          expected_value?: string
          id?: string
          notes?: string | null
          status?: Database["public"]["Enums"]["profile_status"]
          subject_id?: string
          tenant_id?: string
          updated_at?: string
          version?: number
        }
        Relationships: [
          {
            foreignKeyName: "value_profiles_tenant_id_fkey"
            columns: ["tenant_id"]
            isOneToOne: false
            referencedRelation: "tenants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "value_profiles_tenant_id_subject_id_fkey"
            columns: ["tenant_id", "subject_id"]
            isOneToOne: false
            referencedRelation: "subjects"
            referencedColumns: ["tenant_id", "id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      create_demo_objective: {
        Args: { _tenant_id: string; _subject_id: string; _profile_id: string; _deadline: string; _source: string; _capacity_ref: string; _commitment_ref: string; _customer_ref: string }
        Returns: string
      }
      assess_demo_objective: {
        Args: { _tenant_id: string; _objective_id: string; _bundle_id: string }
        Returns: string
      }
      open_demo_case: {
        Args: { _tenant_id: string; _assessment_id: string }
        Returns: string
      }
      command_demo_case: {
        Args: { _tenant_id: string; _case_id: string; _expected_version: number; _operation_id: string; _command: string; _payload: Json }
        Returns: Json
      }
      _c02_cmp: {
        Args: {
          _a: number
          _b: number
          _op: Database["public"]["Enums"]["rule_operator"]
        }
        Returns: boolean
      }
      _c02_effective: {
        Args: {
          _compat: string[]
          _cutoff: string
          _key: string
          _subject: string
          _tenant: string
          _unit: string
        }
        Returns: {
          ingested_at: string
          issue: string
          obs_id: string
          observed_at: string
          source: string
          value: number
        }[]
      }
      _c02_fingerprint: {
        Args: { i: Database["public"]["Tables"]["profile_indicators"]["Row"] }
        Returns: string
      }
      _c02_window: {
        Args: {
          _agg: Database["public"]["Enums"]["c02_aggregation"]
          _cad: number
          _compat: string[]
          _cutoff: string
          _den_compat: string[]
          _den_key: string
          _den_mode: Database["public"]["Enums"]["c02_denominator_mode"]
          _den_unit: string
          _e: string
          _key: string
          _min_cov: number
          _min_den: number
          _s: string
          _subject: string
          _tenant: string
          _unit: string
        }
        Returns: Json
      }
      _c02v2_effective: {
        Args: {
          _compat: string[]
          _cutoff: string
          _key: string
          _subject: string
          _tenant: string
          _unit: string
        }
        Returns: {
          ingested_at: string
          issue: string
          obs_id: string
          observed_at: string
          source: string
          supersedes: string[]
          value: number
        }[]
      }
      _c02v2_window: {
        Args: {
          _agg: Database["public"]["Enums"]["c02_aggregation"]
          _cad: number
          _compat: string[]
          _cutoff: string
          _den_cad: number
          _den_compat: string[]
          _den_key: string
          _den_min_cov: number
          _den_mode: Database["public"]["Enums"]["c02_denominator_mode"]
          _den_unit: string
          _e: string
          _key: string
          _min_cov: number
          _min_den: number
          _s: string
          _subject: string
          _tenant: string
          _unit: string
        }
        Returns: Json
      }
      _c03_assemble: {
        Args: {
          _alg: string
          _budget: number
          _bundle: string
          _run: Database["public"]["Tables"]["c02_runs"]["Row"]
          _uid: string
        }
        Returns: Json
      }
      _c03_build: {
        Args: { _budget: number; _run_id: string; _tenant_id: string }
        Returns: Json
      }
      _c03_payload_hash: {
        Args: { o: Database["public"]["Tables"]["observations"]["Row"] }
        Returns: string
      }
      _c03_reject: { Args: { _code: string }; Returns: undefined }
      _cw_correction_issues: {
        Args: {
          _corr: string
          _dup_in_batch: boolean
          _ind: string
          _obs: string
          _src: string
          _subject: string
          _tenant: string
          _unit: string
        }
        Returns: string[]
      }
      _cw_is_privileged: { Args: never; Returns: boolean }
      add_tenant_member: {
        Args: {
          _role: Database["public"]["Enums"]["member_role"]
          _tenant_id: string
          _user_id: string
        }
        Returns: string
      }
      approve_value_profile: {
        Args: { _profile_id: string }
        Returns: {
          approved_at: string | null
          approved_by: string | null
          created_at: string
          created_by: string | null
          expected_outcome: string | null
          id: string
          notes: string | null
          promise: string
          status: Database["public"]["Enums"]["profile_status"]
          tenant_id: string
          updated_at: string
          version: number
        }
        SetofOptions: {
          from: "*"
          to: "tenant_value_profiles"
          isOneToOne: true
          isSetofReturn: false
        }
      }
      build_evidence_bundle: {
        Args: { _run_id: string; _tenant_id: string }
        Returns: Json
      }
      create_tenant: {
        Args: {
          _name: string
          _subject_unit_type: Database["public"]["Enums"]["subject_unit_type"]
        }
        Returns: string
      }
      create_value_profile_draft: {
        Args: {
          _expected_outcome?: string
          _promise: string
          _tenant_id: string
        }
        Returns: string
      }
      create_value_profile_version: {
        Args: { _from_profile_id: string }
        Returns: string
      }
      effective_value_profile: { Args: { _tenant_id: string }; Returns: string }
      has_tenant_role: {
        Args: {
          _roles: Database["public"]["Enums"]["member_role"][]
          _tenant_id: string
        }
        Returns: boolean
      }
      import_observations: {
        Args: {
          _coverage_declared: boolean
          _coverage_end: string
          _coverage_start: string
          _expected_profile_id: string
          _file_name: string
          _rows: Json
          _source: string
          _tenant_id: string
        }
        Returns: Json
      }
      is_tenant_member: { Args: { _tenant_id: string }; Returns: boolean }
      my_tenant_role: {
        Args: { _tenant_id: string }
        Returns: Database["public"]["Enums"]["member_role"]
      }
      remove_tenant_member: {
        Args: { _tenant_id: string; _user_id: string }
        Returns: undefined
      }
      run_deterioration_analysis: {
        Args: {
          _as_of?: string
          _expected_profile_id: string
          _subject_id: string
          _tenant_id: string
        }
        Returns: Json
      }
      set_member_role: {
        Args: {
          _role: Database["public"]["Enums"]["member_role"]
          _tenant_id: string
          _user_id: string
        }
        Returns: undefined
      }
      value_profile_approval_issues: {
        Args: { _profile_id: string }
        Returns: string[]
      }
    }
    Enums: {
      baseline_method: "fixed_value" | "trailing_window" | "reference_period"
      batch_status: "received" | "processing" | "completed" | "failed"
      c02_aggregation: "mean" | "sum" | "last"
      c02_denominator_mode: "observation_count" | "paired_indicator"
      c02_status:
        | "deterioration_candidate"
        | "no_deterioration"
        | "persistent_condition"
        | "insufficient_data"
        | "insufficient_config"
        | "unsupported"
        | "not_evaluated"
      c03_attempt_status: "built" | "reused" | "rejected" | "failed"
      c03_indicator_status: "complete" | "insufficient" | "context_facts"
      indicator_class: "outcome" | "usage" | "context"
      indicator_direction: "higher_is_better" | "lower_is_better"
      indicator_value_type: "numeric" | "text"
      member_role: "admin" | "operator" | "viewer"
      profile_status: "draft" | "approved" | "superseded"
      rule_kind: "absolute" | "relative_pct"
      rule_operator: "lt" | "lte" | "gt" | "gte"
      subject_unit_type: "organization" | "person"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      baseline_method: ["fixed_value", "trailing_window", "reference_period"],
      batch_status: ["received", "processing", "completed", "failed"],
      c02_aggregation: ["mean", "sum", "last"],
      c02_denominator_mode: ["observation_count", "paired_indicator"],
      c02_status: [
        "deterioration_candidate",
        "no_deterioration",
        "persistent_condition",
        "insufficient_data",
        "insufficient_config",
        "unsupported",
        "not_evaluated",
      ],
      c03_attempt_status: ["built", "reused", "rejected", "failed"],
      c03_indicator_status: ["complete", "insufficient", "context_facts"],
      indicator_class: ["outcome", "usage", "context"],
      indicator_direction: ["higher_is_better", "lower_is_better"],
      indicator_value_type: ["numeric", "text"],
      member_role: ["admin", "operator", "viewer"],
      profile_status: ["draft", "approved", "superseded"],
      rule_kind: ["absolute", "relative_pct"],
      rule_operator: ["lt", "lte", "gt", "gte"],
      subject_unit_type: ["organization", "person"],
    },
  },
} as const
