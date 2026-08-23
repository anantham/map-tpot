import { describe, expect, it } from 'vitest'

import {
  ACCOUNT_MEMBERSHIP_SCHEMA_VERSION,
  assertAccountMembershipResponse,
} from './membershipContract'

function validPayload(overrides = {}) {
  return {
    schemaVersion: ACCOUNT_MEMBERSHIP_SCHEMA_VERSION,
    scoreSemantics: 'affinity',
    calibrated: false,
    affinity: 0.42,
    ...overrides,
  }
}

describe('account membership response contract', () => {
  it('accepts the versioned uncalibrated affinity shape', () => {
    const payload = validPayload()

    expect(assertAccountMembershipResponse(payload)).toBe(payload)
  })

  it.each([
    ['missing', undefined],
    ['stale', 'account-membership-v0'],
  ])('rejects a %s schema version', (_label, schemaVersion) => {
    expect(() =>
      assertAccountMembershipResponse(validPayload({ schemaVersion }))
    ).toThrow(/Unsupported account membership schema/i)
  })

  it('rejects a calibrated-probability contract under the affinity schema', () => {
    expect(() =>
      assertAccountMembershipResponse(validPayload({
        scoreSemantics: 'probability',
        calibrated: true,
        probability: 0.42,
      }))
    ).toThrow(/uncalibrated affinity/i)
  })

  it('rejects legacy probability and confidence-interval fields', () => {
    expect(() =>
      assertAccountMembershipResponse(validPayload({
        confidenceInterval95: [0.2, 0.6],
      }))
    ).toThrow(/forbidden legacy field: confidenceInterval95/i)
  })
})
