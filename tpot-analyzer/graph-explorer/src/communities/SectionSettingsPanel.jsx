import { SECTION_KEYS, SECTION_LABELS, cardStyle } from './accountDeepDiveUtils'

export default function SectionSettingsPanel({ sections, onToggle }) {
  return (
    <div style={{
      ...cardStyle,
      marginBottom: 12,
      display: 'flex',
      flexWrap: 'wrap',
      gap: 8,
    }}>
      {SECTION_KEYS.map((key) => (
        <label
          key={key}
          style={{
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            cursor: 'pointer',
            color: 'var(--text, #e2e8f0)',
          }}
        >
          <input type="checkbox" checked={sections[key] ?? true} onChange={() => onToggle(key)} />
          {SECTION_LABELS[key]}
        </label>
      ))}
    </div>
  )
}
