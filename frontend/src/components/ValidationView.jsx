import { LABEL_TEXT } from '../snapshot.js'

// "How we tested it". Every count is read from snapshot.validation, which export_snapshot.py
// copies from data/validation_report.json. Counts only, never percentages, and the rows
// where the simple rule wins are shown as plainly as the rows where the replay wins.
//
// "Replay" is the engine in anchored mode; "simple rule" is the baseline that reads only
// what a meeting record would show (who covered whom). Both are scored on all observed
// flagged members, so the two columns always share a denominator.
export default function ValidationView({ snapshot, onClose }) {
  const v = snapshot.validation
  if (!v) return null
  const { all_observed: all } = v
  // Runs per member from the stability data itself. The 30% is stability.py PERTURB_RANGE,
  // U(0.7, 1.3), a method setting rather than a result.
  const runs = snapshot.attribution[0]?.stability.n_runs

  const rows = ['INDEX', 'TRANSMITTED', 'INDEPENDENT'].map((label) => ({
    key: label,
    name: LABEL_TEXT[label],
    ...all.per_true_label[label],
  }))
  rows.push({ key: 'total', name: 'All flagged members', ...all.overall })

  return (
    <section className="card validation-view" aria-label="How we tested it">
      <header className="card-head">
        <h2>How we tested it</h2>
        <button className="card-close" aria-label="Close how we tested it" onClick={onClose}>
          ×
        </button>
      </header>

      <p className="card-sentence">
        {v.scenarios_scored} synthetic scenarios with planted causes. This tests the logic, not accuracy on
        real borrowers.
      </p>

      <table className="validation-table">
        <caption>Right cause found, all {all.n} flagged members</caption>
        <thead>
          <tr>
            <th scope="col">True label</th>
            <th scope="col">Replay</th>
            <th scope="col">Simple rule</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const replay = row.engine_anchored
            const rule = row.baseline
            return (
              <tr key={row.key} className={row.key === 'total' ? 'is-total' : ''}>
                <th scope="row">{row.name}</th>
                <td className={replay.correct > rule.correct ? 'is-better' : ''}>
                  {replay.correct} <span className="of">of {replay.of}</span>
                </td>
                <td className={rule.correct > replay.correct ? 'is-better' : ''}>
                  {rule.correct} <span className="of">of {rule.of}</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="validation-key">The simple rule reads meeting records: who covered whom.</p>

      <p className="card-sentence">
        The simple rule names contagion sources better. The replay better identifies borrowers whose own income
        is slipping, and only the replay can test a fix before it is tried.
      </p>
      <p className="card-sentence">
        Every label shows how often it held across {runs} reruns with parameters moved by up to 30%.
      </p>
    </section>
  )
}
