import { useRef, useState, type DragEvent, type FormEvent } from 'react'

import { api } from '../api.ts'

export function UploadPanel({ onUploaded }: { onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [patient, setPatient] = useState('')
  const [clinic, setClinic] = useState(() => localStorage.getItem('clinic') ?? '')
  const [specimen, setSpecimen] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  function pick(f: File | undefined) {
    if (!f) return
    if (preview) URL.revokeObjectURL(preview)
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setError('')
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files[0])
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!file || !patient.trim()) return
    setBusy(true)
    setError('')
    const form = new FormData()
    form.append('image', file)
    form.append('patient_ref', patient)
    form.append('clinic', clinic)
    form.append('specimen', specimen)
    try {
      await api.createCase(form)
      try {
        localStorage.setItem('clinic', clinic)
      } catch {
        /* storage unavailable */
      }
      if (preview) URL.revokeObjectURL(preview)
      setFile(null)
      setPreview(null)
      setPatient('')
      setSpecimen('')
      onUploaded()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  const field =
    'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-cyan-600 focus:ring-2 focus:ring-cyan-600/20 dark:border-slate-700 dark:bg-slate-900'

  return (
    <form onSubmit={submit} className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`relative flex aspect-[4/3] cursor-pointer items-center justify-center overflow-hidden rounded-lg border-2 border-dashed text-center text-sm transition ${
          dragging
            ? 'border-cyan-600 bg-cyan-50 dark:bg-cyan-950/30'
            : 'border-slate-300 hover:border-cyan-600 dark:border-slate-700'
        }`}
      >
        {preview ? (
          <img src={preview} alt="Selected slide" className="absolute inset-0 size-full object-cover" />
        ) : (
          <div className="px-4 text-slate-500">
            <div className="font-medium text-slate-700 dark:text-slate-200">Drop a slide photo here</div>
            <div className="mt-1 text-xs">or tap to choose · JPEG, PNG, TIFF · up to 40 MB</div>
          </div>
        )}
        <input
          ref={input}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0])}
        />
      </div>
      <input className={field} placeholder="Patient / specimen ID *" value={patient} onChange={(e) => setPatient(e.target.value)} required />
      <input className={field} placeholder="Clinic" value={clinic} onChange={(e) => setClinic(e.target.value)} />
      <input className={field} placeholder="Specimen type (e.g. colon biopsy)" value={specimen} onChange={(e) => setSpecimen(e.target.value)} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={!file || !patient.trim() || busy}
        className="w-full rounded-md bg-cyan-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-cyan-800 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? 'Uploading…' : 'Submit for AI triage'}
      </button>
    </form>
  )
}
