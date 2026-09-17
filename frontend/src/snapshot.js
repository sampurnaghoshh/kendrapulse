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

// A counterfactual world from the snapshot, in the same shape as reality so GraphView
// draws it unchanged: same slider, same node positions, only the member states differ.
export function counterfactualWorld(snapshot, memberId) {
  const world = snapshot.counterfactual_worlds[memberId]
  return {
    weeks: world.weeks,
    everFlagged: world.ever_flagged_by_week,
    coverEdges: (week) => coverEdgesFromWeeks(snapshot, world.weeks, week),
    counterfactual: true,
    title: worldTitle(snapshot, memberId),
  }
}

// Counterfactual worlds carry weekly states but no event log. Guarantee cover only flows
// inside a kendra, so pair each member who gave cover that week with each who received it.
// On the actual run this reproduces the event log's guarantee pairs in all 12 weeks.
function coverEdgesFromWeeks(snapshot, weeks, week) {
  const states = weeks[String(week)]
  const keys = []
  for (const ids of Object.values(snapshot.scenario.kendras)) {
    const givers = ids.filter((id) => states[id].cover_given > 0)
    const receivers = ids.filter((id) => states[id].cover_received > 0)
    for (const g of givers) for (const r of receivers) if (g !== r) keys.push(edgeKey(g, r))
  }
  return keys
}

// Plain words for each shock type, for the banner ("World without Lakshmi's illness").
const SHOCK_WORDS = {
  health: 'illness',
  crop_loss: 'crop loss',
  job_loss: 'job loss',
  festival_spend: 'festival spending',
  weak_monsoon: 'weak monsoon',
}

function worldTitle(snapshot, memberId) {
  const world = snapshot.counterfactual_worlds[memberId]
  const attribution = attributionFor(snapshot, memberId)
  if (world.kind === 'without_source' && world.removed_member_id && attribution) {
    const source = membersById(snapshot)[world.removed_member_id]
    let cause = 'trouble'
    if (attribution.source_cause === 'trend') cause = 'slipping income'
    if (attribution.source_cause === 'shock') {
      const shock = snapshot.shock.shocks.find((s) => s.member_id === source.id)
      if (shock) cause = SHOCK_WORDS[shock.type] ?? 'shock'
    }
    return `World without ${firstName(source)}'s ${cause}`
  }
  // Other kinds keep the backend's own title, rewritten for the screen.
  return displayText(snapshot, world.title).replace(/^The world/, 'World')
}

// Order independent key, so an edge stored m010 to m011 matches cover paid m011 to m010.
export function edgeKey(a, b) {
  return a < b ? `${a}|${b}` : `${b}|${a}`
}

// The R chip always names its kind. R live exists only once the kendra has an index case
// (null before that), so until then the chip shows R potential, as CLAUDE.md specifies.
//
// A counterfactual world has no R live in the snapshot. R potential is a property of the
// network, so it still holds for a kendra with nobody flagged in that world. A kendra with a
// flag there would need attribution rerun inside that world, so the chip says it is not
// scored rather than borrowing reality's number.
export function rChipText(snapshot, kendraId, week, world) {
  const r = snapshot.r.find((row) => row.kendra_id === kendraId)
  if (world?.counterfactual) {
    const flagged = snapshot.scenario.kendras[kendraId].some((id) => world.everFlagged[id][week - 1])
    return flagged ? 'R live not scored here' : `R potential ${r.r_potential.toFixed(2)}`
  }
  const live = r.r_live_by_week[week - 1]
  if (live === null) return `R potential ${r.r_potential.toFixed(2)}`
  return `R live ${live.toFixed(2)}`
}
