import L, { type LatLngBoundsExpression } from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { ImageOverlay, MapContainer, Rectangle, Tooltip, useMap } from 'react-leaflet'

import type { Region } from '../api.ts'
import { pct } from '../lib/format.ts'

interface Props {
  imageUrl: string
  heatmapUrl?: string
  width: number
  height: number
  regions: Region[]
  focus: Region | null
  onSelect: (r: Region) => void
}

/** Image pixel box (origin top-left) → Leaflet CRS.Simple bounds (origin bottom-left). */
function toBounds(r: Region, h: number): LatLngBoundsExpression {
  return [
    [h - r.y1, r.x0],
    [h - r.y0, r.x1],
  ]
}

function Fit({ bounds, focus, h }: { bounds: L.LatLngBounds; focus: Region | null; h: number }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds(bounds)
    map.setMinZoom(map.getBoundsZoom(bounds) - 1)
    map.setMaxBounds(bounds.pad(0.5))
  }, [map, bounds])
  useEffect(() => {
    if (focus) map.flyToBounds(toBounds(focus, h), { padding: [40, 40], duration: 0.6, maxZoom: 1.5 })
  }, [map, focus, h])
  return null
}

export function SlideViewer({ imageUrl, heatmapUrl, width, height, regions, focus, onSelect }: Props) {
  const [showHeat, setShowHeat] = useState(true)
  const [opacity, setOpacity] = useState(0.55)
  const [showRegions, setShowRegions] = useState(true)
  const bounds = useMemo(() => L.latLngBounds([0, 0], [height, width]), [width, height])

  return (
    <div className="relative size-full">
      <MapContainer
        crs={L.CRS.Simple}
        bounds={bounds}
        maxZoom={3}
        zoomSnap={0.25}
        zoomDelta={0.5}
        wheelPxPerZoomLevel={90}
        attributionControl={false}
        className="size-full"
      >
        <Fit bounds={bounds} focus={focus} h={height} />
        <ImageOverlay url={imageUrl} bounds={bounds} />
        {heatmapUrl && showHeat && <ImageOverlay url={heatmapUrl} bounds={bounds} opacity={opacity} zIndex={2} />}
        {showRegions &&
          regions.map((r) => (
            <Rectangle
              key={r.id}
              bounds={toBounds(r, height)}
              eventHandlers={{ click: () => onSelect(r) }}
              pathOptions={{
                color: focus?.id === r.id ? '#ffffff' : '#22d3ee',
                weight: focus?.id === r.id ? 3 : 2,
                dashArray: focus?.id === r.id ? undefined : '6 4',
                fillOpacity: 0,
              }}
            >
              <Tooltip direction="top" sticky>
                <strong>Region {r.id}</strong> · peak {pct(r.max_prob)} · {pct(r.area_fraction, 1)} of tissue
              </Tooltip>
            </Rectangle>
          ))}
      </MapContainer>

      <div className="absolute right-3 top-3 z-[500] w-56 space-y-2 rounded-lg bg-slate-900/85 p-3 text-xs text-slate-100 shadow-lg backdrop-blur">
        <label className="flex cursor-pointer items-center justify-between gap-2">
          <span className="font-medium">AI tumor heatmap</span>
          <input type="checkbox" checked={showHeat} onChange={(e) => setShowHeat(e.target.checked)} className="accent-cyan-500" />
        </label>
        <input
          type="range"
          min={0.1}
          max={0.9}
          step={0.05}
          value={opacity}
          disabled={!showHeat}
          onChange={(e) => setOpacity(Number(e.target.value))}
          aria-label="Heatmap opacity"
          className="w-full accent-cyan-500 disabled:opacity-40"
        />
        <div className="flex items-center gap-2" aria-hidden>
          <span className="text-slate-400">Low</span>
          <span className="h-2 flex-1 rounded-full bg-gradient-to-r from-yellow-300/40 via-orange-500 to-red-600" />
          <span className="text-slate-400">High</span>
        </div>
        <label className="flex cursor-pointer items-center justify-between gap-2 border-t border-white/10 pt-2">
          <span>Suspicious regions ({regions.length})</span>
          <input type="checkbox" checked={showRegions} onChange={(e) => setShowRegions(e.target.checked)} className="accent-cyan-500" />
        </label>
      </div>
    </div>
  )
}
