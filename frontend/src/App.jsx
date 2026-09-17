import { useEffect, useState } from 'react'
import GraphView from './components/GraphView.jsx'
import WeekSlider from './components/WeekSlider.jsx'
import { loadSnapshot } from './snapshot.js'

// About 700 ms per week: slow enough to read a colour change, fast enough for a video.
const MS_PER_WEEK = 700

export default function App() {
  const [snapshot, setSnapshot] = useState(null)
  const [error, setError] = useState(null)
  const [week, setWeek] = useState(1)
  const [playing, setPlaying] = useState(false)
  const [selectedId, setSelectedId] = useState(null)

  useEffect(() => {
    loadSnapshot().then(setSnapshot, (err) => setError(err.message))
  }, [])

  const horizon = snapshot?.params.horizon_weeks ?? 12

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

  function togglePlay() {
    // Pressing play on the last week replays the quarter from the start.
    if (!playing && week >= horizon) setWeek(1)
    setPlaying((p) => !p)
  }

  if (error) return <p className="load-error">{error}</p>
  if (!snapshot) return <p className="loading">Loading the branch</p>

  return (
    <div className="app">
      <header className="app-header">
        <h1>KendraPulse</h1>
        <span className="branch">Davanagere branch</span>
        <span className="private-tag">Visible to the loan officer only</span>
      </header>

      <main className="graph-pane">
        <GraphView snapshot={snapshot} week={week} selectedId={selectedId} onSelect={setSelectedId} />
      </main>

      <aside className="side-panel" />

      <footer className="slider-bar">
        <WeekSlider week={week} weeks={horizon} playing={playing} onWeek={setWeek} onTogglePlay={togglePlay} />
      </footer>
    </div>
  )
}
