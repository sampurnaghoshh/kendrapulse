import { useEffect, useMemo, useRef, useState } from 'react'
import GraphView, { GraphLegend } from './components/GraphView.jsx'
import ExplanationCard from './components/ExplanationCard.jsx'
import OfficerNote from './components/OfficerNote.jsx'
import SmallestFixPanel from './components/SmallestFixPanel.jsx'
import WeekSlider from './components/WeekSlider.jsx'
import {
  attributionFor,
  counterfactualWorld,
  fixWorld,
  formatRupees,
  loadSnapshot,
  membersById,
  realityWorld,
  rupeesFlaggedSoFar,
} from './snapshot.js'

// About 700 ms per week: slow enough to read a colour change, fast enough for a video.
const MS_PER_WEEK = 700

function initialWeek() {
  const asked = Number(new URLSearchParams(window.location.search).get('week'))
  return Number.isInteger(asked) && asked >= 1 && asked <= 12 ? asked : 1
}

export default function App() {
  const [snapshot, setSnapshot] = useState(null)
  const [error, setError] = useState(null)
  // ?week=7 opens on that week, handy for rehearsing one moment of the recording.
  const [week, setWeek] = useState(initialWeek)
  const [playing, setPlaying] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  // Explanation cards, newest first: {id, revealedWeek}. See ExplanationCard for why
  // revealedWeek only ever grows.
  const [cards, setCards] = useState([])
  // The one alternate world on screen, if any: {kind: 'whatif', id} or {kind: 'fix', rank}.
  // A single state value, so a What if and an applied fix can never both be showing.
  const [alternate, setAlternate] = useState(null)
  const [fixOpen, setFixOpen] = useState(false)

  const panelRef = useRef(null)
  const fixRef = useRef(null)

  useEffect(() => {
    loadSnapshot().then(setSnapshot, (err) => setError(err.message))
  }, [])

  const horizon = snapshot?.params.horizon_weeks ?? 12
  const reality = useMemo(() => snapshot && realityWorld(snapshot), [snapshot])
  const world = useMemo(() => {
    if (!snapshot || !alternate) return reality
    if (alternate.kind === 'whatif') return counterfactualWorld(snapshot, alternate.id)
    return fixWorld(snapshot, alternate.rank)
  }, [snapshot, alternate, reality])

  const whatIfId = alternate?.kind === 'whatif' ? alternate.id : null
  const appliedRank = alternate?.kind === 'fix' ? alternate.rank : null

  // Advance one week per tick.
  useEffect(() => {
    if (!playing) return undefined
    const timer = setInterval(() => setWeek((w) => Math.min(w + 1, horizon)), MS_PER_WEEK)
    return () => clearInterval(timer)
  }, [playing, horizon])

  // Stop on the last week rather than looping, so a recording ends on the final state.
  useEffect(() => {
    if (playing && week >= horizon) setPlaying(false)
  }, [playing, week, horizon])

  // Cards on screen remember the furthest week they have been shown at.
  useEffect(() => {
    setCards((cs) =>
      cs.some((c) => c.revealedWeek < week)
        ? cs.map((c) => ({ ...c, revealedWeek: Math.max(c.revealedWeek, week) }))
        : cs,
    )
  }, [week])

  function isRevealed(card) {
    const a = attributionFor(snapshot, card.id)
    return a !== null && a.first_flag_week <= card.revealedWeek
  }

  function selectMember(id) {
    setSelectedId(id)
    setCards((cs) => {
      const existing = cs.find((c) => c.id === id)
      // Cards that explained something stay. A "not flagged yet" card for someone else is
      // dropped, so casual clicks do not pile up in the panel.
      const kept = cs.filter((c) => c.id !== id && isRevealed(c))
      return [existing ?? { id, revealedWeek: week }, ...kept]
    })
    // The new card goes to the top of the panel; bring it into view.
    panelRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function closeCard(id) {
    setCards((cs) => cs.filter((c) => c.id !== id))
    if (selectedId === id) setSelectedId(null)
    if (whatIfId === id) setAlternate(null)
  }

  function toggleWhatIf(id) {
    setAlternate((current) => (current?.kind === 'whatif' && current.id === id ? null : { kind: 'whatif', id }))
  }

  function openFixes(rank) {
    setFixOpen(true)
    // Wait one frame so the list exists before scrolling to it.
    requestAnimationFrame(() => {
      const target = rank ? document.getElementById(`fix-option-${rank}`) : fixRef.current
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  function togglePlay() {
    // Pressing play on the last week replays the quarter from the start.
    if (!playing && week >= horizon) setWeek(1)
    setPlaying((p) => !p)
  }

  if (error) return <p className="load-error">{error}</p>
  if (!snapshot) return <p className="loading">Loading the branch</p>

  const byId = membersById(snapshot)

  return (
    <div className="app">
      <header className="app-header">
        <h1>KendraPulse</h1>
        <span className="branch">Davanagere branch</span>
        <span className="private-tag">Visible to the loan officer only</span>
      </header>

      <main className={`graph-pane${world.alternate ? ' is-whatif' : ''}`}>
        {world.alternate && (
          <div className="world-banner" role="status">
            <span className="world-title">{world.title}</span>
            <span className="world-note">Same weeks, same dice, same positions</span>
            <button className="back-to-reality" onClick={() => setAlternate(null)}>
              Back to reality
            </button>
          </div>
        )}
        <GraphView
          snapshot={snapshot}
          world={world}
          week={week}
          selectedId={selectedId}
          onSelect={selectMember}
        />
        <RupeeLine snapshot={snapshot} reality={reality} world={world} week={week} />
        <GraphLegend showProtected={Boolean(world.fix)} />
      </main>

      <aside className="side-panel" ref={panelRef}>
        <OfficerNote snapshot={snapshot} week={week} />
        {cards.length === 0 && <p className="panel-hint">Click a member to see why she is flagged.</p>}
        {cards.map((card) => (
          <ExplanationCard
            key={card.id}
            snapshot={snapshot}
            member={byId[card.id]}
            week={week}
            revealedWeek={card.revealedWeek}
            selected={card.id === selectedId}
            whatIfOn={card.id === whatIfId}
            onToggleWhatIf={() => toggleWhatIf(card.id)}
            onOpenFix={openFixes}
            onSelect={() => setSelectedId(card.id)}
            onClose={() => closeCard(card.id)}
          />
        ))}
        <SmallestFixPanel
          ref={fixRef}
          snapshot={snapshot}
          week={week}
          open={fixOpen}
          appliedRank={appliedRank}
          onOpen={() => openFixes()}
          onApply={(rank) => setAlternate({ kind: 'fix', rank })}
          onBack={() => setAlternate(null)}
        />
      </aside>

      <footer className="slider-bar">
        <WeekSlider week={week} weeks={horizon} playing={playing} onWeek={setWeek} onTogglePlay={togglePlay} />
      </footer>
    </div>
  )
}

// Loans on members flagged at some point so far. With a fix applied it compares the two
// worlds side by side; in a What if world it names the world it is counting.
function RupeeLine({ snapshot, reality, world, week }) {
  const here = formatRupees(rupeesFlaggedSoFar(snapshot, world, week))
  if (world.fix) {
    return (
      <p className="rupee-line is-compare" aria-live="polite">
        <span className="compare">
          <strong>{formatRupees(rupeesFlaggedSoFar(snapshot, reality, week))}</strong> without the fix,
        </span>
        <span className="compare">
          <strong>{here}</strong> with it
        </span>
        <span>loans on members flagged at some point so far</span>
      </p>
    )
  }
  return (
    <p className="rupee-line" aria-live="polite">
      <strong>{here}</strong>
      <span>of loans on members flagged at some point so far{world.alternate ? ' in this world' : ''}</span>
    </p>
  )
}
