import { useState } from 'react'
import GraphView, { GraphLegend } from './GraphView.jsx'
import StabilityBadge from './StabilityBadge.jsx'
import { attributionFor, firstName, membersById } from '../snapshot.js'

// Two graphs of the same members, same positions, same week, one world each. Generic on
// purpose: a What if (reality against the world without the source shock) and an applied
// fix (reality against the fix replay) are the same picture with different titles.
//
// Both panels read the one `week` from the app's shared slider, so they can never drift
// apart. Every status, ring, pulse, R chip and shield comes from the two world objects;
// this component only lays them out and finds the week where they first differ.
export default function TwoWorldsView({
  snapshot,
  leftWorld,
  rightWorld,
  leftTitle,
  rightTitle,
  rightPhrase,
  focusKendra,
  week,
  horizon,
  subjectId,
  selectedId,
  subjectRevealed,
  onSelect,
  onClose,
}) {
  // Focus mode by default: one kendra, large enough to read five first names at 1280x720.
  const [wholeBranch, setWholeBranch] = useState(false)
  const kendra = wholeBranch ? undefined : focusKendra

  const subject = subjectId ? membersById(snapshot)[subjectId] : null
  const divergence = subject ? firstDivergence(leftWorld, rightWorld, subject.id, horizon) : null
  const diverged = divergence !== null && week >= divergence

  const panel = (world, title, side, flashId) => (
    <div className={`split-panel is-${side}`}>
      <h2 className="split-title">{title}</h2>
      <GraphView
        snapshot={snapshot}
        world={world}
        week={week}
        selectedId={selectedId}
        onSelect={onSelect}
        focusKendra={kendra}
        flashId={flashId}
      />
    </div>
  )

  return (
    <section className="two-worlds" aria-label="Two worlds side by side">
      <div className="split-toolbar">
        <span className="split-heading">Side by side</span>
        <span className="split-note">Same weeks, same dice, same positions</span>
        <label className="whatif-toggle split-switch">
          <input
            type="checkbox"
            role="switch"
            checked={wholeBranch}
            onChange={() => setWholeBranch((on) => !on)}
          />
          <span className="switch" aria-hidden="true" />
          Show whole branch
        </label>
        <button className="split-close" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="split-panels">
        {panel(leftWorld, leftTitle, 'left', null)}
        {/* The flash marks the divergence week only, on the side where things went differently. */}
        {panel(rightWorld, rightTitle, 'right', week === divergence ? subject?.id : null)}
      </div>

      <p className={`divergence-caption${diverged ? ' is-diverged' : ''}`} aria-live="polite">
        {diverged
          ? `Week ${divergence}: ${firstName(subject)} ${statusPhrase(rightWorld, subject.id, divergence)} ${rightPhrase}`
          : 'Both worlds share every week until the removed cause makes a difference'}
      </p>

      <div className="split-foot">
        <GraphLegend showProtected={Boolean(rightWorld.fix)} />
        <TransmittedLine snapshot={snapshot} member={subject} revealed={subjectRevealed} />
      </div>
    </section>
  )
}

// First week the member's status differs between the two worlds, or null if it never does.
// Both worlds share their dice, so any difference is caused by what was changed.
function firstDivergence(left, right, memberId, horizon) {
  for (let w = 1; w <= horizon; w++) {
    if (left.weeks[String(w)][memberId].status !== right.weeks[String(w)][memberId].status) return w
  }
  return null
}

const STATUS_PHRASE = { green: 'stays green', amber: 'is on watch', red: 'is stressed' }

function statusPhrase(world, memberId, week) {
  return STATUS_PHRASE[world.weeks[String(week)][memberId].status]
}

// Under the right panel: where a transmitted member's stress came from, with the same two
// number badge as her card. Only once her card has revealed it, never ahead of the story.
function TransmittedLine({ snapshot, member, revealed }) {
  const attribution = member ? attributionFor(snapshot, member.id) : null
  if (!attribution || attribution.label !== 'TRANSMITTED' || !revealed) return <div />
  const source = membersById(snapshot)[attribution.source_id]
  return (
    <div className="split-transmitted">
      <p className="split-source">
        {firstName(member)}: Transmitted from {firstName(source)}
      </p>
      <StabilityBadge stability={attribution.stability} />
    </div>
  )
}
