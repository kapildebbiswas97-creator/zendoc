'use server';

import { createClient } from '@/lib/supabase/server';

export type ActionResult<T = void> =
  | { success: true; data: T }
  | { success: false; error: string };

// ─── Append audit log entry (server-only, never exposed to client) ────────────

export async function appendAuditLog(
  action: string,
  resourceType: string,
  resourceId?: string,
  metadata?: Record<string, unknown>
): Promise<void> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();

    await supabase.from('audit_logs').insert({
      actor_id: user?.id ?? null,
      action,
      resource_type: resourceType,
      resource_id: resourceId ?? '',
      metadata: metadata ?? {},
      created_at: new Date().toISOString(),
    });
  } catch {
    // Audit logging must never crash the calling flow
  }
}

// ─── List audit logs (admin only — enforced by RLS) ───────────────────────────

export async function listAuditLogs(
  limit = 100,
  offset = 0
): Promise<ActionResult<unknown[]>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const { data, error } = await supabase
      .from('audit_logs')
      .select(`
        id, action, resource_type, resource_id, metadata, created_at,
        actor:actor_id ( full_name, role )
      `)
      .order('created_at', { ascending: false })
      .range(offset, offset + limit - 1);

    if (error) return { success: false, error: error.message };
    return { success: true, data: data ?? [] };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}
