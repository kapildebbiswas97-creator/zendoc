import { TriageEvaluation } from '@/lib/types/healthcare';

const EMERGENCY_RED_FLAGS = [
  // Cardiac
  /\b(crushing|severe|radiating)\s*(chest\s*pain|heart\s*pain)\b/i,
  /\bheart\s*attack\b/i,
  /\bpressure\s*(in|on)\s*(the\s*)?chest\b/i,
  // Stroke / Neurological
  /\b(sudden|severe)\s*(numbness|weakness)\s*(in\s*the\s*face|on\s*one\s*side|in\s*the\s*arm)\b/i,
  /\bfacial\s*droop(ing)?\b/i,
  /\bslurred\s*speech\b/i,
  /\bworst\s*headache\s*of\s*(my\s*)?life\b/i,
  // Seizures & Convulsions
  /\b(active\s+)?seiz(ure|ing)\b/i,
  /\bconvulsions?\b/i,
  // Respiratory
  /\b(cannot|can't)\s*breathe\b/i,
  /\bsevere\s*(shortness\s*of\s*breath|difficulty\s*breathing)\b/i,
  /\bturning\s*blue\b/i,
  /\bstridor\b/i,
  // Choking & Airway Obstruction
  /\b(choking|airway\s*obstruct(ed|ion))\b/i,
  // Unconscious & Unresponsive
  /\b(unconscious(ness)?|unresponsive|not\s*breathing)\b/i,
  // Drowning
  /\b(drowning|near[\s-]drowning)\b/i,
  // Hemorrhage
  /\b(massive|uncontrolled|severe)\s*bleeding\b/i,
  /\bvomi?ting\s*blood\b/i,
  /\b(coughing|cough)\s*up\s*blood\b/i,
  // Severe Burns
  /\bsevere\s*burn(s)?\b/i,
  /\b(chemical|electrical)\s*burn(s)?\b/i,
  // Diabetic Acute Crisis (DKA)
  /\b(diabetic\s+)?(ketoacidosis|dka)\b/i,
  // Psychiatric crisis
  /\b(suicid(e|al)|kill\s*myself|end\s*my\s*life)\b/i,
  // Anaphylaxis & Airway Closure
  /\b(throat\s*(is\s*)?closing|swelling\s*(in|of)\s*(the\s*)?throat|anaphyla(xis|ctic))\b/i,
  /\bcannot\s+swallow\b/i,
  /\b(face|lip|tongue)\s+(is\s+)?(swelling|swollen)\b/i,
];

const YELLOW_FLAGS = [
  /\b(moderate|persistent|high|elevated)\s*fever\b/i,
  /\bmild\s*chest\s*tightness\b/i,
  /\bpersistent\s*vomiting\b/i,
  /\bdeep\s*cut\b/i,
  /\bfracture|broken\s*bone\b/i,
  /\bsevere\s*(abdominal|stomach)\s*pain\b/i,
  /\b(sudden|severe)\s*back\s*pain\b/i,
  /\bblood\s*in\s*(the\s*)?(urine|stool)\b/i,
  /\bhematuria\b/i,
];

export function evaluateEmergencyTriage(input: string): TriageEvaluation {
  const normalized = input.trim();
  if (!normalized) {
    return {
      is_emergency: false,
      emergency_numbers: [],
      action_advice: 'Please describe your symptoms.',
    };
  }

  for (const pattern of EMERGENCY_RED_FLAGS) {
    if (pattern.test(normalized)) {
      return {
        is_emergency: true,
        emergency_level: 'RED',
        reason: 'Acute life-threatening red-flag symptoms detected.',
        emergency_numbers: ['102 (Ambulance - India)', '108 (Disaster/Emergency - India)', '112 (National Emergency)', '911 (US/Canada)', '999 (UK)'],
        action_advice: 'IMMEDIATE EMERGENCY ACTION REQUIRED: Do not wait for AI advice. Call your local emergency medical service or proceed to the nearest emergency trauma center immediately.',
      };
    }
  }

  for (const pattern of YELLOW_FLAGS) {
    if (pattern.test(normalized)) {
      return {
        is_emergency: false,
        emergency_level: 'YELLOW',
        reason: 'Urgent clinical evaluation recommended.',
        emergency_numbers: ['102', '108', '112'],
        action_advice: 'We advise scheduling an urgent consultation with a verified clinician today.',
      };
    }
  }

  return {
    is_emergency: false,
    emergency_level: 'GREEN',
    emergency_numbers: [],
    action_advice: 'Advisory guidance available. Remember that ZENDOC AI is strictly educational and not a medical diagnosis.',
  };
}
