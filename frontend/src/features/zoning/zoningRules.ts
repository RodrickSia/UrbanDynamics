import { RULE_FIELDS } from './types';

export type RuleKey = typeof RULE_FIELDS[number][0];
export type RuleState = 'unknown' | 'conditional' | 'not_applicable';
export interface RuleHint { state: RuleState; text: string }

const conditional = (text: string): RuleHint => ({ state: 'conditional', text });
const notApplicable = (text: string): RuleHint => ({ state: 'not_applicable', text });
const defaultHint: RuleHint = { state: 'unknown', text: 'Approved plan required' };
const front = conditional('QCVN 01:2021, Table 2.7 · road boundary + height required');
const publicCoverage = conditional('≤40% for eligible public facilities in new areas · QCVN 2.6.3');

// These are applicability hints, never parcel-level permissions or numeric defaults.
// Each of the 22 catalog zoning groups is listed explicitly so new groups cannot silently inherit a rule.
const groups: Record<string, Partial<Record<RuleKey, RuleHint>>> = {
  RES: { coverage: conditional('Detached house: Table 2.8; apartment: Table 2.9'),
    far: conditional('Detached house ≤7; other forms need their own basis'), setback_front: front },
  MIX: { coverage: conditional('High-rise mixed use: Table 2.10 if applicable'),
    far: conditional('Existing urban case: Table 2.12 if applicable'), setback_front: front },
  COM: { coverage: conditional('High-rise retail: Table 2.10; public market may use 40%'),
    far: conditional('Existing urban case: Table 2.12 if applicable'), setback_front: front },
  IND: { coverage: conditional('Factory / warehouse ≤70%; >5 production floors ≤60% if in scope') },
  TEC: { coverage: conditional('Depends on actual building use: factory, lab, or office') },
  EDU: { coverage: publicCoverage, setback_front: front },
  HEA: { coverage: publicCoverage, setback_front: front },
  SOC: { coverage: conditional('≤40% only if a qualifying public facility in a new area') },
  CUL: { coverage: publicCoverage, setback_front: front },
  SPT: { coverage: conditional('≤40% for eligible public buildings; outdoor fields differ') },
  GOV: {},
  DEF: {},
  PRK: { coverage: { state: 'unknown', text: 'Park 5% / theme park 25% are gross density, not net coverage' } },
  TRN: { coverage: { state: 'unknown', text: 'Road: N/A; station or terminal: approved plan required' } },
  UTL: {},
  FLO: { coverage: { state: 'unknown', text: 'Canal / reservoir: N/A; structures need a separate plan' } },
  AGR: { coverage: { state: 'unknown', text: 'Agricultural land code gives no building entitlement' } },
  FOR: { coverage: { state: 'unknown', text: 'Forest land code gives no building entitlement' } },
  WAT: Object.fromEntries(RULE_FIELDS.map(([key]) => [key, notApplicable('Open water · separate permitted structure required')])) as Record<RuleKey, RuleHint>,
  HER: {},
  REL: {},
  UND: { max_height: { state: 'unknown', text: 'Building entitlement undetermined' },
    max_floors: { state: 'unknown', text: 'Building entitlement undetermined' } },
};

const subtype: Record<string, Partial<Record<RuleKey, RuleHint>>> = {
  'RES-V': { max_floors: conditional('HCMC villa: ≤3 floors if the local rule applies'),
    coverage: conditional('Detached villa ≤50%; semi-detached ≤55% if the local rule applies'),
    setback_front: conditional('HCMC villa: ≥3 m to road/alley boundary if applicable'),
    setback_side: conditional('HCMC villa: ≥2 m to parcel boundary, with exceptions') },
  'TRN-R': Object.fromEntries(RULE_FIELDS.map(([key]) => [key, notApplicable('Road right-of-way')])) as Record<RuleKey, RuleHint>,
};

export const RULE_SOURCE = 'QCVN 01:2021/BXD (effective before 2027); HCMC Decision 56/2021 for applicable villas. Verify the approved plan and scope.';

export function ruleGuidance(code: string): { field: RuleKey; hint: RuleHint }[] {
  const parent = code.split('-')[0].toUpperCase();
  const base = groups[parent];
  return RULE_FIELDS.map(([field]) => ({ field, hint: subtype[code.toUpperCase()]?.[field] ?? base?.[field] ?? defaultHint }));
}

export function isZoningCode(code: string): boolean {
  return Object.hasOwn(groups, code.split('-')[0].toUpperCase());
}
