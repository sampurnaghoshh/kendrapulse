import { edgeKey, firstName, kendraGeometry, kendraLabel, rChipText } from '../snapshot.js'

// Layout coordinates come from the backend, so every view draws members in the same place.
// The viewBox is fixed around that layout (plus room for labels) rather than measured, so
// nothing jumps when the week or the world changes.
const VIEWBOX = '-470 -495 940 875'
const NODE_R = 20

// Status must not rely on colour alone: amber carries one mark, red two.
const STATUS_MARK = { green: '', amber: '!', red: '!!' }

export default function GraphView({ snapshot, world, week, selectedId, onSelect }) {
  const { layout, edges, members } = snapshot.scenario
  const states = world.weeks[String(week)]
  const pulsing = new Set(world.coverEdges(week))

  // Only guarantee edges are drawn: they are the channel cover travels along. Shared income
  // and shared lender links cross the whole branch and would bury the picture.
  const guaranteeEdges = edges.filter((e) => e.type === 'guarantee')

  return (
    <svg className="graph" viewBox={VIEWBOX} role="img" aria-label={`Branch network in week ${week}`}>
      <g className="edges">
        {guaranteeEdges.map((e) => {
          const [x1, y1] = layout[e.from_id]
          const [x2, y2] = layout[e.to_id]
          return <line key={edgeKey(e.from_id, e.to_id)} className="edge" x1={x1} y1={y1} x2={x2} y2={y2} />
        })}
      </g>

      {/* Pulses sit in their own layer. The week is part of the key so React mounts a fresh
          element each week and the CSS animation plays again even on the same edge. */}
      <g className="pulses">
        {guaranteeEdges
          .filter((e) => pulsing.has(edgeKey(e.from_id, e.to_id)))
          .map((e) => {
            const [x1, y1] = layout[e.from_id]
            const [x2, y2] = layout[e.to_id]
            return (
              <line
                key={`${edgeKey(e.from_id, e.to_id)}@${week}`}
                className="edge-pulse"
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
              />
            )
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
          const status = states[m.id].status
          const ringed = world.everFlagged[m.id][week - 1]
          const selected = m.id === selectedId
          return (
            <g
              key={m.id}
              className={`node status-${status}${selected ? ' is-selected' : ''}`}
              transform={`translate(${x} ${y})`}
              onClick={() => onSelect(m.id)}
              role="button"
              tabIndex={0}
              aria-label={`${firstName(m)}, ${status}${ringed ? ', flagged at some point so far' : ''}`}
              onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && onSelect(m.id)}
            >
              {selected && <circle className="node-select" r={NODE_R + 13} />}
              {ringed && <circle className="node-ring" r={NODE_R + 6} />}
              <circle className="node-body" r={NODE_R} />
              <text className="node-mark" y={6} textAnchor="middle">
                {STATUS_MARK[status]}
              </text>
              <text className="node-name" y={NODE_R + 21} textAnchor="middle">
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

export function GraphLegend() {
  return (
    <ul className="legend">
      <li>
        <span className="swatch status-green" /> On track
      </li>
      <li>
        <span className="swatch status-amber">!</span> Watch
      </li>
      <li>
        <span className="swatch status-red">!!</span> Stressed
      </li>
      <li>
        <span className="swatch ring" /> Flagged at some point so far
      </li>
      <li>
        <span className="pulse-sample" /> Guarantee cover paid this week
      </li>
    </ul>
  )
}
