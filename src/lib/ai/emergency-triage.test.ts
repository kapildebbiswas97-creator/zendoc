import { describe, it, expect } from 'vitest';
import { evaluateEmergencyTriage } from './emergency-triage';

describe('Deterministic Emergency Triage Gate', () => {
  it('should flag crushing chest pain as RED emergency immediately', () => {
    const input = 'I am having crushing chest pain radiating to my left arm.';
    const result = evaluateEmergencyTriage(input);
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
    expect(result.emergency_numbers).toContain('102 (Ambulance - India)');
    expect(result.action_advice).toContain('IMMEDIATE EMERGENCY ACTION REQUIRED');
  });

  it('should flag stroke symptoms (slurred speech, facial drooping) as RED emergency', () => {
    const input = 'My mother has sudden facial drooping and slurred speech.';
    const result = evaluateEmergencyTriage(input);
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('should flag severe breathing difficulty as RED emergency', () => {
    const input = 'Patient cannot breathe and has severe shortness of breath.';
    const result = evaluateEmergencyTriage(input);
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('should flag suicidal ideation as RED emergency', () => {
    const input = 'I want to kill myself, I feel like ending my life.';
    const result = evaluateEmergencyTriage(input);
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('should flag persistent moderate fever as YELLOW warning without full emergency', () => {
    const input = 'I have had a moderate fever for two days.';
    const result = evaluateEmergencyTriage(input);
    expect(result.is_emergency).toBe(false);
    expect(result.emergency_level).toBe('YELLOW');
    expect(result.action_advice).toContain('urgent consultation');
  });

  it('should classify routine questions as GREEN advisory', () => {
    const input = 'What are healthy breakfast choices for managing blood glucose?';
    const result = evaluateEmergencyTriage(input);
    expect(result.is_emergency).toBe(false);
    expect(result.emergency_level).toBe('GREEN');
  });
});
