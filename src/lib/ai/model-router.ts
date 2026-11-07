import { evaluateEmergencyTriage } from './emergency-triage';
import { TriageEvaluation } from '@/lib/types/healthcare';

export interface AIResponse {
  success: boolean;
  is_emergency: boolean;
  triage: TriageEvaluation;
  content: string;
  suggested_actions?: Array<{
    title: string;
    action_type: 'book_appointment' | 'order_lab' | 'consult_specialist' | 'emergency_call';
    payload?: Record<string, unknown>;
  }>;
  plan_hash?: string;
  disclaimer: string;
}

const MANDATORY_DISCLAIMER = 
  "DISCLAIMER: ZENDOC AI is an educational health advisory tool, NOT a certified medical device, autonomous diagnostic engine, or prescribing authority. Always consult a qualified, licensed healthcare professional for medical emergencies and clinical diagnoses.";

export async function processAIChat(
  userQuery: string,
  userContext?: {
    patientName?: string;
    age?: number;
    activeConditions?: string[];
  }
): Promise<AIResponse> {
  // 1. Mandatory Deterministic Emergency Check FIRST
  const triage = evaluateEmergencyTriage(userQuery);
  if (triage.is_emergency) {
    return {
      success: false,
      is_emergency: true,
      triage,
      content: `${triage.action_advice}\n\nEmergency Numbers: ${triage.emergency_numbers.join(', ')}`,
      suggested_actions: [
        {
          title: 'Call Emergency Ambulance (102/108)',
          action_type: 'emergency_call',
          payload: { numbers: triage.emergency_numbers },
        },
      ],
      disclaimer: MANDATORY_DISCLAIMER,
    };
  }

  // 2. Structured Knowledge & Advisory Formulation
  const responseText = formulateClinicalAdvisory(userQuery, userContext);

  return {
    success: true,
    is_emergency: false,
    triage,
    content: responseText,
    suggested_actions: [
      {
        title: 'Find a Specialist Near You',
        action_type: 'consult_specialist',
        payload: { query: userQuery },
      },
      {
        title: 'Schedule a Follow-Up Consultation',
        action_type: 'book_appointment',
      },
    ],
    disclaimer: MANDATORY_DISCLAIMER,
  };
}

function formulateClinicalAdvisory(
  query: string,
  context?: { patientName?: string; activeConditions?: string[] }
): string {
  const q = query.toLowerCase();

  if (q.includes('fever') || q.includes('temperature')) {
    return `### Fever Advisory & Guidance
1. **Hydration**: Ensure adequate fluid intake (water, oral rehydration solutions, clear broths) to prevent dehydration.
2. **Monitoring**: Track temperature using a digital thermometer every 4â€“6 hours and record readings in your Health Memory vitals tracker.
3. **Rest**: Prioritize adequate sleep and avoid intense physical exertion.
4. **Clinical Evaluation**: If fever exceeds 102Â°F (38.9Â°C), persists for more than 48 hours, or is accompanied by a stiff neck, rash, or persistent vomiting, seek medical evaluation immediately.`;
  }

  if (q.includes('headache') || q.includes('migraine')) {
    return `### Headache Self-Care & Assessment
1. **Rest**: Rest in a quiet, dimly lit, well-ventilated room.
2. **Hydration & Electrolytes**: Mild dehydration is a frequent trigger; drink a glass of water or electrolyte solution.
3. **Screen Ergonomics**: Reduce screen exposure and take regular breaks.
4. **Red Flags**: If this headache began suddenly like a "thunderclap", or is accompanied by vision loss, weakness, or fever, please seek urgent medical attention.`;
  }

  if (q.includes('diet') || q.includes('nutrition') || q.includes('weight')) {
    return `### General Nutritional Guidance
1. **Balanced Nutrition**: Aim for a plate rich in whole grains, colorful vegetables, lean proteins, and healthy dietary fats.
2. **Hydration Target**: Maintain at least 2.5 liters of clean water daily unless medically restricted for renal or cardiac reasons.
3. **Tracking**: Log your daily meals and hydration in the ZENDOC Nutrition Tracker to review with your clinical dietitian.`;
  }

  return `Thank you for sharing your inquiry. Based on the symptoms described:
- **Rest and Observation**: Monitor the progression of symptoms over the next 24 to 48 hours.
- **Log Metrics**: Record any relevant vitals (such as blood pressure, temperature, or pulse) in your ZENDOC Health Memory.
- **Consultation Recommended**: For tailored guidance, we recommend booking an appointment with a verified healthcare professional in the Find Care directory.`;
}
