import { LEGACY_MAP_NOTICE } from './legacyCommunitySemantics'

export default function LegacyMapNotice({ compact = false }) {
  return (
    <div
      role="note"
      style={{
        padding: compact ? '6px 8px' : '8px 16px',
        background: 'rgba(245, 158, 11, 0.10)',
        borderBottom: compact ? 'none' : '1px solid rgba(245, 158, 11, 0.25)',
        borderRadius: compact ? 6 : 0,
        color: 'var(--text, #92400e)',
        fontSize: 12,
        fontWeight: 600,
        lineHeight: 1.45,
      }}
    >
      {LEGACY_MAP_NOTICE}
    </div>
  )
}
