'use server';

import { createClient } from '@/lib/supabase/server';

export type ActionResult<T = void> =
  | { success: true; data: T }
  | { success: false; error: string };

// ─── Grant Consent ────────────────────────────────────────────────────────────

export async function grantConsent(
  granteeId: string,
  dataCategory: string,
  expiresAt?: string
): Promise<ActionResult<{ id: string }>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const validUntil = expiresAt || new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString();

    const { data, error } = await supabase
      .from('consent_grants')
      .insert({
        grantor_id: user.id,
        grantee_id: granteeId,
        purpose: dataCategory || 'CLINICAL_CARE',
        scope: 'FULL_RECORD',
        data_category: dataCategory,
        status: 'ACTIVE',
        valid_until: validUntil,
      })
      .select('id')
      .single();

    if (error) return { success: false, error: error.message };
    return { success: true, data: { id: data.id } };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

// ─── Revoke Consent ───────────────────────────────────────────────────────────

export async function revokeConsent(consentId: string): Promise<ActionResult> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { error } = await supabase
      .from('consent_grants')
      .update({ status: 'REVOKED', revoked_at: new Date().toISOString() })
      .eq('id', consentId)
      .eq('grantor_id', user.id); // only grantor can revoke their own grants

    if (error) return { success: false, error: error.message };
    return { success: true, data: undefined };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

// ─── List active consents ──────────────────────────────────────────────────────

export async function listConsents(): Promise<ActionResult<unknown[]>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { data, error } = await supabase
      .from('consent_grants')
      .select(`
        id, purpose, scope, status, valid_until, revoked_at, created_at,
        grantee:grantee_id ( full_name, role )
      `)
      .eq('grantor_id', user.id)
      .order('created_at', { ascending: false });

    if (error) return { success: false, error: error.message };
    return { success: true, data: data ?? [] };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}
