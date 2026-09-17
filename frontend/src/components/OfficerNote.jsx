import { displayText, firstName, formatRupees, kendraLabel, membersById } from '../snapshot.js'

// The officer's own note from the kendra meeting. It only appears from the week it was
// written: before that the officer has not heard anything. The savings line is read from
// the same run the note was checked against, not typed in.
export default function OfficerNote({ snapshot, week }) {
  const note = snapshot.officer_note
  if (week < note.week) return null
  const member = membersById(snapshot)[note.member_id]

  return (
    <article className="card officer-note">
      <header className="card-head">
        <h2>Officer's note</h2>
        <span className="card-kendra">
          Week {note.week}, {kendraLabel(member.kendra_id)}
        </span>
      </header>
      <p className="card-sentence">{displayText(snapshot, note.text)}</p>
      <p className="note-fact">
        {firstName(member)}'s savings: {formatRupees(note.buffer_start)} at the start of the quarter,{' '}
        {formatRupees(note.buffer_at_note)} on the day of the note.
      </p>
    </article>
  )
}
