// On the last week the button says Replay, because pressing it starts again from week 1.
export default function WeekSlider({ week, weeks, playing, onWeek, onTogglePlay }) {
  const label = playing ? 'Pause' : week >= weeks ? 'Replay' : 'Play'
  return (
    <div className="week-slider">
      <button className="play" onClick={onTogglePlay} aria-label={label}>
        {label}
      </button>
      <label className="week-readout" htmlFor="week-range">
        Week <strong>{week}</strong> of {weeks}
      </label>
      <input
        id="week-range"
        type="range"
        min={1}
        max={weeks}
        step={1}
        value={week}
        onChange={(ev) => onWeek(Number(ev.target.value))}
      />
    </div>
  )
}
