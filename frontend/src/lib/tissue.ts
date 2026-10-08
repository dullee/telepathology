/**
 * Tissue classes the model reports, with plain-language viewing notes so someone who is not a
 * pathologist knows what each marked spot should look like in an H&E photo.
 * Colours must match TISSUE_COLORS in backend/app/config.py (they paint the tissue map).
 * TISSUE covers the colorectal (Kather) classes; ORGAN_TISSUE below adds stomach, liver and lung.
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

/**
 * Organ-specific notes for the organ models (see backend/app/inference/registry.py). Entries here win
 * over the colorectal TISSUE notes. Class codes keep one colour across organs (TUM/ACA red, NOR green…).
 * "TUM" is also used for tumor-region stops in organs whose model has several tumor classes (lung).
 */
export const ORGAN_TISSUE: Record<string, Record<string, TissueInfo>> = {
  Stomach: {
    TUM: {
      label: 'Gastric adenocarcinoma',
      color: '#dc2626',
      what: 'Cancer of the stomach lining. It grows either as abnormal glands or as scattered single cells.',
      lookFor: [
        'Irregular, crowded or fused glands with enlarged, dark, uneven nuclei',
        'Single loose cells infiltrating between normal glands; "signet-ring" cells have a clear mucin bubble pushing the nucleus to one side',
        'Tumor reaching below the mucosa into stroma or muscle',
      ],
    },
    NOR: {
      label: 'Normal gastric mucosa',
      color: '#10b981',
      what: 'Healthy stomach lining. Use it as your comparison for what "normal" looks like.',
      lookFor: [
        'Regular surface pits lined by tall cells filled with pale mucin',
        'Evenly spaced glands below; in the body of the stomach, pink and purple gland cells side by side',
        'Small, round nuclei sitting neatly at the base of each cell',
      ],
    },
    DEB: {
      label: 'Debris / necrosis',
      color: '#f97316',
      what: 'Dead tissue, often in the centre of a tumor or at an ulcer surface.',
      lookFor: ['Smudgy pink-purple material with no clear cell outlines', 'Scattered dark fragments of broken nuclei'],
    },
  },
  Liver: {
    TUM: {
      label: 'Hepatocellular carcinoma',
      color: '#dc2626',
      what: 'Cancer of the liver cells themselves (HCC). It replaces the normal plate-and-sinusoid pattern.',
      lookFor: [
        'Liver cells in thick cords (more than 3 cells across) or solid sheets instead of thin plates',
        'Enlarged nuclei with prominent nucleoli and a high nucleus-to-cytoplasm ratio',
        'No portal tracts within the nodule; sometimes small gland-like (pseudoglandular) spaces',
      ],
    },
    NOR: {
      label: 'Normal liver',
      color: '#10b981',
      what: 'Healthy liver. Use it as your comparison for what "normal" looks like.',
      lookFor: [
        'Thin plates of liver cells, 1–2 cells thick, separated by narrow sinusoid channels',
        'Polygonal cells with pink cytoplasm and one round, central nucleus',
        'Portal tracts: a bile duct, artery and vein together in a small pocket of connective tissue',
      ],
    },
    FIB: {
      label: 'Fibrosis',
      color: '#f472b6',
      what: 'Scar tissue. Bands that connect portal tracts and encircle nodules indicate cirrhosis, a soil for HCC.',
      lookFor: ['Pink bands of collagen with few, thin nuclei', 'Bands bridging between portal tracts or wrapping around round nodules'],
    },
    INF: {
      label: 'Inflammation',
      color: '#6366f1',
      what: 'Immune cells, as in hepatitis.',
      lookFor: [
        'Clusters of small, round, very dark nuclei',
        'Usually in portal tracts, sometimes spilling into the surrounding liver cells',
      ],
    },
    NEC: {
      label: 'Necrosis',
      color: '#f97316',
      what: 'Dead tissue, common in the centre of larger tumors.',
      lookFor: ['Pale pink areas where cells have lost their nuclei ("ghost" cell outlines)', 'Granular debris and nuclear fragments'],
    },
    REA: {
      label: 'Bile duct reaction',
      color: '#14b8a6',
      what: 'Proliferating small bile ducts, a response to chronic liver injury.',
      lookFor: ['Small, irregular duct-like tubes of cuboidal cells', 'At the edges of portal tracts and fibrous bands, often with inflammation'],
    },
    STE: {
      label: 'Steatosis',
      color: '#facc15',
      what: 'Fat inside liver cells (fatty liver). Common, and usually not cancer by itself.',
      lookFor: ['Round, clear, empty-looking vacuoles inside liver cells', 'Large vacuoles push the nucleus to the edge of the cell'],
    },
  },
  Lung: {
    TUM: {
      label: 'Lung carcinoma',
      color: '#dc2626',
      what: 'Cancer replacing normal lung. The model splits it into adenocarcinoma and squamous cell carcinoma.',
      lookFor: [
        'Crowded cells with enlarged, dark, irregular nuclei and visible nucleoli',
        'Air spaces filled or replaced by solid groups of cells',
        'Dense fibrous stroma around tumor nests or glands',
      ],
    },
    ACA: {
      label: 'Adenocarcinoma',
      color: '#dc2626',
      what: 'Gland-forming lung cancer, the most common type.',
      lookFor: [
        'Glands, papillae, or tumor cells lining the alveolar walls',
        'Sometimes pale mucin inside the cells or glands',
        'Nuclei often large and pale with a prominent nucleolus',
      ],
    },
    SCC: {
      label: 'Squamous cell carcinoma',
      color: '#a21caf',
      what: 'Lung cancer resembling skin-type (squamous) cells; strongly linked to smoking.',
      lookFor: [
        'Nests and sheets of cells with plenty of glassy pink cytoplasm',
        'Keratin pearls: concentric pink whorls in the middle of nests',
        'Necrosis in the centre of nests',
      ],
    },
    NOR: {
      label: 'Normal lung',
      color: '#10b981',
      what: 'Healthy lung. Use it as your comparison for what "normal" looks like.',
      lookFor: [
        'A lacy network of open air spaces (alveoli) with thin pink walls',
        'Few, small, flat nuclei in the walls',
        'Airways lined by a single orderly row of tall cells',
      ],
    },
  },
}

export const tissueInfo = (cls: string, organ?: string): TissueInfo =>
  (organ && ORGAN_TISSUE[organ]?.[cls]) || TISSUE[cls] || { label: cls, color: '#94a3b8', what: '', lookFor: [] }
