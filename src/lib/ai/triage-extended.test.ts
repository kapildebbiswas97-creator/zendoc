import { describe, it, expect } from 'vitest';
import { evaluateEmergencyTriage } from './emergency-triage';
import { sanitizeAIResponse } from './model-router';

describe('Phase 3E: Extended AI Emergency Safety & Output Sanitization', () => {
  describe('Acute Life-Threatening Red Flag Interception', () => {
    it('intercepts active seizure as RED emergency immediately', () => {
      const result = evaluateEmergencyTriage('My brother is having an active seizure right now');
      expect(result.is_emergency).toBe(true);
      expect(result.emergency_level).toBe('RED');
      expect(result.emergency_numbers).toContain('112 (National Emergency)');
    });

    it('intercepts convulsions as RED emergency', () => {
      const result = evaluateEmergencyTriage('The child has violent convulsions and high heat');
      expect(result.is_emergency).toBe(true);
      expect(result.emergency_level).toBe('RED');
    });

    it('intercepts choking and airway obstruction as RED emergency', () => {
      const result = evaluateEmergencyTriage('Patient is choking on food and airway is obstructed');
      expect(result.is_emergency).toBe(true);
      expect(result.emergency_level).toBe('RED');
    });

    it('intercepts unconscious and unresponsive patient as RED emergency', () => {
      const result = evaluateEmergencyTriage('Found my elderly father unconscious and unresponsive on the floor');
      expect(result.is_emergency).toBe(true);
      expect(result.emergency_level).toBe('RED');
    });

    it('intercepts diabetic ketoacidosis (DKA) as RED emergency', () => {
      const result = evaluateEmergencyTriage('Patient has type 1 diabetes, deep breathing, and suspected diabetic ketoacidosis');
      expect(result.is_emergency).toBe(true);
      expect(result.emergency_level).toBe('RED');
    });

    it('intercepts near-drowning as RED emergency', () => {
      const result = evaluateEmergencyTriage('Child rescued from pool, near drowning incident');
      expect(result.is_emergency).toBe(true);
      expect(result.emergency_level).toBe('RED');
    });

    it('intercepts severe electrical or chemical burns as RED emergency', () => {
      const result = evaluateEmergencyTriage('Worker suffered an electrical burn on hands and chest');
      expect(result.is_emergency).toBe(true);
      expect(result.emergency_level).toBe('RED');
    });

    it('intercepts severe allergic reaction with face/lip swelling as RED emergency', () => {
      const result = evaluateEmergencyTriage('Ate shellfish and my face is swelling rapidly');
      expect(result.is_emergency).toBe(true);
      expect(result.emergency_level).toBe('RED');
    });

    it('intercepts cannot swallow phrase as RED emergency', () => {
      const result = evaluateEmergencyTriage('Severe reaction and cannot swallow saliva');
      expect(result.is_emergency).toBe(true);
      expect(result.emergency_level).toBe('RED');
    });
  });

  describe('Yellow Flag Urgent Clinical Evaluation', () => {
    it('flags high fever as YELLOW warning', () => {
      const result = evaluateEmergencyTriage('I have a high fever of 103F for 24 hours');
      expect(result.is_emergency).toBe(false);
      expect(result.emergency_level).toBe('YELLOW');
      expect(result.action_advice).toContain('urgent consultation');
    });

    it('flags severe abdominal pain as YELLOW warning', () => {
      const result = evaluateEmergencyTriage('Sudden severe abdominal pain on lower right side');
      expect(result.is_emergency).toBe(false);
      expect(result.emergency_level).toBe('YELLOW');
    });

    it('flags blood in urine / hematuria as YELLOW warning', () => {
      const result = evaluateEmergencyTriage('I noticed blood in urine today with burning sensation');
      expect(result.is_emergency).toBe(false);
      expect(result.emergency_level).toBe('YELLOW');
    });
  });

  describe('False Positives & Benign Guidance', () => {
    it('classifies benign health questions as GREEN advisory', () => {
      const result = evaluateEmergencyTriage('What foods are high in vitamin C and antioxidants?');
      expect(result.is_emergency).toBe(false);
      expect(result.emergency_level).toBe('GREEN');
    });

    it('classifies mild fatigue after travel as GREEN advisory', () => {
      const result = evaluateEmergencyTriage('Feeling mild tiredness after a long flight, best sleep routine?');
      expect(result.is_emergency).toBe(false);
      expect(result.emergency_level).toBe('GREEN');
    });
  });

  describe('AI Output Sanitization & Prescription Masking', () => {
    it('strips autonomous medication dosages from model output', () => {
      const rawText = 'You should take 500 mg of paracetamol and 10 ml of cough syrup twice daily.';
      const sanitized = sanitizeAIResponse(rawText);

      expect(sanitized).not.toContain('500 mg');
      expect(sanitized).not.toContain('10 ml');
      expect(sanitized).toContain('[dosage omitted — consult your prescriber]');
    });

    it('truncates oversized text exceeding 2000 characters', () => {
      const longText = 'A'.repeat(2500);
      const sanitized = sanitizeAIResponse(longText);

      expect(sanitized.length).toBeLessThanOrEqual(2000);
      expect(sanitized.endsWith('...')).toBe(true);
    });
  });
});
