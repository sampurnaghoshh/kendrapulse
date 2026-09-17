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

// Indian digit grouping, as the snapshot's own text uses: Rs 4,20,707.
const RUPEES = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
export function formatRupees(amount) {
  return `Rs ${RUPEES.format(Math.round(amount))}`
}

// Loans outstanding on everyone flagged at some point up to this week in the given world.
// At week 12 of reality this equals the snapshot's rupees_at_risk; earlier weeks use the
// same rule on the ring data so the number grows as the story plays.
export function rupeesFlaggedSoFar(snapshot, world, week) {
  return snapshot.scenario.members
    .filter((m) => world.everFlagged[m.id][week - 1])
    .reduce((sum, m) => sum + m.total_outstanding, 0)
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

// A viewBox around one kendra, for the zoomed split screen panels. Padding leaves room for
// the kendra label and R chip above (drawn at top minus 66) and first names below the nodes.
export function kendraViewBox(snapshot, kendraId) {
  const points = snapshot.scenario.kendras[kendraId].map((id) => snapshot.scenario.layout[id])
  const xs = points.map((p) => p[0])
  const ys = points.map((p) => p[1])
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2
  const halfWidth = Math.max(170, (Math.max(...xs) - Math.min(...xs)) / 2 + 90)
  const top = Math.min(...ys) - 100
  const bottom = Math.max(...ys) + 52
  return `${cx - halfWidth} ${top} ${2 * halfWidth} ${bottom - top}`
}

// A "world" is what the graph draws: weekly member states plus the persistent ring.
// Reality is the actual run. What if worlds and fix replays use the same shape and set
// `alternate`, so the app can insist only one alternate world is ever on screen.
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
    alternate: true,
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

// A smallest fix replay from the snapshot (fix_replays), with what the ranked entry says
// about it: who it protects and the R live per kendra computed on that replay.
export function fixWorld(snapshot, rank) {
  const replay = snapshot.fix_replays.find((r) => r.rank === rank)
  const fix = snapshot.smallest_fix.ranked.find((r) => r.rank === rank)
  return {
    weeks: replay.weeks,
    everFlagged: replay.ever_flagged_by_week,
    coverEdges: (week) => coverEdgesFromWeeks(snapshot, replay.weeks, week),
    alternate: true,
    fix,
    title: interventionText(snapshot, fix.intervention, 'with'),
    rLiveByWeek: fix.r_live_by_week,
    // Protected so far: flagged by this week in reality, not flagged by this week with the
    // fix. At the horizon this is exactly the snapshot's members_protected; earlier weeks
    // only show the ones reality has already flagged, so the marker never runs ahead.
    isProtected: (id, week) =>
      fix.members_protected.includes(id) &&
      snapshot.ever_flagged_by_week[id][week - 1] &&
      !replay.ever_flagged_by_week[id][week - 1],
  }
}

// One intervention in three grammatical shapes, built from its fields so the wording stays
// in step with the numbers:
//   'do'   "Cut Lakshmi's installment by 50% from week 4"
//   'with' "With Lakshmi's installment cut by 50% from week 4"
//   'her'  "cut her installment by 50% from week 4"
export function interventionText(snapshot, iv, form) {
  const name = firstName(membersById(snapshot)[iv.member_id])
  const who = form === 'her' ? 'her' : `${name}'s`
  let text
  if (iv.type === 'moratorium') {
    const span = `for ${iv.weeks} weeks from week ${iv.start_week}`
    text = form === 'with' ? `With ${who} installments paused ${span}` : `pause ${who} installments ${span}`
  } else {
    const pct = Math.round(100 * (1 - iv.installment_fraction))
    const span = `by ${pct}% from week ${iv.start_week}`
    text = form === 'with' ? `With ${who} installment cut ${span}` : `cut ${who} installment ${span}`
  }
  return form === 'do' ? text[0].toUpperCase() + text.slice(1) : text
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
// A fix replay carries its own R live per kendra; use it wherever it exists. Beyond that,
// an alternate world has no R live in the snapshot. R potential is a property of the
// network, so it still holds for a kendra with nobody flagged in that world. A kendra with a
// flag there would need attribution rerun inside that world, so the chip says it is not
// scored rather than borrowing reality's number.
export function rChipText(snapshot, kendraId, week, world) {
  const r = snapshot.r.find((row) => row.kendra_id === kendraId)
  const fixLive = world?.rLiveByWeek?.[kendraId]?.[week - 1]
  if (fixLive !== undefined && fixLive !== null) return `R live ${fixLive.toFixed(2)}`
  if (world?.alternate) {
    const flagged = snapshot.scenario.kendras[kendraId].some((id) => world.everFlagged[id][week - 1])
    return flagged ? 'R live not scored here' : `R potential ${r.r_potential.toFixed(2)}`
  }
  const live = r.r_live_by_week[week - 1]
  if (live === null) return `R potential ${r.r_potential.toFixed(2)}`
  return `R live ${live.toFixed(2)}`
}
