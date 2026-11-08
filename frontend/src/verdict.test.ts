import { describe, it, expect } from 'vitest';
import { verdictMeta } from '../src/types';

describe('verdictMeta', () => {
  it('covers all three verdicts', () => {
    expect(Object.keys(verdictMeta).sort()).toEqual(
      ['INCONCLUSIVE', 'LIKELY_AI_MANIPULATED', 'LIKELY_REAL'].sort()
    );
  });
});
