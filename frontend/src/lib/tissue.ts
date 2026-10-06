/**
 * Tissue classes the model reports, with plain-language viewing notes so someone who is not a
 * pathologist knows what each marked spot should look like in an H&E photo.
 * Colours must match TISSUE_COLORS in backend/app/config.py (they paint the tissue map).
 */
export interface TissueInfo {
  label: string
  color: string
  /** One sentence: what this tissue is. */
  what: string
  /** Visual clues to check at the marked spot. */
  lookFor: string[]
}

export const TISSUE: Record<string, TissueInfo> = {
  TUM: {
    label: 'Tumor epithelium',
    color: '#dc2626',
    what: 'Cancer cells forming abnormal glands. In the colon this pattern means adenocarcinoma.',
    lookFor: [
      'Crowded, enlarged, dark purple nuclei, often elongated and stacked several layers deep instead of one neat row',
      'Glands that are irregular, branching or fused back-to-back, with little pink tissue between them',
      'Few or no goblet cells (the pale, empty-looking mucin bubbles seen in normal lining)',
      'Glands sitting where they do not belong, pushing into stroma or muscle (invasion)',
    ],
  },
  DEB: {
    label: 'Debris / necrosis',
    color: '#f97316',
    what: 'Dead tissue. "Dirty necrosis" inside glands is a classic clue to colorectal cancer.',
    lookFor: [
      'Granular, smudgy pink-purple material with no clear cell outlines',
      'Scattered dark specks: broken-up nuclei from dying cells',
      'Often fills the centre of tumor glands, ringed by viable tumor cells',
    ],
  },
  NORM: {
    label: 'Normal mucosa',
    color: '#10b981',
    what: 'Healthy colon lining. Use it as your comparison for what "normal" looks like.',
    lookFor: [
      'Evenly spaced crypts: test tubes side by side when cut lengthwise, a honeycomb of rings when cut across',
      'A single tidy row of small nuclei pressed against the base of each cell',
      'Many goblet cells: pale, clear bubbles between the nuclei',
    ],
  },
  LYM: {
    label: 'Lymphocytes',
    color: '#6366f1',
    what: 'Immune cells. Dense clusters can sit at the edge of a tumor or in normal lymphoid tissue.',
    lookFor: [
      'Sheets of small, round, very dark blue dots with almost no pink around them',
      'Much smaller and more uniform than tumor nuclei',
    ],
  },
  STR: {
    label: 'Stroma',
    color: '#f472b6',
    what: 'Supporting connective tissue between glands. Tumors often provoke a dense stromal reaction.',
    lookFor: [
      'Pink, wavy or streaky fibres',
      'Only a few thin, spindle-shaped nuclei',
      'Tumor glands embedded in stroma (rather than mucosa) suggest invasion',
    ],
  },
  MUS: {
    label: 'Smooth muscle',
    color: '#fda4af',
    what: 'The muscle wall of the bowel. Tumor reaching it means deeper invasion.',
    lookFor: [
      'Dense, uniform pink bundles running in one direction',
      'Long cigar-shaped nuclei lined up with the fibres',
    ],
  },
  MUC: {
    label: 'Mucus',
    color: '#38bdf8',
    what: 'Mucin pools. Tumor cells floating in large lakes of mucin suggest a mucinous carcinoma.',
    lookFor: [
      'Pale grey-blue, wispy or stringy material with few cells',
      'Check the edges for clusters of tumor cells floating inside the pool',
    ],
  },
}

export const tissueInfo = (cls: string): TissueInfo =>
  TISSUE[cls] ?? { label: cls, color: '#94a3b8', what: '', lookFor: [] }
