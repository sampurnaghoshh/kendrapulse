import {
  KENDRA_CHIP_DY,
  KENDRA_TITLE_DY,
  edgeKey,
  firstName,
  kendraGeometry,
  kendraLabel,
  kendraViewBox,
  nameOffsets,
  rChipText,
} from '../snapshot.js'

// Layout coordinates come from the backend, so every view draws members in the same place.
// The viewBox is fixed around that layout (plus room for labels) rather than measured, so
// nothing jumps when the week or the world changes.
const VIEWBOX = '-500 -535 1000 925'
const NODE_R = 20
// The persistent ring sits a few units off the node so it reads as a separate mark.
const RING_R = NODE_R + 7
// Names start just outside the ring and the selection disc.
const NAME_GAP = RING_R + 9

// Status must not rely on colour alone: amber carries one mark, red two.
const STATUS_MARK = { green: '', amber: '!', red: '!!' }

// `focusKendra` (optional) draws only that kendra, zoomed in; the split screen uses it so five
// names stay readable in a half width panel. `flashId` (optional) briefly pulses one node.
export default function GraphView({ snapshot, world, week, selectedId, onSelect, focusKendra, flashId }) {
  const { layout, edges } = snapshot.scenario
  const states = world.weeks[String(week)]
  const pulsing = new Set(world.coverEdges(week))
  const inFocus = (id) => !focusKendra || snapshot.scenario.kendras[focusKendra].includes(id)
  const members = snapshot.scenario.members.filter((m) => inFocus(m.id))

  // Only guarantee edges are drawn: they are the channel cover travels along. Shared income
  // and shared lender links cross the whole branch and would bury the picture. Guarantee
  // edges never leave a kendra, so filtering on one end is enough in focus mode.
  const guaranteeEdges = edges.filter((e) => e.type === 'guarantee' && inFocus(e.from_id))
  const viewBox = focusKendra ? kendraViewBox(snapshot, focusKendra) : VIEWBOX
  const label = focusKendra ? `${kendraLabel(focusKendra)} in week ${week}` : `Branch network in week ${week}`
  const names = nameOffsets(snapshot, NAME_GAP)

  return (
    <svg className="graph" viewBox={viewBox} role="img" aria-label={label}>
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
        {kendraGeometry(snapshot)
          .filter(({ kendraId }) => !focusKendra || kendraId === focusKendra)
          .map(({ kendraId, cx, top }) => (
            <g key={kendraId}>
              <text className="kendra-label" x={cx} y={top + KENDRA_TITLE_DY} textAnchor="middle">
                {kendraLabel(kendraId)}
              </text>
              <RChip x={cx} y={top + KENDRA_CHIP_DY} text={rChipText(snapshot, kendraId, week, world)} />
            </g>
          ))}
      </g>

      <g className="nodes">
        {members.map((m) => {
          const [x, y] = layout[m.id]
          const status = states[m.id].status
          const ringed = world.everFlagged[m.id][week - 1]
          const selected = m.id === selectedId
          const isProtected = Boolean(world.isProtected?.(m.id, week))
          return (
            <g
              key={m.id}
              className={`node status-${status}${selected ? ' is-selected' : ''}`}
              transform={`translate(${x} ${y})`}
              onClick={() => onSelect(m.id)}
              role="button"
              tabIndex={0}
              aria-label={`${firstName(m)}, ${status}${ringed ? ', flagged at some point so far' : ''}${isProtected ? ', protected by the fix' : ''}`}
              onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && onSelect(m.id)}
            >
              {selected && <circle className="node-select" r={NODE_R + 13} />}
              {/* Keyed by week so the flash plays again if the slider comes back to it. */}
              {m.id === flashId && <circle key={`flash@${week}`} className="node-flash" r={NODE_R + 13} />}
              {ringed && <circle className="node-ring" r={RING_R} />}
              <circle className="node-body" r={NODE_R} />
              <text className="node-mark" y={6} textAnchor="middle">
                {STATUS_MARK[status]}
              </text>
              {isProtected && <ShieldMark x={NODE_R + 3} y={10} />}
              <text className="node-name" x={names[m.id].x} y={names[m.id].y} textAnchor={names[m.id].anchor}>
                {firstName(m)}
              </text>
            </g>
          )
        })}
      </g>
    </svg>
  )
}

// Small shield with a check: this member would have been flagged by now without the fix.
function ShieldMark({ x, y }) {
  return (
    <g className="shield" transform={`translate(${x} ${y})`} aria-hidden="true">
      <path d="M0 -11 L10 -7 L10 1 C10 7 5 11 0 13 C-5 11 -10 7 -10 1 L-10 -7 Z" />
      <path className="shield-check" d="M-5 1 L-1 5 L5 -3" />
    </g>
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

export function GraphLegend({ showProtected }) {
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
      {showProtected && (
        <li>
          <svg className="shield-sample" viewBox="-12 -13 24 28" aria-hidden="true">
            <g className="shield">
              <path d="M0 -11 L10 -7 L10 1 C10 7 5 11 0 13 C-5 11 -10 7 -10 1 L-10 -7 Z" />
              <path className="shield-check" d="M-5 1 L-1 5 L5 -3" />
            </g>
          </svg>
          Protected by the fix
        </li>
      )}
    </ul>
  )
}
