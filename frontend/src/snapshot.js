// Everything on screen comes from frontend/public/demo_snapshot.json, which
// backend/scripts/export_snapshot.py writes from real runs. This module only reshapes
// that data for display (first names, "Kendra 1" labels, rupee formatting). It never
// invents a number.

export async function loadSnapshot() {
  // BASE_URL keeps the path right if the app is ever served from a sub folder.
  const res = await fetch(`${import.meta.env.BASE_URL}demo_snapshot.json`)
  if (!res.ok) throw new Error(`Could not load the demo snapshot (${res.status})`)
  return res.json()
}

// Display rule: first names only. The full name stays in the data, never on screen.
export function firstName(member) {
  return member.name.split(' ')[0]
}

// Display rule: k0 is "Kendra 1". Internal ids never reach the screen.
export function kendraLabel(kendraId) {
  return `Kendra ${Number(kendraId.slice(1)) + 1}`
}

// Snapshot sentences are written by the backend with full names and internal ids. This
// rewrites them for the screen: full names become first names, "k2" becomes "Kendra 3",
// and any hyphen or dash becomes a space (UI copy has none; this is a guard, not a fix).
export function displayText(snapshot, text) {
  const members = [...snapshot.scenario.members].sort((a, b) => b.name.length - a.name.length)
  let out = text
  for (const m of members) out = out.split(m.name).join(firstName(m))
  const byId = membersById(snapshot)
  out = out.replace(/\bm\d{3}\b/g, (id) => (byId[id] ? firstName(byId[id]) : 'a member'))
  out = out.replace(/\bk(\d+)\b/g, (id) => kendraLabel(id))
  return out.replace(/\s*[-‐-―]\s*/g, ' ')
}

export function attributionFor(snapshot, memberId) {
  return snapshot.attribution.find((a) => a.member_id === memberId) ?? null
}

export const LABEL_TEXT = {
  INDEX: 'Index case',
  TRANSMITTED: 'Transmitted',
  INDEPENDENT: 'Independent',
}

export function membersById(snapshot) {
  return Object.fromEntries(snapshot.scenario.members.map((m) => [m.id, m]))
}

// Per kendra: centre and top edge of its cluster, so the label and R chip sit above it.
export function kendraGeometry(snapshot) {
  const { layout, kendras } = snapshot.scenario
  return Object.entries(kendras).map(([kendraId, memberIds]) => {
    const points = memberIds.map((id) => layout[id])
    const cx = points.reduce((sum, p) => sum + p[0], 0) / points.length
    const top = Math.min(...points.map((p) => p[1]))
    return { kendraId, cx, top }
  })
}

// A "world" is what the graph draws: weekly member states plus the persistent ring.
// Reality is the actual run; step 4 adds the counterfactual worlds in the same shape.
export function realityWorld(snapshot) {
  return {
    weeks: snapshot.actual.weeks,
    everFlagged: snapshot.ever_flagged_by_week,
    coverEdges: (week) => coverEdgesFromLog(snapshot, week),
  }
}

// Guarantee cover paid in a week, as member id pairs, read straight from the event log.
function coverEdgesFromLog(snapshot, week) {
  const entry = snapshot.actual.timeline.find((t) => t.week === week)
  return (entry?.events ?? [])
    .filter((e) => e.channel === 'guarantee')
    .map((e) => edgeKey(e.from_id, e.to_id))
}

// Order independent key, so an edge stored m010 to m011 matches cover paid m011 to m010.
export function edgeKey(a, b) {
  return a < b ? `${a}|${b}` : `${b}|${a}`
}

// The R chip always names its kind. R live exists only once the kendra has an index case
// (null before that), so until then the chip shows R potential, as CLAUDE.md specifies.
export function rChipText(snapshot, kendraId, week) {
  const r = snapshot.r.find((row) => row.kendra_id === kendraId)
  const live = r.r_live_by_week[week - 1]
  if (live === null) return `R potential ${r.r_potential.toFixed(2)}`
  return `R live ${live.toFixed(2)}`
}
