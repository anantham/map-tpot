import { LEGACY_MAP_NOTICE } from './legacyCommunitySemantics'

export default function LegacyMapNotice() {
  return (
    <div
      role="note"
      style={{
        margin: '8px 0',
        padding: '6px 8px',
        border: '1px solid rgba(212, 175, 55, 0.35)',
        borderRadius: 6,
        background: 'rgba(212, 175, 55, 0.08)',
        color: '#d6bd69',
        fontSize: 11,
        lineHeight: 1.35,
      }}
    >
      {LEGACY_MAP_NOTICE}
    </div>
  )
}
