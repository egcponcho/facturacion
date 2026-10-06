// Casos de paridad de las descripciones aduanera y comercial que armaba motor.js
// (descripcionProfesional, descripcionComercial) sobre las fichas de paridad.
// Uso: node scripts/paridad-descripciones.mjs
import { readFileSync, writeFileSync } from 'node:fs'
import * as M from '../src/clasificacion/motor.js'

const base = new URL('../../backend/tests/paridad/', import.meta.url)
const { casos } = JSON.parse(readFileSync(new URL('atributos.json', base)))
const MARCAS = ['', 'Vans', 'The North Face']
const out = casos.map((c, i) => {
  const s = { ...JSON.parse(JSON.stringify(c.entrada)), marca: MARCAS[i % 3] }
  if (i % 4 === 1) s.genero = ['M', 'F', 'U'][i % 3]
  if (i % 5 === 2) s.largo = 'corto'
  if (i % 7 === 3) s.sueter = true
  M.normalizar(s)
  return { entrada: { ...c.entrada, marca: s.marca, genero: s.genero, largo: s.largo, sueter: s.sueter }, aduana: M.descripcionProfesional(s), comercial: M.descripcionComercial(s) }
})
writeFileSync(new URL('descripciones.json', base), JSON.stringify({ casos: out }) + '\n')
console.log(out.length, 'descripciones')
