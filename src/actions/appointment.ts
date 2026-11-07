'use server';

import { createClient } from '@/lib/supabase/server';
import { z } from 'zod';

// ─── Schemas ──────────────────────────────────────────────────────────────────

const AppointmentSchema = z.object({
  provider_profile_id: z.string().uuid(),
  facility_id: z.string().uuid().optional(),
  appointment_type: z.string().min(1),
  scheduled_at: z.string().datetime(),
  chief_complaint: z.string().max(500).optional(),
  consultation_mode: z.enum(['in_person', 'video', 'phone', 'home_visit']).default('in_person'),
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
        id, appointment_type, scheduled_at, status, consultation_mode,
        chief_complaint, notes,
        provider_profiles ( id, specialisation,
          profiles ( full_name, avatar_url )
        ),
        facilities ( id, name, address_line1, city )
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
    const raw = {
      provider_profile_id: formData.get('provider_profile_id') as string,
      facility_id: formData.get('facility_id') as string | null,
      appointment_type: formData.get('appointment_type') as string,
      scheduled_at: formData.get('scheduled_at') as string,
      chief_complaint: formData.get('chief_complaint') as string | null,
      consultation_mode: formData.get('consultation_mode') as string,
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
        ...parsed.data,
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
      .update({ status: 'cancelled', cancelled_at: new Date().toISOString() })
      .eq('id', appointmentId)
      .eq('patient_id', user.id); // RLS + explicit ownership check

    if (error) return { success: false, error: error.message };
    return { success: true, data: undefined };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}
