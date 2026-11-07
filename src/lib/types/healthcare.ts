export type UserRole = 'patient' | 'provider' | 'org_admin' | 'platform_admin' | 'caregiver';

export type TruthStatus = 
  | 'WORKING'
  | 'BETA'
  | 'INTEGRATION_REQUIRED'
  | 'DISABLED'
  | 'FUTURE';

export type ProvenanceSource = 
  | 'USER_REPORTED'
  | 'PROVIDER_RECORDED'
  | 'DOCUMENT_EXTRACTED'
  | 'DEVICE_RECORDED';

export type AppointmentStatus = 
  | 'requested'
  | 'confirmed'
  | 'in_consultation'
  | 'completed'
  | 'cancelled'
  | 'no_show';

export type ConsentStatus = 'ACTIVE' | 'REVOKED' | 'EXPIRED';

export interface Profile {
  id: string;
  role: UserRole;
  full_name: string;
  email?: string;
  phone?: string;
  date_of_birth?: string;
  gender?: string;
  blood_group?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  avatar_url?: string;
  ekyc_verified: boolean;
  data_mode: 'LIVE' | 'DEMO' | 'SYNTHETIC';
  created_at: string;
}

export interface Facility {
  id: string;
  name: string;
  category: string;
  address: string;
  city: string;
  state: string;
  pincode: string;
  phone?: string;
  email?: string;
  is_verified: boolean;
  verification_source: string;
  latitude?: number;
  longitude?: number;
}

export interface ProviderProfile {
  id: string;
  full_name: string;
  specialty: string;
  registration_number: string;
  qualifications: string;
  experience_years: number;
  consultation_fee: number;
  bio?: string;
  is_verified: boolean;
  facility_name?: string;
  avatar_url?: string;
  rating?: number;
}

export interface MedicalRecord {
  id: string;
  patient_id: string;
  title: string;
  record_type: string;
  storage_path: string;
  mime_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  summary?: string;
  provenance: ProvenanceSource;
  created_at: string;
}

export interface HealthMetric {
  id: string;
  patient_id: string;
  metric_type: 'blood_pressure' | 'heart_rate' | 'blood_glucose' | 'spo2' | 'temperature' | 'weight';
  value: number;
  unit: string;
  secondary_value?: number;
  notes?: string;
  provenance: ProvenanceSource;
  recorded_at: string;
}

export interface Appointment {
  id: string;
  patient_id: string;
  patient_name?: string;
  provider_id: string;
  provider_name?: string;
  specialty?: string;
  scheduled_at: string;
  appointment_type: 'in_person' | 'telehealth' | 'home_visit';
  status: AppointmentStatus;
  reason?: string;
  notes?: string;
}

export interface ConsentGrant {
  id: string;
  grantor_id: string;
  grantee_id: string;
  grantee_name?: string;
  purpose: string;
  scope: string;
  valid_until: string;
  status: ConsentStatus;
  created_at: string;
}

export interface CareJourneyMilestone {
  id: string;
  name: string;
  is_completed: boolean;
  due_date?: string;
  completed_at?: string;
}

export interface CareJourney {
  id: string;
  patient_id: string;
  journey_title: string;
  category: string;
  current_milestone: string;
  status: 'active' | 'completed' | 'paused';
  milestones?: CareJourneyMilestone[];
}

export interface TriageEvaluation {
  is_emergency: boolean;
  emergency_level?: 'RED' | 'YELLOW' | 'GREEN';
  reason?: string;
  emergency_numbers: string[];
  action_advice: string;
}
