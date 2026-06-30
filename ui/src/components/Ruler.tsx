import type { TickPosition } from '../hooks/useTimelineLayout'

interface RulerProps {
  ticks: TickPosition[]
  maxTick: number
  /** Pixels from the scroll container's left edge to where this SVG starts.
   *  Tick x-values are in scroll-container coordinates; subtracting this gives
   *  the position within the ruler's own SVG coordinate space. */
  leftMargin: number
}

export function Ruler({ ticks, maxTick, leftMargin }: RulerProps) {
  // Show a label every 5 ticks (or every tick if max_tick is small).
  const labelStep = maxTick <= 10 ? 1 : 5

  return (
    <svg className="absolute top-0 left-0 w-full h-full pointer-events-none">
      {ticks.map((t) => {
        const isMajor = t.isCycleStart
        // Convert from scroll-container space to this SVG's local space.
        const svgX = t.x - leftMargin
        const bottomY = 43
        // Major ticks are taller (more visible).
        const tickTop = isMajor ? 14 : 30
        // Minor labels sit just above their tick mark; major labels stay near the top.
        const labelY = isMajor ? 11 : 27
        const showTickLabel = !isMajor && t.tick % labelStep === 0
        const labelText = isMajor ? t.cycle.toString() : t.tick.toString()

        return (
          <g key={`${t.cycle}-${t.tick}`}>
            <line
              x1={svgX}
              y1={tickTop}
              x2={svgX}
              y2={bottomY}
              stroke={isMajor ? '#7A8490' : '#59616A'}
              strokeWidth={isMajor ? 1.5 : 1}
            />
            {(isMajor || showTickLabel) && (
              <text
                x={svgX}
                y={labelY}
                fill={isMajor ? '#A0A8B0' : '#7F8790'}
                fontSize={isMajor ? 12 : 10}
                textAnchor="middle"
                fontFamily="Consolas, monospace"
              >
                {labelText}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
