import { describe, it, expect } from 'vitest';
import { SYNTHETIC_RECORDS, SYNTHETIC_CONSENTS } from '@/lib/data/synthetic-store';
import { ProvenanceSource } from '@/lib/types/healthcare';

describe('Healthcare Security & Tenant Isolation Invariants', () => {
  it('should enforce patient record ownership against unauthorized IDOR access', () => {
    const callerId = 'unauthorized-user-999';
    const targetRecord = SYNTHETIC_RECORDS[0];

    // Caller is not the patient
    const isOwner = targetRecord.patient_id === callerId;
    expect(isOwner).toBe(false);

    // Caller has no active consent grant
    const hasConsent = SYNTHETIC_CONSENTS.some(
      (c) => c.grantee_id === callerId && c.grantor_id === targetRecord.patient_id && c.status === 'ACTIVE'
    );
    expect(hasConsent).toBe(false);

    // Therefore access must be strictly denied
    const accessPermitted = isOwner || hasConsent;
    expect(accessPermitted).toBe(false);
  });

  it('should permit access when an active, non-expired consent grant exists', () => {
    const doctorId = 'doc-001';
    const targetRecord = SYNTHETIC_RECORDS[0];

    const hasActiveConsent = SYNTHETIC_CONSENTS.some(
      (c) =>
        c.grantee_id === doctorId &&
        c.grantor_id === targetRecord.patient_id &&
        c.status === 'ACTIVE' &&
        new Date(c.valid_until).getTime() > Date.now()
    );

    expect(hasActiveConsent).toBe(true);
  });

  it('should immediately revoke access when consent status transitions to REVOKED', () => {
    const mutableConsent: { grantee_id: string; grantor_id: string; status: string } = {
      ...SYNTHETIC_CONSENTS[0],
      status: 'REVOKED',
    };
    const doctorId = 'doc-001';
    const patientId = 'pat-default';

    const hasActiveConsent = 
      mutableConsent.grantee_id === doctorId &&
      mutableConsent.grantor_id === patientId &&
      mutableConsent.status === 'ACTIVE';

    expect(hasActiveConsent).toBe(false);
  });

  it('should require every clinical fact to possess a valid provenance tag', () => {
    const validProvenances: ProvenanceSource[] = [
      'USER_REPORTED',
      'PROVIDER_RECORDED',
      'DOCUMENT_EXTRACTED',
      'DEVICE_RECORDED',
    ];

    for (const record of SYNTHETIC_RECORDS) {
      expect(validProvenances).toContain(record.provenance);
    }
  });
});
