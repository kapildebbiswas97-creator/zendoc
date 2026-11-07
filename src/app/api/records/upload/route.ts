import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { uploadMedicalRecord } from '@/actions/records';

/**
 * POST /api/records/upload
 * Accepts multipart/form-data with a medical document.
 * Authenticates via session cookie, delegates to the uploadMedicalRecord action.
 */
export async function POST(request: NextRequest) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: 'Unauthorized.' }, { status: 401 });
  }

  try {
    const formData = await request.formData();
    const result = await uploadMedicalRecord(formData);

    if (!result.success) {
      return NextResponse.json({ error: result.error }, { status: 422 });
    }

    return NextResponse.json(
      { recordId: result.recordId, storagePath: result.storagePath },
      { status: 201 }
    );
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
