export default function WeekSlider({ week, weeks, playing, onWeek, onTogglePlay }) {
  return (
    <div className="week-slider">
      <button className="play" onClick={onTogglePlay} aria-label={playing ? 'Pause' : 'Play'}>
        {playing ? 'Pause' : 'Play'}
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
