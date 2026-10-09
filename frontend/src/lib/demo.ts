import { useSyncExternalStore } from 'react'

import type { CaseDetail, CaseSummary, Health, ModelStatus } from '../api.ts'

/**
 * Built-in demo: saved results of real analyses (public/demo/, written by backend/scripts/export_demo.py).
 * The hosted dashboard answers from it when the viewer's computer runs no backend, so the triage
 * queue can be shown anywhere. Reviews are kept in memory for the visit; uploads need a backend.
 */

interface DemoData {
  health: Health
  models: ModelStatus
  cases: CaseDetail[]
}

export const DEMO_READ_ONLY = 'This is the built-in demo. Start the backend on this computer to upload or re-analyze.'

/** Same order as the backend's queue: analysed first, then by urgency, oldest first on ties. */
const STATUS_ORDER: Record<string, number> = { ready: 0, analyzing: 1, queued: 2, retake: 3, failed: 4, reviewed: 5 }

let active = false
const listeners = new Set<() => void>()

export function setDemoMode(on: boolean) {
  if (on === active) return
  active = on
  listeners.forEach((l) => l())
}

/** True while the dashboard shows the built-in demo instead of a live backend. */
export function useDemoMode() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => active,
  )
}

let data: Promise<DemoData> | null = null

function load(): Promise<DemoData> {
  data ??= fetch('/demo/data.json')
    .then((r) => {
      if (!r.ok) throw new Error('The demo cases are missing from this build.')
      return r.json() as Promise<DemoData>
    })
    .then((d) => {
      // Show the snapshot as this morning's queue: uploads a few minutes apart, newest first.
      const now = Date.now()
      const byAge = [...d.cases].sort((a, b) => b.created_at.localeCompare(a.created_at))
      byAge.forEach((c, i) => {
        const created = now - (4 + i * 11) * 60_000
        c.created_at = new Date(created).toISOString()
        if (c.analyzed_at) c.analyzed_at = new Date(created + 40_000).toISOString()
        if (c.reviewed_at) c.reviewed_at = new Date(created + 5 * 60_000).toISOString()
      })
      d.health = { ...d.health, device: 'demo results' }
      return d
    })
  return data
}

function summarize(c: CaseDetail): CaseSummary {
  const { result, ...rest } = c
  return { ...rest, regions_count: result?.regions.length ?? 0, tumor_fraction: result?.tumor_fraction ?? null }
}

/** Answers an API request (`/api/...` URL plus fetch options) from the demo snapshot. */
export async function demoRequest(url: string, init?: RequestInit): Promise<unknown> {
  const d = await load()
  const { pathname, searchParams } = new URL(url, location.origin)
  const method = init?.method ?? 'GET'
  const caseId = pathname.match(/^\/api\/cases\/(\d+)$/)?.[1]
  const find = (id: string) => {
    const c = d.cases.find((x) => x.id === Number(id))
    if (!c) throw new Error('Case not found')
    return c
  }

  if (method === 'GET' && pathname === '/api/health') return d.health
  if (method === 'GET' && pathname === '/api/models') return d.models
  if (method === 'GET' && pathname === '/api/cases') {
    const status = searchParams.get('status')
    return d.cases
      .filter((c) => (status === 'active' ? c.status !== 'reviewed' : !status || c.status === status))
      .sort(
        (a, b) =>
          (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) ||
          (b.urgency ?? -1) - (a.urgency ?? -1) ||
          a.created_at.localeCompare(b.created_at),
      )
      .map(summarize)
  }
  if (method === 'GET' && caseId) return find(caseId)
  if (method === 'PATCH' && caseId) {
    const c = find(caseId)
    const body = JSON.parse(String(init?.body ?? '{}')) as Partial<CaseDetail>
    if (body.diagnosis != null) c.diagnosis = body.diagnosis
    if (body.notes != null) c.notes = body.notes
    if (body.status != null) {
      c.status = body.status
      c.reviewed_at = body.status === 'reviewed' ? new Date().toISOString() : null
    }
    return c
  }
  throw new Error(DEMO_READ_ONLY)
}
