import { describe, it, expect } from 'vitest';
import { evaluateEmergencyTriage } from './emergency-triage';

// ─── Original 6 tests (preserved) ─────────────────────────────────────────────

describe('Deterministic Emergency Triage Gate — Core RED flags', () => {
  it('flags crushing chest pain as RED emergency', () => {
    const result = evaluateEmergencyTriage('I am having crushing chest pain radiating to my left arm.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
    expect(result.emergency_numbers).toContain('102 (Ambulance - India)');
    expect(result.action_advice).toContain('IMMEDIATE EMERGENCY ACTION REQUIRED');
  });

  it('flags stroke symptoms (slurred speech, facial drooping) as RED', () => {
    const result = evaluateEmergencyTriage('My mother has sudden facial drooping and slurred speech.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags severe breathing difficulty as RED', () => {
    const result = evaluateEmergencyTriage('Patient cannot breathe and has severe shortness of breath.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags suicidal ideation as RED', () => {
    const result = evaluateEmergencyTriage('I want to kill myself, I feel like ending my life.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags persistent moderate fever as YELLOW', () => {
    const result = evaluateEmergencyTriage('I have had a moderate fever for two days.');
    expect(result.is_emergency).toBe(false);
    expect(result.emergency_level).toBe('YELLOW');
    expect(result.action_advice).toContain('urgent consultation');
  });

  it('classifies routine questions as GREEN', () => {
    const result = evaluateEmergencyTriage('What are healthy breakfast choices for managing blood glucose?');
    expect(result.is_emergency).toBe(false);
    expect(result.emergency_level).toBe('GREEN');
  });
});

// ─── Extended RED flag coverage ────────────────────────────────────────────────

describe('Emergency Triage — Extended RED flag coverage', () => {
  it('flags anaphylaxis (throat closing) as RED', () => {
    const result = evaluateEmergencyTriage('My throat is closing after eating peanuts.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags anaphylactic shock by name as RED', () => {
    const result = evaluateEmergencyTriage('I think I am going into anaphylactic shock.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags vomiting blood as RED', () => {
    const result = evaluateEmergencyTriage('The patient is vomiting blood continuously.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags coughing up blood as RED', () => {
    const result = evaluateEmergencyTriage('I have been coughing up blood since this morning.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags uncontrolled bleeding as RED', () => {
    const result = evaluateEmergencyTriage('There is massive uncontrolled bleeding from the wound.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags worst headache of life as RED', () => {
    const result = evaluateEmergencyTriage('This is the worst headache of my life, started suddenly.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags heart attack mention as RED', () => {
    const result = evaluateEmergencyTriage('I think I am having a heart attack.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('flags stridor as RED', () => {
    const result = evaluateEmergencyTriage('Child has stridor and difficulty breathing.');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('RED result always includes emergency numbers', () => {
    const result = evaluateEmergencyTriage('severe chest pain radiating to arm');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_numbers.length).toBeGreaterThan(0);
  });
});

// ─── YELLOW flag coverage ──────────────────────────────────────────────────────

describe('Emergency Triage — YELLOW flag coverage', () => {
  it('flags mild chest tightness as YELLOW, not RED', () => {
    const result = evaluateEmergencyTriage('I have mild chest tightness when climbing stairs.');
    expect(result.is_emergency).toBe(false);
    expect(result.emergency_level).toBe('YELLOW');
  });

  it('flags persistent vomiting as YELLOW', () => {
    const result = evaluateEmergencyTriage('I have persistent vomiting and cannot keep water down.');
    expect(result.is_emergency).toBe(false);
    expect(result.emergency_level).toBe('YELLOW');
  });

  it('flags deep cut as YELLOW', () => {
    const result = evaluateEmergencyTriage('I have a deep cut on my hand that is still bleeding slowly.');
    expect(result.is_emergency).toBe(false);
    expect(result.emergency_level).toBe('YELLOW');
  });

  it('flags fracture mention as YELLOW', () => {
    const result = evaluateEmergencyTriage('I think I have a fracture in my wrist from the fall.');
    expect(result.is_emergency).toBe(false);
    expect(result.emergency_level).toBe('YELLOW');
  });
});

// ─── Edge cases ────────────────────────────────────────────────────────────────

describe('Emergency Triage — Edge cases', () => {
  it('returns safe result for empty string', () => {
    const result = evaluateEmergencyTriage('');
    expect(result.is_emergency).toBe(false);
    expect(result.action_advice).toContain('describe your symptoms');
  });

  it('returns safe result for whitespace only', () => {
    const result = evaluateEmergencyTriage('   ');
    expect(result.is_emergency).toBe(false);
  });

  it('is case-insensitive for CRUSHING CHEST PAIN', () => {
    const result = evaluateEmergencyTriage('CRUSHING CHEST PAIN radiating');
    expect(result.is_emergency).toBe(true);
    expect(result.emergency_level).toBe('RED');
  });

  it('GREEN result has no emergency numbers', () => {
    const result = evaluateEmergencyTriage('How much water should I drink daily?');
    expect(result.is_emergency).toBe(false);
    expect(result.emergency_numbers).toHaveLength(0);
  });

  it('GREEN result contains advisory disclaimer', () => {
    const result = evaluateEmergencyTriage('What vitamins should I take?');
    expect(result.action_advice).toContain('ZENDOC AI');
  });
});
