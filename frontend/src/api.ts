export type Tier = 'critical' | 'high' | 'routine'
export type Status = 'queued' | 'analyzing' | 'ready' | 'reviewed' | 'failed'

export interface Region {
  id: number
  x0: number
  y0: number
  x1: number
  y1: number
  area_fraction: number
  max_prob: number
  mean_prob: number
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
  tiles: number
  device: string
  elapsed_ms: number
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
  image_url?: string
  heatmap_url?: string
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
  model_ready: boolean
  model_error: string
  classes: Record<string, string>
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  health: () => request<Health>('/api/health'),
  listCases: (status = 'active') => request<CaseSummary[]>(`/api/cases?status=${status}`),
  getCase: (id: number | string) => request<CaseDetail>(`/api/cases/${id}`),
  createCase: (form: FormData) => request<CaseDetail>('/api/cases', { method: 'POST', body: form }),
  reviewCase: (id: number, body: { status?: Status; diagnosis?: string; notes?: string }) =>
    request<CaseDetail>(`/api/cases/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  reanalyze: (id: number) => request<CaseDetail>(`/api/cases/${id}/reanalyze`, { method: 'POST' }),
}
