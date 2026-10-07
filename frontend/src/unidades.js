import { t } from './i18n/index.js'

// Unidades de medida de los artículos: la misma lista que
// backend/app/services/unidades.py (una prueba verifica que coincidan).
// código → [singular, plural]
export const UNIDADES = {
  PAR: [t('pair'), t('pairs')],
  UN: [t('unit'), t('units')],
  DOC: [t('dozen'), t('dozens')],
  JGO: [t('set'), t('sets')],
  KG: ['kg', 'kg'],
  G: ['g', 'g'],
  L: [t('liter'), t('liters')],
  ML: ['ml', 'ml'],
  M: [t('meter'), t('meters')],
  M2: ['m²', 'm²'],
  M3: ['m³', 'm³'],
  ROL: [t('roll'), t('rolls')],
  CJ: [t('prepack carton'), t('prepack cartons')],
}
// Las de un artículo sólido (la caja de prepack solo existe para prepacks)
export const UNIDADES_ARTICULO = Object.keys(UNIDADES).filter((k) => k !== 'CJ')
export const etiquetaUnidad = (k) => `${(UNIDADES[k]?.[1] || k).replace(/^./, (c) => c.toUpperCase())} (${k})`
