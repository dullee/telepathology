import type { AnalysisResult, Region } from '../api.ts'
import { tissueInfo } from './tissue.ts'

/** One place on the slide the guided tour points at, in display-image pixels. */
export interface GuideStop {
  key: string
  cls: string
  x: number
  y: number
  prob: number
  title: string
  region?: Region
}

/** Suspicious regions first (most important), then one reference example per tissue type. */
export function buildStops(r: AnalysisResult): GuideStop[] {
  const regions: GuideStop[] = r.regions.map((reg) => ({
    key: `r${reg.id}`,
    cls: 'TUM',
    x: reg.hotspot_x ?? (reg.x0 + reg.x1) / 2,
    y: reg.hotspot_y ?? (reg.y0 + reg.y1) / 2,
    prob: reg.max_prob,
    title: `Suspicious region ${reg.id}`,
    region: reg,
  }))
  const examples: GuideStop[] = (r.landmarks ?? []).map((lm) => ({
    key: `l${lm.cls}`,
    cls: lm.cls,
    x: lm.x,
    y: lm.y,
    prob: lm.prob,
    title: `Example: ${tissueInfo(lm.cls).label}`,
  }))
  return [...regions, ...examples]
}
