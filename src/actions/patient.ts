'use server';

import { createClient } from '@/lib/supabase/server';
import { z } from 'zod';

export type ActionResult<T = void> =
  | { success: true; data: T }
  | { success: false; error: string };

// ─── Health Metrics ───────────────────────────────────────────────────────────

const MetricSchema = z.object({
  metric_type: z.string().min(1),
  value: z.number(),
  unit: z.string().min(1),
  measured_at: z.string().datetime().optional(),
  notes: z.string().max(500).optional(),
  device_source: z.string().optional(),
});

export async function listHealthMetrics(): Promise<ActionResult<unknown[]>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { data, error } = await supabase
      .from('health_metrics')
      .select('id, metric_type, value, unit, secondary_value, notes, provenance, recorded_at, measured_at, created_at')
      .eq('patient_id', user.id)
      .order('recorded_at', { ascending: false })
      .limit(200);

    if (error) return { success: false, error: error.message };
    return { success: true, data: data ?? [] };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

export async function addHealthMetric(
  _prevState: ActionResult | null,
  formData: FormData
): Promise<ActionResult<{ id: string }>> {
  try {
    const raw = {
      metric_type: formData.get('metric_type') as string,
      value: parseFloat(formData.get('value') as string),
      unit: formData.get('unit') as string,
      measured_at: (formData.get('measured_at') as string) || new Date().toISOString(),
      notes: (formData.get('notes') as string) || undefined,
      device_source: (formData.get('device_source') as string) || undefined,
    };

    const parsed = MetricSchema.safeParse(raw);
    if (!parsed.success) {
      return { success: false, error: parsed.error.issues[0]?.message ?? 'Invalid input.' };
    }

    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const timestamp = parsed.data.measured_at || new Date().toISOString();

    const { data, error } = await supabase
      .from('health_metrics')
      .insert({
        patient_id: user.id,
        metric_type: parsed.data.metric_type,
        value: parsed.data.value,
        unit: parsed.data.unit,
        notes: parsed.data.notes,
        device_source: parsed.data.device_source,
        recorded_at: timestamp,
        measured_at: timestamp,
        provenance: 'USER_REPORTED',
      })
      .select('id')
      .single();

    if (error) return { success: false, error: error.message };
    return { success: true, data: { id: data.id } };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

// ─── Medical Records ──────────────────────────────────────────────────────────

export async function listMedicalRecords(): Promise<ActionResult<unknown[]>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { data, error } = await supabase
      .from('medical_records')
      .select('id, record_type, title, source_facility, storage_path, file_size_bytes, mime_type, sha256_hash, provenance, created_at')
      .eq('patient_id', user.id)
      .order('created_at', { ascending: false })
      .limit(100);

    if (error) return { success: false, error: error.message };
    return { success: true, data: data ?? [] };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

export async function getSignedRecordUrl(
  recordId: string
): Promise<ActionResult<{ url: string }>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    // Fetch record — RLS ensures it belongs to this user
    const { data: record, error: fetchErr } = await supabase
      .from('medical_records')
      .select('storage_path')
      .eq('id', recordId)
      .eq('patient_id', user.id)
      .single();

    if (fetchErr || !record?.storage_path) {
      return { success: false, error: 'Record not found or access denied.' };
    }

    const { data: signedData, error: signErr } = await supabase.storage
      .from('medical-records')
      .createSignedUrl(record.storage_path, 300); // 5-min TTL

    if (signErr || !signedData?.signedUrl) {
      return { success: false, error: signErr?.message ?? 'Failed to generate download link.' };
    }

    return { success: true, data: { url: signedData.signedUrl } };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

// ─── Health Timeline / Memory ─────────────────────────────────────────────────

export async function listHealthTimeline(): Promise<ActionResult<unknown[]>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { data, error } = await supabase
      .from('health_timeline_events')
      .select('id, event_type, title, description, related_record_id, occurred_at, created_at')
      .eq('patient_id', user.id)
      .order('occurred_at', { ascending: false })
      .limit(150);

    if (error) return { success: false, error: error.message };
    return { success: true, data: data ?? [] };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

// ─── Patient Profile ──────────────────────────────────────────────────────────

export async function getPatientProfile(): Promise<ActionResult<unknown>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { data, error } = await supabase
      .from('profiles')
      .select('id, full_name, avatar_url, date_of_birth, gender, phone, blood_group, role, created_at')
      .eq('id', user.id)
      .single();

    if (error) return { success: false, error: error.message };
    return { success: true, data };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

export async function updatePatientProfile(
  _prevState: ActionResult | null,
  formData: FormData
): Promise<ActionResult> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const updates: Record<string, unknown> = {};
    const fields = ['full_name', 'date_of_birth', 'gender', 'phone', 'blood_group'];
    for (const f of fields) {
      const val = formData.get(f);
      if (val !== null && val !== '') updates[f] = val;
    }

    const { error } = await supabase
      .from('profiles')
      .update({ ...updates, updated_at: new Date().toISOString() })
      .eq('id', user.id);

    if (error) return { success: false, error: error.message };
    return { success: true, data: undefined };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}
