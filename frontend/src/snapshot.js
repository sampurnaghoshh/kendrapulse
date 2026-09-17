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

// The R chip always names its kind. R live exists only once the kendra has an index case
// (null before that), so until then the chip shows R potential, as CLAUDE.md specifies.
export function rChipText(snapshot, kendraId, week) {
  const r = snapshot.r.find((row) => row.kendra_id === kendraId)
  const live = r.r_live_by_week[week - 1]
  if (live === null) return `R potential ${r.r_potential.toFixed(2)}`
  return `R live ${live.toFixed(2)}`
}
