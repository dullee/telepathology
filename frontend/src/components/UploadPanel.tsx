import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react'

import { api } from '../api.ts'

const MAX_PHOTOS = 40

export function UploadPanel({ onUploaded }: { onUploaded: () => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [patient, setPatient] = useState('')
  const [clinic, setClinic] = useState(() => {
    try {
      return localStorage.getItem('clinic') ?? ''
    } catch {
      return ''
    }
  })
  const [specimen, setSpecimen] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews])

  /** Photos accumulate, so a phone user can capture one field at a time. */
  function add(list: FileList | null | undefined) {
    const picked = [...(list ?? [])].filter((f) => f.type.startsWith('image/'))
    if (!picked.length) return
    const next = [...files, ...picked].slice(0, MAX_PHOTOS)
    setFiles(next)
    setPreviews(next.map((f) => URL.createObjectURL(f)))
    setError(files.length + picked.length > MAX_PHOTOS ? `Up to ${MAX_PHOTOS} photos per case.` : '')
  }

  function remove(i: number) {
    const next = files.filter((_, j) => j !== i)
    setFiles(next)
    setPreviews(next.map((f) => URL.createObjectURL(f)))
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    add(e.dataTransfer.files)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!files.length || !patient.trim()) return
    setBusy(true)
    setError('')
    const form = new FormData()
    if (files.length === 1) form.append('image', files[0])
    else files.forEach((f) => form.append('images', f))
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
      setFiles([])
      setPreviews([])
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
        className={`relative flex cursor-pointer items-center justify-center overflow-hidden rounded-lg border-2 border-dashed text-center text-sm transition ${
          files.length ? 'py-3' : 'aspect-[4/3]'
        } ${
          dragging
            ? 'border-cyan-600 bg-cyan-50 dark:bg-cyan-950/30'
            : 'border-slate-300 hover:border-cyan-600 dark:border-slate-700'
        }`}
      >
        {files.length === 1 ? (
          <img src={previews[0]} alt="Selected slide" className="max-h-56 rounded object-contain" />
        ) : files.length > 1 ? (
          <span className="px-4 font-medium text-slate-700 dark:text-slate-200">+ Add more photos</span>
        ) : (
          <div className="px-4 text-slate-500">
            <div className="font-medium text-slate-700 dark:text-slate-200">Drop slide photos here</div>
            <div className="mt-1 text-xs">or tap to choose · JPEG, PNG, TIFF · up to 40 MB each</div>
            <div className="mt-2 text-xs">
              One photo, or several overlapping photos of the same slide (about ⅓ overlap) to stitch into one image.
            </div>
          </div>
        )}
        <input
          ref={input}
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          className="hidden"
          onChange={(e) => {
            add(e.target.files)
            e.target.value = '' // allow picking the same file again
          }}
        />
      </div>

      {files.length > 1 && (
        <div>
          <div className="mb-1.5 flex items-center justify-between text-xs text-slate-500">
            <span>{files.length} photos · will be stitched into one image</span>
            <button
              type="button"
              onClick={() => {
                setFiles([])
                setPreviews([])
              }}
              className="hover:text-red-600"
            >
              Clear
            </button>
          </div>
          <ul className="grid grid-cols-4 gap-1.5 sm:grid-cols-5">
            {previews.map((src, i) => (
              <li key={src} className="group relative aspect-square overflow-hidden rounded bg-slate-900">
                <img src={src} alt={`Photo ${i + 1}`} className="size-full object-cover" />
                <button
                  type="button"
                  onClick={() => remove(i)}
                  aria-label={`Remove photo ${i + 1}`}
                  className="absolute right-0.5 top-0.5 flex size-5 items-center justify-center rounded-full bg-black/70 text-xs text-white opacity-80 hover:opacity-100"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <input className={field} placeholder="Patient / specimen ID *" value={patient} onChange={(e) => setPatient(e.target.value)} required />
      <input className={field} placeholder="Clinic" value={clinic} onChange={(e) => setClinic(e.target.value)} />
      <input className={field} placeholder="Specimen type (e.g. colon biopsy)" value={specimen} onChange={(e) => setSpecimen(e.target.value)} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={!files.length || !patient.trim() || busy}
        className="w-full rounded-md bg-cyan-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-cyan-800 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? 'Uploading…' : files.length > 1 ? `Stitch ${files.length} photos & submit` : 'Submit for AI triage'}
      </button>
    </form>
  )
}
