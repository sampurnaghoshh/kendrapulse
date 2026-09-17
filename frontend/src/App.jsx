import { useEffect, useMemo, useRef, useState } from 'react'
import GraphView, { GraphLegend } from './components/GraphView.jsx'
import ExplanationCard from './components/ExplanationCard.jsx'
import OfficerNote from './components/OfficerNote.jsx'
import SmallestFixPanel from './components/SmallestFixPanel.jsx'
import TwoWorldsView from './components/TwoWorldsView.jsx'
import ValidationView from './components/ValidationView.jsx'
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
  // Side by side view, same shape as `alternate`. Kept separate so opening and closing it
  // leaves the single graph exactly as it was (What if, applied fix or reality).
  const [split, setSplit] = useState(null)
  // "How we tested it" opens at the top of the side panel, never over the graph.
  const [validationOpen, setValidationOpen] = useState(false)

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

  // The two worlds for the side by side view: reality on the left in both uses.
  const splitView = useMemo(() => {
    if (!snapshot || !split) return null
    if (split.kind === 'whatif') {
      const right = counterfactualWorld(snapshot, split.id)
      return {
        left: reality,
        right,
        leftTitle: 'Reality',
        rightTitle: right.title,
        rightPhrase: `in the ${lowerFirst(right.title)}`,
        targetId: split.id,
      }
    }
    const right = fixWorld(snapshot, split.rank)
    return {
      left: reality,
      right,
      leftTitle: 'Without the fix',
      rightTitle: right.title,
      rightPhrase: lowerFirst(right.title),
      targetId: right.fix.intervention.member_id,
    }
  }, [snapshot, split, reality])

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

  function toggleValidation() {
    setValidationOpen((open) => !open)
    panelRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function togglePlay() {
    // Pressing play on the last week replays the quarter from the start.
    if (!playing && week >= horizon) setWeek(1)
    setPlaying((p) => !p)
  }

  if (error) return <p className="load-error">{error}</p>
  if (!snapshot) return <p className="loading">Loading the branch</p>

  const byId = membersById(snapshot)
  // The split screen follows the selected member; without one it falls back to whoever the
  // world is about (the What if member, or the member the fix is aimed at).
  const subjectId = splitView ? (selectedId ?? splitView.targetId) : null

  return (
    <div className={`app${splitView && !validationOpen ? ' is-split' : ''}`}>
      <header className="app-header">
        <h1>KendraPulse</h1>
        <span className="branch">Davanagere branch</span>
        <button
          className={`header-button${validationOpen ? ' is-on' : ''}`}
          aria-pressed={validationOpen}
          onClick={toggleValidation}
        >
          How we tested it
        </button>
        {/* A statement, not a control: plain text with a drawn eye, nothing to click or tab to. */}
        <span className="private-tag">
          <svg className="eye" viewBox="0 0 16 10" aria-hidden="true">
            <path className="eye-outline" d="M1 5 C3.5 1 12.5 1 15 5 C12.5 9 3.5 9 1 5 Z" />
            <circle className="eye-pupil" cx="8" cy="5" r="2" />
          </svg>
          Officer view only. Never shown to the group.
        </span>
      </header>

      {splitView ? (
        <main className="graph-pane split-pane">
          <TwoWorldsView
            snapshot={snapshot}
            leftWorld={splitView.left}
            rightWorld={splitView.right}
            leftTitle={splitView.leftTitle}
            rightTitle={splitView.rightTitle}
            rightPhrase={splitView.rightPhrase}
            focusKendra={byId[subjectId].kendra_id}
            week={week}
            horizon={horizon}
            subjectId={subjectId}
            selectedId={selectedId}
            onSelect={selectMember}
            onClose={() => setSplit(null)}
          />
        </main>
      ) : (
        <main className={`graph-pane${world.alternate ? ' is-whatif' : ''}`}>
          {world.alternate && (
            <div className="world-banner" role="status">
              <span className="world-title">{world.title}</span>
              <span className="world-note">Same weeks, same dice, same positions</span>
              <button className="back-to-reality" onClick={() => setAlternate(null)}>
                Back to reality
              </button>
              {world.fix && (
                <button className="back-to-reality" onClick={() => setSplit(alternate)}>
                  Side by side
                </button>
              )}
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
      )}

      {splitView && !validationOpen ? (
        // Collapsed to a narrow strip so both graphs get the width. Cards keep their state
        // in the app and come back unchanged on Close. Opening "How we tested it" brings the
        // panel back beside the two graphs rather than over them.
        <aside className="side-panel is-strip" aria-label="Side panel hidden while side by side">
          <span className="strip-text">Cards return on Close</span>
        </aside>
      ) : (
        <aside className="side-panel" ref={panelRef}>
          {validationOpen && <ValidationView snapshot={snapshot} onClose={() => setValidationOpen(false)} />}
          <OfficerNote snapshot={snapshot} week={week} />
          {cards.length === 0 && !(fixOpen && week >= snapshot.smallest_fix.decision_week) && (
            <p className="panel-hint">Click a member to see why she is flagged.</p>
          )}
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
              onSideBySide={() => {
                setSelectedId(card.id)
                setSplit({ kind: 'whatif', id: card.id })
              }}
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
      )}

      <footer className="slider-bar">
        <WeekSlider week={week} weeks={horizon} playing={playing} onWeek={setWeek} onTogglePlay={togglePlay} />
      </footer>
    </div>
  )
}

// "World without Lakshmi's illness" reads as "world without Lakshmi's illness" mid sentence.
function lowerFirst(text) {
  return text[0].toLowerCase() + text.slice(1)
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
        <span className="rupee-words">
          <span>loans on members</span> <span>flagged at some point so far</span>
        </span>
      </p>
    )
  }
  return (
    <p className="rupee-line" aria-live="polite">
      <strong>{here}</strong>
      {/* Two unbreakable phrases, so the line wraps between them and "so far" never ends up
          alone on a line. */}
      <span className="rupee-words">
        <span>of loans on members</span> <span>flagged at some point so far{world.alternate ? ' in this world' : ''}</span>
      </span>
    </p>
  )
}
