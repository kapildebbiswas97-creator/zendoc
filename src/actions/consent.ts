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

    const { data, error } = await supabase
      .from('consent_grants')
      .insert({
        grantor_id: user.id,
        grantee_id: granteeId,
        data_category: dataCategory,
        status: 'active',
        granted_at: new Date().toISOString(),
        expires_at: expiresAt ?? null,
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
      .update({ status: 'revoked', revoked_at: new Date().toISOString() })
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
        id, data_category, status, granted_at, expires_at, revoked_at,
        grantee:grantee_id ( full_name, role )
      `)
      .eq('grantor_id', user.id)
      .order('granted_at', { ascending: false });

    if (error) return { success: false, error: error.message };
    return { success: true, data: data ?? [] };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}
