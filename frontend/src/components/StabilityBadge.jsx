// Two numbers, never merged into one percentage: how often the member is flagged at all
// across the perturbed reruns, and how often the cause matches among those. A member who
// is rarely flagged but always for the same reason reads very differently from one who is
// always flagged for shifting reasons.
export default function StabilityBadge({ stability }) {
  const { flagged_runs: flagged, n_runs: runs, matched } = stability
  return (
    <div className="stability-badge">
      <div className="stability-row">
        <span className="stability-num">
          {flagged} <span className="of">of {runs}</span>
        </span>
        <span className="stability-what">reruns flag her</span>
      </div>
      <div className="stability-row">
        <span className="stability-num">
          {matched} <span className="of">of {flagged}</span>
        </span>
        <span className="stability-what">flagged reruns find the same cause</span>
      </div>
      <p className="stability-note">Each rerun uses new dice and nudges every tunable parameter.</p>
    </div>
  )
}
