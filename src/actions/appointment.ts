'use server';

import { createClient } from '@/lib/supabase/server';
import { z } from 'zod';

// ─── Schemas ──────────────────────────────────────────────────────────────────

const AppointmentSchema = z.object({
  provider_id: z.string().uuid(),
  appointment_type: z.enum(['in_person', 'telehealth', 'home_visit']).default('in_person'),
  scheduled_at: z.string().datetime(),
  reason: z.string().max(500).optional(),
  notes: z.string().max(1000).optional(),
});

// ─── Types ────────────────────────────────────────────────────────────────────

export type ActionResult<T = void> =
  | { success: true; data: T }
  | { success: false; error: string };

// ─── List appointments for the current patient ────────────────────────────────

export async function listAppointments(): Promise<ActionResult<unknown[]>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { data, error } = await supabase
      .from('appointments')
      .select(`
        id, appointment_type, scheduled_at, status, reason, notes, created_at,
        provider:provider_id (
          id, specialty, consultation_fee,
          profile:id ( full_name, avatar_url )
        )
      `)
      .eq('patient_id', user.id)
      .order('scheduled_at', { ascending: false })
      .limit(50);

    if (error) return { success: false, error: error.message };
    return { success: true, data: data ?? [] };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

// ─── Book a new appointment ───────────────────────────────────────────────────

export async function bookAppointment(
  _prevState: ActionResult | null,
  formData: FormData
): Promise<ActionResult<{ id: string }>> {
  try {
    const providerId = (formData.get('provider_id') || formData.get('provider_profile_id')) as string;
    const appointmentType = (formData.get('appointment_type') || formData.get('consultation_mode') || 'in_person') as string;
    const normalizedType = appointmentType === 'video' ? 'telehealth' : appointmentType;

    const raw = {
      provider_id: providerId,
      appointment_type: normalizedType,
      scheduled_at: formData.get('scheduled_at') as string,
      reason: (formData.get('reason') || formData.get('chief_complaint')) as string | null,
      notes: formData.get('notes') as string | null,
    };

    const parsed = AppointmentSchema.safeParse(raw);
    if (!parsed.success) {
      return { success: false, error: parsed.error.issues[0]?.message ?? 'Invalid input.' };
    }

    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { data, error } = await supabase
      .from('appointments')
      .insert({
        patient_id: user.id,
        provider_id: parsed.data.provider_id,
        appointment_type: parsed.data.appointment_type,
        scheduled_at: parsed.data.scheduled_at,
        reason: parsed.data.reason ?? null,
        notes: parsed.data.notes ?? null,
        status: 'requested',
      })
      .select('id')
      .single();

    if (error) return { success: false, error: error.message };
    return { success: true, data: { id: data.id } };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

// ─── Cancel an appointment ────────────────────────────────────────────────────

export async function cancelAppointment(
  appointmentId: string
): Promise<ActionResult> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { error } = await supabase
      .from('appointments')
      .update({ status: 'cancelled' })
      .eq('id', appointmentId)
      .eq('patient_id', user.id); // RLS + explicit ownership check

    if (error) return { success: false, error: error.message };
    return { success: true, data: undefined };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}
