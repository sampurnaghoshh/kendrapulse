import StabilityBadge from './StabilityBadge.jsx'
import { LABEL_TEXT, attributionFor, counterfactualWorld, displayText, firstName, kendraLabel } from '../snapshot.js'

// One card per clicked member. `revealedWeek` is the latest week the card has been on
// screen for: the explanation appears once the slider has reached her first flag, and then
// stays, because moving the slider does not make an explanation untrue. It never appears
// before her flag week, which would be showing the officer the future.
export default function ExplanationCard({
  snapshot,
  member,
  week,
  revealedWeek,
  selected,
  whatIfOn,
  onToggleWhatIf,
  onSelect,
  onClose,
}) {
  const attribution = attributionFor(snapshot, member.id)
  const revealed = attribution !== null && attribution.first_flag_week <= revealedWeek
  const name = firstName(member)

  return (
    <article className={`card explanation-card${selected ? ' is-selected' : ''}`} onClick={onSelect}>
      <header className="card-head">
        <h2>{name}</h2>
        <span className="card-kendra">{kendraLabel(member.kendra_id)}</span>
        {revealed && (
          <span className={`label-chip label-${attribution.label.toLowerCase()}`}>
            {LABEL_TEXT[attribution.label]}
          </span>
        )}
        <button
          className="card-close"
          aria-label={`Close the card for ${name}`}
          onClick={(ev) => {
            ev.stopPropagation()
            onClose()
          }}
        >
          ×
        </button>
      </header>

      {revealed ? (
        <>
          <p className="card-sentence">{displayText(snapshot, attribution.sentence)}</p>
          <StabilityBadge stability={attribution.stability} />
          {snapshot.counterfactual_worlds[member.id] && (
            <WhatIf snapshot={snapshot} member={member} week={week} on={whatIfOn} onToggle={onToggleWhatIf} />
          )}
        </>
      ) : (
        <p className="card-sentence quiet">Not flagged up to week {week}.</p>
      )}
    </article>
  )
}

// The toggle swaps the graph into this member's counterfactual world. The line under it is
// read from that world's own ring data at the current week, so it tracks the slider.
function WhatIf({ snapshot, member, week, on, onToggle }) {
  const world = counterfactualWorld(snapshot, member.id)
  const flaggedThere = world.everFlagged[member.id][week - 1]
  const name = firstName(member)
  return (
    <div className="whatif" onClick={(ev) => ev.stopPropagation()}>
      <label className="whatif-toggle">
        <input type="checkbox" role="switch" checked={on} onChange={onToggle} />
        <span className="switch" aria-hidden="true" />
        What if
      </label>
      {on && (
        <p className="whatif-result">
          In this world {name} {flaggedThere ? `is flagged by week ${week}` : `is not flagged up to week ${week}`}.
        </p>
      )}
    </div>
  )
}
