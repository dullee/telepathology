import L, { type LatLngBoundsExpression, type LatLngExpression } from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { Circle, ImageOverlay, MapContainer, Marker, Rectangle, Tooltip, useMap } from 'react-leaflet'

import type { NucleiFile, Region } from '../api.ts'
import { pct } from '../lib/format.ts'
import type { GuideStop } from '../lib/guide.ts'
import { NUCLEUS_TYPES } from '../lib/nuclei.ts'
import { tissueInfo } from '../lib/tissue.ts'

type Overlay = 'heat' | 'tissue' | 'none'

interface Props {
  imageUrl: string
  heatmapUrl?: string
  tissueMapUrl?: string
  width: number
  height: number
  stops: GuideStop[]
  focus: GuideStop | null
  onSelect: (s: GuideStop) => void
  /** Tissue classes of the model that produced the result, for the tissue-map legend. */
  classes: string[]
  organ?: string
  nucleiUrl?: string
  nucleiCount?: number
}

/** Image pixel box (origin top-left) → Leaflet CRS.Simple bounds (origin bottom-left). */
function toBounds(r: Region, h: number): LatLngBoundsExpression {
  return [
    [h - r.y1, r.x0],
    [h - r.y0, r.x1],
  ]
}

const toLatLng = (s: GuideStop, h: number): LatLngExpression => [h - s.y, s.x]

/** Radius of the "look here" circle: about one model tile, the area the AI judged. */
const LOOK_RADIUS = 112

function pinIcon(stop: GuideStop, focused: boolean, organ?: string) {
  const color = tissueInfo(stop.cls, organ).color
  const label = stop.region ? String(stop.region.id) : ''
  return L.divIcon({
    className: '',
    html: `<span class="guide-pin${stop.region ? '' : ' guide-pin--example'}${focused ? ' guide-pin--focus' : ''}" style="--pin:${color}">${label}</span>`,
    iconSize: [0, 0],
  })
}

function Fit({ bounds, focus, h }: { bounds: L.LatLngBounds; focus: GuideStop | null; h: number }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds(bounds)
    map.setMinZoom(map.getBoundsZoom(bounds) - 1)
    map.setMaxBounds(bounds.pad(0.5))
  }, [map, bounds])
  useEffect(() => {
    if (focus) map.flyTo(toLatLng(focus, h), Math.max(map.getZoom(), 1.25), { duration: 0.6 })
  }, [map, focus, h])
  return null
}

/** One dot per detected nucleus, drawn on a shared canvas so tens of thousands stay smooth. */
function NucleiLayer({ url, h }: { url: string; h: number }) {
  const map = useMap()
  useEffect(() => {
    const renderer = L.canvas({ padding: 0.2 })
    const group = L.layerGroup().addTo(map)
    let cancelled = false
    fetch(url)
      .then((r) => r.json() as Promise<NucleiFile>)
      .then(({ points }) => {
        if (cancelled) return
        for (const [x, y, t] of points) {
          const color = NUCLEUS_TYPES[t - 1]?.color ?? '#ffffff'
          L.circleMarker([h - y, x], { renderer, radius: 3, weight: 1.5, color, fillOpacity: 0, interactive: false }).addTo(group)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
      group.remove()
    }
  }, [map, url, h])
  return null
}

export function SlideViewer({
  imageUrl,
  heatmapUrl,
  tissueMapUrl,
  width,
  height,
  stops,
  focus,
  onSelect,
  classes,
  organ,
  nucleiUrl,
  nucleiCount,
}: Props) {
  const [overlay, setOverlay] = useState<Overlay>('heat')
  const [showCells, setShowCells] = useState(false)
  const [opacity, setOpacity] = useState(0.55)
  const [showPins, setShowPins] = useState(true)
  const bounds = useMemo(() => L.latLngBounds([0, 0], [height, width]), [width, height])
  const overlayUrl = overlay === 'heat' ? heatmapUrl : overlay === 'tissue' ? tissueMapUrl : undefined
  const options: [Overlay, string, boolean][] = [
    ['heat', 'Tumor heatmap', !!heatmapUrl],
    ['tissue', 'Tissue map', !!tissueMapUrl],
    ['none', 'Photo only', true],
  ]

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
        {overlayUrl && <ImageOverlay key={overlay} url={overlayUrl} bounds={bounds} opacity={opacity} zIndex={2} />}
        {nucleiUrl && showCells && <NucleiLayer url={nucleiUrl} h={height} />}
        {showPins &&
          stops.map((s) =>
            s.region ? (
              <Rectangle
                key={`box-${s.key}`}
                bounds={toBounds(s.region, height)}
                eventHandlers={{ click: () => onSelect(s) }}
                pathOptions={{
                  color: focus?.key === s.key ? '#ffffff' : '#22d3ee',
                  weight: focus?.key === s.key ? 3 : 2,
                  dashArray: focus?.key === s.key ? undefined : '6 4',
                  fillOpacity: 0,
                }}
              />
            ) : null,
          )}
        {focus && (
          <Circle
            center={toLatLng(focus, height)}
            radius={LOOK_RADIUS}
            interactive={false}
            pathOptions={{ color: '#ffffff', weight: 2, dashArray: '4 4', fillOpacity: 0 }}
          />
        )}
        {showPins &&
          stops.map((s) => (
            <Marker
              key={s.key}
              position={toLatLng(s, height)}
              icon={pinIcon(s, focus?.key === s.key, organ)}
              eventHandlers={{ click: () => onSelect(s) }}
              zIndexOffset={s.region ? 100 : 0}
            >
              <Tooltip direction="top" offset={[0, -14]}>
                <strong>{s.title}</strong> · AI confidence {pct(s.prob)}
                {s.region && <> · {pct(s.region.area_fraction, 1)} of tissue</>}
              </Tooltip>
            </Marker>
          ))}
      </MapContainer>

      <div className="absolute right-3 top-3 z-[500] w-60 space-y-2 rounded-lg bg-slate-900/85 p-3 text-xs text-slate-100 shadow-lg backdrop-blur">
        <div className="grid grid-cols-3 gap-1 rounded-md bg-white/10 p-0.5" role="radiogroup" aria-label="Overlay">
          {options.map(([value, label, available]) => (
            <button
              key={value}
              role="radio"
              aria-checked={overlay === value}
              disabled={!available}
              title={available ? undefined : 'Re-analyze this case to generate the tissue map'}
              onClick={() => setOverlay(value)}
              className={`rounded px-1 py-1 leading-tight transition disabled:opacity-35 ${
                overlay === value ? 'bg-cyan-600 font-medium text-white' : 'hover:bg-white/10'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          type="range"
          min={0.1}
          max={0.9}
          step={0.05}
          value={opacity}
          disabled={overlay === 'none'}
          onChange={(e) => setOpacity(Number(e.target.value))}
          aria-label="Overlay opacity"
          className="w-full accent-cyan-500 disabled:opacity-40"
        />
        {overlay === 'heat' && (
          <div className="flex items-center gap-2" aria-hidden>
            <span className="text-slate-400">Low</span>
            <span className="h-2 flex-1 rounded-full bg-gradient-to-r from-yellow-300/40 via-orange-500 to-red-600" />
            <span className="text-slate-400">High</span>
          </div>
        )}
        {overlay === 'tissue' && (
          <ul className="grid grid-cols-2 gap-x-2 gap-y-0.5">
            {classes.map((k) => {
              const t = tissueInfo(k, organ)
              return (
                <li key={k} className="flex items-center gap-1.5 truncate" title={t.label}>
                  <span className="size-2 shrink-0 rounded-sm" style={{ backgroundColor: t.color }} />
                  {t.label}
                </li>
              )
            })}
          </ul>
        )}
        <label className="flex cursor-pointer items-center justify-between gap-2 border-t border-white/10 pt-2">
          <span>Guide markers ({stops.length})</span>
          <input type="checkbox" checked={showPins} onChange={(e) => setShowPins(e.target.checked)} className="accent-cyan-500" />
        </label>
        {nucleiUrl && (
          <div className="border-t border-white/10 pt-2">
            <label className="flex cursor-pointer items-center justify-between gap-2">
              <span>Cells{nucleiCount != null && ` (${nucleiCount.toLocaleString()})`}</span>
              <input type="checkbox" checked={showCells} onChange={(e) => setShowCells(e.target.checked)} className="accent-cyan-500" />
            </label>
            {showCells && (
              <ul className="mt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[11px] text-slate-300">
                {NUCLEUS_TYPES.map((t) => (
                  <li key={t.key} className="flex items-center gap-1.5 truncate">
                    <span className="size-2 shrink-0 rounded-full border-2" style={{ borderColor: t.color }} />
                    {t.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
