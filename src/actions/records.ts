'use server';

import { createClient } from '@/lib/supabase/server';

export type UploadResult =
  | { success: true; recordId: string; storagePath: string }
  | { success: false; error: string };

const ALLOWED_MIME_TYPES = new Set([
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
  'application/dicom',
]);

const MAX_BYTES = 25 * 1024 * 1024; // 25 MB

export async function uploadMedicalRecord(formData: FormData): Promise<UploadResult> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return { success: false, error: 'Not authenticated.' };

    const file = formData.get('file') as File | null;
    const title = (formData.get('title') as string | null)?.trim();
    const recordType = (formData.get('record_type') as string | null) ?? 'general';
    const sourceFacility = (formData.get('source_facility') as string | null) ?? '';
    const recordDate = (formData.get('record_date') as string | null) ?? new Date().toISOString().split('T')[0];

    if (!file) return { success: false, error: 'No file provided.' };
    if (!title) return { success: false, error: 'Document title is required.' };
    if (!ALLOWED_MIME_TYPES.has(file.type)) {
      return { success: false, error: `File type '${file.type}' is not permitted. Allowed: PDF, JPEG, PNG, WEBP, HEIC, DICOM.` };
    }
    if (file.size > MAX_BYTES) {
      return { success: false, error: 'File exceeds the 25 MB size limit.' };
    }

    // Build a namespaced, collision-resistant storage path
    const ext = file.name.split('.').pop() ?? 'bin';
    const storagePath = `${user.id}/${recordDate}/${crypto.randomUUID()}.${ext}`;

    const { error: uploadError } = await supabase.storage
      .from('medical-records')
      .upload(storagePath, file, {
        contentType: file.type,
        upsert: false,
      });

    if (uploadError) return { success: false, error: uploadError.message };

    // Insert metadata row — RLS restricts this row to the user
    const { data: record, error: dbError } = await supabase
      .from('medical_records')
      .insert({
        patient_id: user.id,
        title,
        record_type: recordType,
        source_facility: sourceFacility || null,
        record_date: recordDate,
        storage_path: storagePath,
        file_size_bytes: file.size,
        mime_type: file.type,
        is_verified: false,
      })
      .select('id')
      .single();

    if (dbError) {
      // Best-effort cleanup of orphaned storage object
      await supabase.storage.from('medical-records').remove([storagePath]);
      return { success: false, error: dbError.message };
    }

    return { success: true, recordId: record.id, storagePath };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}
