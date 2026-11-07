import { describe, it, expect } from 'vitest';
import { processAIChat } from './model-router';

describe('AI Model Router & Advisory Layer', () => {
  it('should abort AI model inference on life-threatening input', async () => {
    const res = await processAIChat('Crushing chest pain and left arm numbness');
    expect(res.success).toBe(false);
    expect(res.is_emergency).toBe(true);
    expect(res.suggested_actions?.[0].action_type).toBe('emergency_call');
    expect(res.disclaimer).toContain('NOT a certified medical device');
  });

  it('should formulate clinical advisory with mandatory educational disclaimer', async () => {
    const res = await processAIChat('How should I monitor a mild fever at home?');
    expect(res.success).toBe(true);
    expect(res.is_emergency).toBe(false);
    expect(res.content).toContain('Hydration');
    expect(res.content).toContain('Monitoring');
    expect(res.disclaimer).toContain('NOT a certified medical device');
    expect(res.suggested_actions).toBeDefined();
    expect(res.suggested_actions?.length).toBeGreaterThan(0);
  });
});
