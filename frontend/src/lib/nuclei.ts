import type { NucleusType } from '../api.ts'

/** HoVer-Net PanNuke nucleus types, in nuclei.json type order (type 1 = index 0). */
export const NUCLEUS_TYPES: { key: NucleusType; label: string; color: string; swatch: string }[] = [
  { key: 'neoplastic', label: 'Neoplastic', color: '#ef4444', swatch: 'bg-red-500' },
  { key: 'inflammatory', label: 'Inflammatory', color: '#22c55e', swatch: 'bg-green-500' },
  { key: 'connective', label: 'Connective', color: '#22d3ee', swatch: 'bg-cyan-400' },
  { key: 'dead', label: 'Dead', color: '#a8a29e', swatch: 'bg-stone-400' },
  { key: 'epithelial', label: 'Benign epithelial', color: '#facc15', swatch: 'bg-yellow-400' },
]
