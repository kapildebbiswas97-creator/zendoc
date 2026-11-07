'use server';

import { createClient } from '@/lib/supabase/server';

export type ActionResult<T = void> =
  | { success: true; data: T }
  | { success: false; error: string };

// ─── Search Facilities ────────────────────────────────────────────────────────

export async function searchFacilities(query: {
  city?: string;
  facility_type?: string;
  name?: string;
  limit?: number;
}): Promise<ActionResult<unknown[]>> {
  try {
    const supabase = await createClient();

    let qb = supabase
      .from('facilities')
      .select(`
        id, name, facility_type, address_line1, city, state,
        phone, website, is_verified, verification_status,
        average_rating, total_reviews
      `)
      .eq('is_active', true)
      .limit(query.limit ?? 20);

    if (query.city) qb = qb.ilike('city', `%${query.city}%`);
    if (query.facility_type) qb = qb.eq('facility_type', query.facility_type);
    if (query.name) qb = qb.ilike('name', `%${query.name}%`);

    const { data, error } = await qb.order('is_verified', { ascending: false });
    if (error) return { success: false, error: error.message };
    return { success: true, data: data ?? [] };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

// ─── Search Providers ─────────────────────────────────────────────────────────

export async function searchProviders(query: {
  specialisation?: string;
  city?: string;
  name?: string;
  limit?: number;
}): Promise<ActionResult<unknown[]>> {
  try {
    const supabase = await createClient();

    let qb = supabase
      .from('provider_profiles')
      .select(`
        id, specialisation, years_experience, consultation_fee,
        average_rating, total_reviews, is_verified, verification_status,
        consultation_modes,
        profiles!inner ( full_name, avatar_url )
      `)
      .eq('is_active', true)
      .limit(query.limit ?? 20);

    if (query.specialisation)
      qb = qb.ilike('specialisation', `%${query.specialisation}%`);
    if (query.name)
      qb = qb.ilike('profiles.full_name', `%${query.name}%`);

    const { data, error } = await qb.order('is_verified', { ascending: false });
    if (error) return { success: false, error: error.message };
    return { success: true, data: data ?? [] };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}
