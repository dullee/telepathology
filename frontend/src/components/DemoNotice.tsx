import { FORCE_DEMO, USES_LOCAL_BACKEND } from '../api.ts'

/** Shown above the queue while the dashboard answers from the built-in demo. */
export function DemoNotice() {
  return (
    <div className="mb-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-200">
      <strong className="font-semibold">Demo cases.</strong> These are saved results from the triage engine: colon
      biopsy photos (single and stitched) and one photo the quality check sent back for a retake. Open any case to
      see the heatmap, tissue map and cell counts. You can review cases, but changes reset when the page reloads.
      {USES_LOCAL_BACKEND && !FORCE_DEMO && (
        <p className="mt-1">
          To analyze your own photos, start the backend on this computer with{' '}
          <code className="rounded bg-sky-100 px-1 dark:bg-sky-900/50">
            cd backend &amp;&amp; uv run uvicorn app.main:app --port 8000
          </code>
          . This page switches to it within 15 seconds.
        </p>
      )}
    </div>
  )
}
