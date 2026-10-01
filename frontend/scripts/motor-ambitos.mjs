// Exporta del motor del navegador en qué categorías aplica cada atributo
// (directamente o cuando otra respuesta lo activa) a
// backend/app/data/motor_ambitos.json, para sembrar AtributoAmbito con los
// mismos datos que usa la ficha. Uso: node scripts/motor-ambitos.mjs [salida.json]
import { writeFileSync } from 'node:fs'
import * as M from '../src/clasificacion/motor.js'

const aplica = (s) => new Set(M.ATTRS.filter((a) => a.aplica(s)).map((a) => a.id))
const estado = (base) => { const s = { comp: {}, ...base }; M.normalizar(s); return s }
const salida = {}
const anotar = (id, tipo, cond) => {
  const x = (salida[id] ||= {})
  const lista = (x[tipo] ||= [])
  if (!cond) { x[tipo] = [null]; return }
  if (lista[0] !== null && !lista.some((c) => JSON.stringify(c) === JSON.stringify(cond))) lista.push(cond)
}
for (const [, tipos] of M.TIPOS) {
  for (const [tipo] of tipos) {
    const s0 = estado({ tipo })
    const base = aplica(s0)
    base.forEach((id) => anotar(id, tipo, null))
    for (const id of base) {
      const a = M.ATTR_BY[id]
      const valores = a.tipo === 'check' ? [true] : (a.ops || []).map((o) => o.v)
      for (const v of valores) {
        for (const nuevo of aplica(estado({ ...s0, [id]: v }))) if (!base.has(nuevo)) anotar(nuevo, tipo, { [id]: v })
      }
    }
    // Atributos que se activan por la composición (p. ej. guante de cuero)
    for (const parte of M.partesDe(tipo, s0)) {
      for (const [clase, texto] of [['cuero', '100% leather'], ['textil', '100% cotton'], ['plastico', '100% polyurethane']]) {
        for (const nuevo of aplica(estado({ tipo, comp: { [parte]: texto } }))) if (!base.has(nuevo)) anotar(nuevo, tipo, { [`material.${parte}`]: clase })
      }
    }
  }
}
const ruta = process.argv[2] || new URL('../../backend/app/data/motor_ambitos.json', import.meta.url)
writeFileSync(ruta, '{\n' + Object.entries(salida).map(([k, v]) => ` ${JSON.stringify(k)}: ${JSON.stringify(v)}`).join(',\n') + '\n}\n')
console.log(Object.keys(salida).length, 'atributos con ámbito;', M.ATTR_IDS.filter((id) => !salida[id]).join(', ') || 'todos cubiertos')
