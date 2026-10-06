// Extrae de motor.js las sugerencias de materiales por parte de la
// composición (lo típico por categoría y estilo, y lo que nombra el producto)
// como opciones de los atributos comp.* (datos del motor del servidor).
// Uso: node scripts/motor-sugerencias.mjs > /ruta/sugerencias.json
import * as M from '../src/clasificacion/motor.js'

const PARTES = Object.keys(M.PARTE_LBL)
const cats = Object.keys(M.TIPO_LBL).filter((k) => k !== M.GENERICO)
const ESTILOS = (M.ATTR_BY.estiloCalz?.ops || []).map((o) => o.v)
const salida = {}
for (const p of PARTES) {
  const grupos = new Map() // lista -> contextos
  for (const c of cats) {
    const ests = c === 'calzado' ? [...ESTILOS, ''] : [null]
    for (const e of ests) {
      const lista = M.tipicosDe(p, { tipo: c, estiloCalz: e || '' })
      if (!lista?.length) continue
      const k = JSON.stringify(lista)
      grupos.set(k, [...(grupos.get(k) || []), [c, e]])
    }
  }
  const rel = M.SUG_DESC.filter(([, , partes]) => partes.includes(p)).map(([re, lbl]) => ({ re: re.source, material: lbl }))
  salida[p] = { grupos: [...grupos].map(([k, ctx]) => ({ lista: JSON.parse(k), contextos: ctx })), rel }
}
process.stdout.write(JSON.stringify(salida))
