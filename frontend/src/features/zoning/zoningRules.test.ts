import { describe, expect, it } from 'vitest';
import catalog from './zoningCatalog.json';
import { RULE_FIELDS } from './types';
import { isZoningCode, ruleGuidance } from './zoningRules';

describe('zoning rule guidance', () => {
  it('covers all 22 proposed zoning groups without inventing numeric limits', () => {
    const groups = catalog.filter(item => item.category === 'zoning_type');
    expect(groups).toHaveLength(22);
    for (const group of groups) {
      expect(isZoningCode(group.code)).toBe(true);
      const guidance = ruleGuidance(group.code);
      expect(guidance.map(item => item.field)).toEqual(RULE_FIELDS.map(([field]) => field));
      expect(guidance.every(item => ['unknown', 'conditional', 'not_applicable'].includes(item.hint.state))).toBe(true);
    }
  });

  it('keeps conditional villa limits and N/A road controls distinct from approved values', () => {
    const villa = ruleGuidance('RES-V');
    expect(villa.find(item => item.field === 'max_floors')?.hint.state).toBe('conditional');
    expect(villa.find(item => item.field === 'max_height')?.hint.state).toBe('unknown');
    expect(ruleGuidance('TRN-R').find(item => item.field === 'coverage')?.hint.state).toBe('not_applicable');
    expect(ruleGuidance('PRK').find(item => item.field === 'coverage')?.hint.state).toBe('unknown');
    expect(isZoningCode('ODT')).toBe(false);
  });
});
