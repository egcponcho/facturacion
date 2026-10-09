import { tx } from '@/i18n/index.js'
import { valor, valores } from './listas.js'

// Unidades de medida de los artículos: la lista «unidad» de la empresa
// (Datos maestros → Listas de valores). La caja de prepack (CJ) es la única
// que no es la unidad de un artículo sólido.
const PREPACK = 'CJ'
export const codigosUnidad = () => valores('unidad').map((u) => u.codigo)
export const unidadesArticulo = () => codigosUnidad().filter((k) => k !== PREPACK)
export const nombresUnidad = (k) => {
  const u = valor('unidad', k)
  return u ? [tx(u.nombre), tx(u.nombre_plural || u.nombre)] : [k, k]
}
export const etiquetaUnidad = (k) => `${nombresUnidad(k)[1].replace(/^./, (c) => c.toUpperCase())} (${k})`

// Lo que se cuenta va en enteros (o en inner packs enteros); lo que se mide admite 3 decimales
const contable = (unidad) => valor('unidad', unidad || 'UN')?.contable ?? true
export const pasoCantidad = (unidad, inner = null) => (contable(unidad) ? (inner || 1) : 0.001)
