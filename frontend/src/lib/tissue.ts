/**
 * Display names and colours for the tissue classes the models report.
 * Colours must match TISSUE_COLORS in backend/app/config.py (they paint the tissue map).
 * TISSUE covers the colorectal (Kather) classes; ORGAN_TISSUE below adds stomach, liver and lung.
 */
export interface TissueInfo {
  label: string
  color: string
}

export const TISSUE: Record<string, TissueInfo> = {
  TUM: {
    label: 'Tumor epithelium',
    color: '#dc2626',
  },
  DEB: {
    label: 'Debris / necrosis',
    color: '#f97316',
  },
  NORM: {
    label: 'Normal mucosa',
    color: '#10b981',
  },
  LYM: {
    label: 'Lymphocytes',
    color: '#6366f1',
  },
  STR: {
    label: 'Stroma',
    color: '#f472b6',
  },
  MUS: {
    label: 'Smooth muscle',
    color: '#fda4af',
  },
  MUC: {
    label: 'Mucus',
    color: '#38bdf8',
  },
}

/**
 * Organ-specific names for the organ models (see backend/app/inference/registry.py). Entries here win
 * over the colorectal TISSUE names. Class codes keep one colour across organs (TUM/ACA red, NOR green…).
 */
export const ORGAN_TISSUE: Record<string, Record<string, TissueInfo>> = {
  Stomach: {
    TUM: {
      label: 'Gastric adenocarcinoma',
      color: '#dc2626',
    },
    NOR: {
      label: 'Normal gastric mucosa',
      color: '#10b981',
    },
    DEB: {
      label: 'Debris / necrosis',
      color: '#f97316',
    },
  },
  Liver: {
    TUM: {
      label: 'Hepatocellular carcinoma',
      color: '#dc2626',
    },
    NOR: {
      label: 'Normal liver',
      color: '#10b981',
    },
    FIB: {
      label: 'Fibrosis',
      color: '#f472b6',
    },
    INF: {
      label: 'Inflammation',
      color: '#6366f1',
    },
    NEC: {
      label: 'Necrosis',
      color: '#f97316',
    },
    REA: {
      label: 'Bile duct reaction',
      color: '#14b8a6',
    },
    STE: {
      label: 'Steatosis',
      color: '#facc15',
    },
  },
  Lung: {
    TUM: {
      label: 'Lung carcinoma',
      color: '#dc2626',
    },
    ACA: {
      label: 'Adenocarcinoma',
      color: '#dc2626',
    },
    SCC: {
      label: 'Squamous cell carcinoma',
      color: '#a21caf',
    },
    NOR: {
      label: 'Normal lung',
      color: '#10b981',
    },
  },
}

export const tissueInfo = (cls: string, organ?: string): TissueInfo =>
  (organ && ORGAN_TISSUE[organ]?.[cls]) || TISSUE[cls] || { label: cls, color: '#94a3b8' }
