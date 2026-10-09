import { DEMO_READ_ONLY, demoRequest, isDemoCase, setDemoMode, sortQueue } from './lib/demo.ts'

export type Tier ='critical' | 'high' | 'routine'
export type Status = 'queued' | 'analyzing' | 'ready' | 'reviewed' | 'failed' | 'retake'

export interface Region {
  id: number
  x0: number
  y0: number
  x1: number
  y1: number
  area_fraction: number
  max_prob: number
  mean_prob: number
  /** Missing on cases analysed before hotspots existed. */
  hotspot_x?: number
  hotspot_y?: number
}

export interface Landmark {
  cls: string
  x: number
  y: number
  prob: number
}

export interface AnalysisResult {
  width: number
  height: number
  urgency: number
  tier: Tier
  tumor_fraction: number
  lesion_fraction: number
  max_tumor_prob: number
  largest_region_fraction: number
  necrosis_fraction: number
  tissue_fraction: number
  composition: Record<string, number>
  regions: Region[]
  landmarks?: Landmark[]
  tiles: number
  device: string
  elapsed_ms: number
  model?: string
  model_label?: string
  organ?: string
  /** Class code -> display label for the model that produced this result (absent on old results). */
  class_labels?: Record<string, string>
  tumor_classes?: string[]
  /** Present when several photos were stitched into one mosaic. */
  fields?: { uploaded: number; stitched: number; downscale: number } | null
  cells?: CellSummary | null
}

export type QualityStatus = 'pass' | 'warn' | 'reject'

export interface QualityCheck {
  name: string
  label: string
  status: QualityStatus
  value: number
  message: string
}

/** Pre-analysis photo quality gate (quality.json). */
export interface QualityReport {
  status: QualityStatus
  checks: QualityCheck[]
  /** Stitched cases: photos left out before stitching. */
  dropped: { photo: number; reason: string }[]
  forced: boolean
}

export type NucleusType = 'neoplastic' | 'inflammatory' | 'connective' | 'dead' | 'epithelial'

export type CellSummary =
  | { status: 'counting' }
  | { status: 'failed'; error: string }
  | {
      status: 'done'
      total: number
      counts: Record<NucleusType, number>
      fractions: Record<NucleusType, number>
      per_mm2: number
      tissue_mm2: number
      elapsed_ms: number
    }

/** nuclei.json: [x, y, type] in display-image pixels; type 1-5 in NUCLEUS_TYPES order. */
export interface NucleiFile {
  points: [number, number, number][]
}

interface CaseBase {
  id: number
  patient_ref: string
  clinic: string
  specimen: string
  status: Status
  urgency: number | null
  tier: Tier | null
  created_at: string
  analyzed_at: string | null
  reviewed_at: string | null
  diagnosis: string
  notes: string
  error: string
  original_url: string
  /** Every uploaded photo when the case was stitched from several. */
  field_urls: string[]
  quality: QualityReport | null
  image_url?: string
  heatmap_url?: string
  tissue_map_url?: string
  nuclei_url?: string
}

export interface CaseSummary extends CaseBase {
  regions_count: number
  tumor_fraction: number | null
}

export interface CaseDetail extends CaseBase {
  result: AnalysisResult | null
}

export interface Health {
  device: string
  model: string
  model_label: string
  model_ready: boolean
  model_error: string
  classes: Record<string, string>
}

export interface ModelInfo {
  id: string
  label: string
  organ: string
  family: 'cnn' | 'foundation'
  description: string
  license: string
  params: string
  speed: 'fast' | 'medium' | 'slow'
  download_gb: number
  trained_on: string
  classes: Record<string, string>
  tumor_classes: string[]
  validation: { val_accuracy?: number; val_accuracy_degraded?: number }
  available: boolean
  unavailable_reason: string
  weights_cached: boolean
}

export interface ModelStatus {
  active: string
  /** Model currently in memory; differs from `active` while a switch is loading. */
  loaded: string
  loading: string
  error: string
  models: ModelInfo[]
}

/**
 * Backend origin, e.g. https://clinic-pc.tailnet.ts.net, when the dashboard is hosted apart from the
 * backend (Vercel). Empty in development, where Vite proxies /api and /media to localhost.
 */
const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '')

/** The hosted dashboard talks to a backend on the viewer's own computer (http://localhost:8000). */
export const USES_LOCAL_BACKEND = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(API_BASE)

/** The backend returns /media/... paths; point them at the backend origin too. */
const absoluteMedia = (_key: string, value: unknown) =>
  typeof value === 'string' && value.startsWith('/media/') ? API_BASE + value : value

/** `?demo` in the address forces the built-in demo, e.g. to rehearse a presentation with a backend running. */
export const FORCE_DEMO = new URLSearchParams(location.search).has('demo')

/**
 * Is the viewer's backend running? Checked once per visit, with a timeout so a pending
 * local-network permission prompt doesn't leave the page loading. Without it, the hosted
 * dashboard shows the built-in demo.
 */
const probe = () =>
  fetch(API_BASE + '/api/health', { signal: AbortSignal.timeout(5000) }).then(
    (r) => r.ok,
    () => false,
  )
const backendUp: Promise<boolean> = FORCE_DEMO ? Promise.resolve(false) : USES_LOCAL_BACKEND ? probe() : Promise.resolve(true)
backendUp.then((up) => setDemoMode(!up))

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  if (!(await backendUp)) {
    // Switch to the live backend as soon as it is started (the header polls health).
    if (url === '/api/health' && !FORCE_DEMO && (await probe())) location.reload()
    return demoRequest(url, init) as Promise<T>
  }
  const res = await fetch(API_BASE + url, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`)
  }
  return JSON.parse(await res.text(), absoluteMedia)
}

export const api = {
  health: () => request<Health>('/api/health'),
  /** The backend's queue with the demo cases mixed in (only the demo cases when no backend runs). */
  listCases: async (status = 'active') => {
    const url = `/api/cases?status=${status}`
    const demo = demoRequest(url) as Promise<CaseSummary[]>
    if (!(await backendUp)) return demo
    const [live, demoCases] = await Promise.all([request<CaseSummary[]>(url), demo.catch(() => [])])
    return sortQueue([...live, ...demoCases])
  },
  getCase: (id: number | string) =>
    isDemoCase(id) ? (demoRequest(`/api/cases/${id}`) as Promise<CaseDetail>) : request<CaseDetail>(`/api/cases/${id}`),
  createCase: (form: FormData) => request<CaseDetail>('/api/cases', { method: 'POST', body: form }),
  reviewCase: (id: number, body: { status?: Status; diagnosis?: string; notes?: string }) => {
    const init = { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    return isDemoCase(id)
      ? (demoRequest(`/api/cases/${id}`, init) as Promise<CaseDetail>)
      : request<CaseDetail>(`/api/cases/${id}`, init)
  },
  models: () => request<ModelStatus>('/api/models'),
  setModel: (id: string) =>
    request<ModelStatus>('/api/models/active', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    }),
  reanalyze: (id: number, force = false) =>
    isDemoCase(id)
      ? Promise.reject(new Error(DEMO_READ_ONLY))
      : request<CaseDetail>(`/api/cases/${id}/reanalyze${force ? '?force=true' : ''}`, { method: 'POST' }),
}
