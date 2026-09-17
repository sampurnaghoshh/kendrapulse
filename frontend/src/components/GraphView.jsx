import { firstName, kendraGeometry, kendraLabel, membersById, rChipText } from '../snapshot.js'

// Layout coordinates come from the backend, so every view draws members in the same place.
// The viewBox is fixed around that layout (plus room for labels) rather than measured, so
// nothing jumps when the week changes.
const VIEWBOX = '-470 -500 940 880'
const NODE_R = 20

export default function GraphView({ snapshot, week, selectedId, onSelect }) {
  const { layout, edges } = snapshot.scenario
  const members = snapshot.scenario.members
  const byId = membersById(snapshot)

  // Only guarantee edges are drawn: they are the channel cover travels along. Shared income
  // and shared lender links cross the whole branch and would bury the picture.
  const guaranteeEdges = edges.filter((e) => e.type === 'guarantee')

  return (
    <svg className="graph" viewBox={VIEWBOX} role="img" aria-label={`Branch network in week ${week}`}>
      <g className="edges">
        {guaranteeEdges.map((e) => {
          const [x1, y1] = layout[e.from_id]
          const [x2, y2] = layout[e.to_id]
          return <line key={`${e.from_id}_${e.to_id}`} className="edge" x1={x1} y1={y1} x2={x2} y2={y2} />
        })}
      </g>

      <g className="kendras">
        {kendraGeometry(snapshot).map(({ kendraId, cx, top }) => (
          <g key={kendraId}>
            <text className="kendra-label" x={cx} y={top - 66} textAnchor="middle">
              {kendraLabel(kendraId)}
            </text>
            <RChip x={cx} y={top - 44} text={rChipText(snapshot, kendraId, week)} />
          </g>
        ))}
      </g>

      <g className="nodes">
        {members.map((m) => {
          const [x, y] = layout[m.id]
          const selected = m.id === selectedId
          return (
            <g
              key={m.id}
              className={`node${selected ? ' is-selected' : ''}`}
              transform={`translate(${x} ${y})`}
              onClick={() => onSelect(m.id)}
              role="button"
              tabIndex={0}
              aria-label={firstName(byId[m.id])}
              onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && onSelect(m.id)}
            >
              {selected && <circle className="node-select" r={NODE_R + 11} />}
              <circle className="node-body" r={NODE_R} />
              <text className="node-name" y={NODE_R + 19} textAnchor="middle">
                {firstName(m)}
              </text>
            </g>
          )
        })}
      </g>
    </svg>
  )
}

function RChip({ x, y, text }) {
  // Rough width from character count keeps the chip plain SVG with no text measuring.
  const width = text.length * 9.6 + 20
  return (
    <g className="r-chip" transform={`translate(${x} ${y})`}>
      <rect x={-width / 2} y={-14} width={width} height={28} rx={14} />
      <text y={6} textAnchor="middle">
        {text}
      </text>
    </g>
  )
}
