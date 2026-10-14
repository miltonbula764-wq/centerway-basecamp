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
          baseline_method: Database["public"]["Enums"]["baseline_method"] | null
          baseline_min_period_days: number | null
          baseline_value: number | null
          classification: Database["public"]["Enums"]["indicator_class"]
          comparison_window_days: number | null
          created_at: string
          definition: string | null
          deterioration_consecutive_windows: number | null
          deterioration_kind: Database["public"]["Enums"]["rule_kind"] | null
          deterioration_operator:
            | Database["public"]["Enums"]["rule_operator"]
            | null
          deterioration_value: number | null
          direction: Database["public"]["Enums"]["indicator_direction"]
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
          baseline_method?:
            | Database["public"]["Enums"]["baseline_method"]
            | null
          baseline_min_period_days?: number | null
          baseline_value?: number | null
          classification: Database["public"]["Enums"]["indicator_class"]
          comparison_window_days?: number | null
          created_at?: string
          definition?: string | null
          deterioration_consecutive_windows?: number | null
          deterioration_kind?: Database["public"]["Enums"]["rule_kind"] | null
          deterioration_operator?:
            | Database["public"]["Enums"]["rule_operator"]
            | null
          deterioration_value?: number | null
          direction: Database["public"]["Enums"]["indicator_direction"]
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
          baseline_method?:
            | Database["public"]["Enums"]["baseline_method"]
            | null
          baseline_min_period_days?: number | null
          baseline_value?: number | null
          classification?: Database["public"]["Enums"]["indicator_class"]
          comparison_window_days?: number | null
          created_at?: string
          definition?: string | null
          deterioration_consecutive_windows?: number | null
          deterioration_kind?: Database["public"]["Enums"]["rule_kind"] | null
          deterioration_operator?:
            | Database["public"]["Enums"]["rule_operator"]
            | null
          deterioration_value?: number | null
          direction?: Database["public"]["Enums"]["indicator_direction"]
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
