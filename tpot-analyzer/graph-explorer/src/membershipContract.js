export const ACCOUNT_MEMBERSHIP_SCHEMA_VERSION = 'account-membership-affinity-v1'

const FORBIDDEN_LEGACY_FIELDS = [
  'probability',
  'probabilityRaw',
  'confidenceInterval95',
]

export function assertAccountMembershipResponse(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('Account membership response must be a JSON object')
  }

  if (payload.schemaVersion !== ACCOUNT_MEMBERSHIP_SCHEMA_VERSION) {
    throw new Error(
      `Unsupported account membership schema: expected ${ACCOUNT_MEMBERSHIP_SCHEMA_VERSION}, received ${String(payload.schemaVersion)}`
    )
  }
  if (payload.scoreSemantics !== 'affinity' || payload.calibrated !== false) {
    throw new Error(
      'Account membership response must expose an uncalibrated affinity'
    )
  }

  const legacyField = FORBIDDEN_LEGACY_FIELDS.find(field =>
    Object.prototype.hasOwnProperty.call(payload, field)
  )
  if (legacyField) {
    throw new Error(
      `Account membership response contains forbidden legacy field: ${legacyField}`
    )
  }

  return payload
}
