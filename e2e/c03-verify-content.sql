-- Independent read-only reconstruction of the c03-v1 content address from persisted evidence.
-- No C03 private helper or builder is called. JSONB preserves stored numeric precision/UTC encoding.
SET TIME ZONE 'UTC';
WITH reconstructed AS (
  SELECT b.id, b.content_hash,
    jsonb_build_object('alg',b.algorithm_version,'run',b.run_id,'c02_alg',b.c02_algorithm_version,
      'input_hash',b.c02_input_hash,'cutoff',to_char(b.data_cutoff,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      'budget',b.summary->'ref_budget','indicators',(
        SELECT jsonb_agg(jsonb_build_object('key',i.indicator_key,'status',i.status,'reasons',to_jsonb(i.reasons),
          'ref_count',i.ref_count,'stored',i.stored_ref_count,'snapshot',i.snapshot,'refs',coalesce((
            SELECT jsonb_agg(
              jsonb_build_object('oid',r.observation_id,'role',r.role,'label',r.window_label,
                's',r.window_start,'e',r.window_end,'key',r.indicator_key) ||
              CASE WHEN r.role IN ('numerator','denominator') THEN jsonb_build_object('unit',r.unit)
                ELSE jsonb_build_object('prev',r.superseded_by,'leaf',(
                  SELECT c.value->>'observation_id'
                  FROM jsonb_array_elements(i.snapshot#>'{details,windows}' ||
                    jsonb_build_array(i.snapshot#>'{details,reference}') ||
                    jsonb_build_array(i.snapshot#>'{details,baseline_window}')) w,
                    LATERAL jsonb_array_elements(CASE WHEN r.role='denominator_superseded'
                      THEN coalesce(w.value->'denominator_corrections','[]')
                      ELSE coalesce(w.value->'corrections','[]') END) c
                  WHERE c.value->'supersedes' @> jsonb_build_array(r.observation_id::text)
                )) END || jsonb_build_object('ph',r.payload_hash,'ord',r.ordinal)
              ORDER BY r.ordinal)
            FROM public.c03_refs r WHERE r.indicator_id=i.id AND r.bundle_id=b.id
          ),'[]'::jsonb)) ORDER BY i.indicator_key)
        FROM public.c03_indicators i WHERE i.bundle_id=b.id
      )) AS payload
  FROM public.c03_bundles b
)
SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'valid',
  encode(sha256(convert_to(payload::text,'UTF8')),'hex')=content_hash) ORDER BY id),'[]'::jsonb)
FROM reconstructed;
