import { forwardRef } from 'react'
import { displayText, firstName, interventionText, membersById } from '../snapshot.js'

// The ranked top 3 from the snapshot's smallest fix search. Hidden before the decision week:
// until the officer has heard about the illness there is nothing to fix. Every number here
// is read from smallest_fix.ranked and fix_replays; only the wording is built on screen.
const SmallestFixPanel = forwardRef(function SmallestFixPanel(
  { snapshot, week, open, appliedRank, onOpen, onApply, onBack },
  ref,
) {
  const { decision_week: decisionWeek, ranked } = snapshot.smallest_fix
  if (week < decisionWeek) return null
  const byId = membersById(snapshot)

  if (!open) {
    return (
      <div className="fix-panel" ref={ref}>
        <button className="find-fix" onClick={onOpen}>
          Find the smallest fix
        </button>
      </div>
    )
  }

  return (
    <section className="fix-panel" ref={ref}>
      <h2 className="fix-heading">Smallest fixes from week {decisionWeek}</h2>
      {ranked.map((fix) => {
        const applied = fix.rank === appliedRank
        const names = fix.members_protected.map((id) => firstName(byId[id]))
        return (
          <article
            key={fix.rank}
            id={`fix-option-${fix.rank}`}
            className={`card fix-option${applied ? ' is-applied' : ''}`}
          >
            <div className="fix-top">
              <span className="fix-rank">Option {fix.rank}</span>
              {applied ? (
                <button className="fix-button secondary" onClick={onBack}>
                  Back to reality
                </button>
              ) : (
                <button className="fix-button" onClick={() => onApply(fix.rank)}>
                  Apply
                </button>
              )}
            </div>
            <p className="fix-title">{interventionText(snapshot, fix.intervention, 'do')}</p>
            <p className="fix-line">
              Protects {names.length}: {names.join(', ')}
            </p>
            <p className="fix-line">Lender cost {fix.lender_cost_text} in interest carry</p>
            <p className="fix-line">{displayText(snapshot, fix.moved_text)}</p>
            {applied && <SupportLine snapshot={snapshot} fix={fix} />}
          </article>
        )
      })}
    </section>
  )
})

export default SmallestFixPanel

// A fix that protects the neighbours does not cure the member it is aimed at. Shown only
// when the replay says so: she is still flagged at the horizon with the fix, and everyone
// it protects is somebody else.
function SupportLine({ snapshot, fix }) {
  const target = fix.intervention.member_id
  const replay = snapshot.fix_replays.find((r) => r.rank === fix.rank)
  const flags = replay.ever_flagged_by_week[target]
  const stillFlagged = flags[flags.length - 1]
  const neighboursOnly = fix.members_protected.length > 0 && !fix.members_protected.includes(target)
  if (!stillFlagged || !neighboursOnly) return null
  const name = firstName(membersById(snapshot)[target])
  return <p className="fix-support">{name} still needs support. Her neighbours are protected.</p>
}
