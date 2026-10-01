// Lista todos los textos de la interfaz que pasan por t()/tr() y los guarda en
// src/i18n/claves.json (con los del servidor de backend/app/i18n_claves.json).
// Las pruebas comprueban que cada idioma los tenga todos y bien formados.
// Uso: node scripts/i18n-extraer.mjs
import fs from 'node:fs'
import path from 'node:path'

const raiz = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..')
const archivos = []
const recorrer = (d) => {
  for (const x of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, x.name)
    if (x.isDirectory()) recorrer(p)
    else if (/\.(vue|js)$/.test(x.name) && !p.includes(`${path.sep}i18n${path.sep}`)) archivos.push(p)
  }
}
recorrer(path.join(raiz, 'src'))
const claves = new Set()
const re = /\b(?:t|tr)\(\s*'((?:[^'\\]|\\.)*)'/g
for (const a of archivos) {
  const src = fs.readFileSync(a, 'utf8')
  for (const m of src.matchAll(re)) claves.add(m[1].replace(/\\(.)/g, (x, c) => (c === 'n' ? '\n' : c)))
}
const util = (k) => /[A-Za-z]{2}/.test(k.replace(/\{\d\}/g, '')) && !/^[\w-]+\.\{\d\}$/.test(k) && !/^[\w.+-]+@[\w.-]+$/.test(k)
const servidor = path.join(raiz, '..', 'backend', 'app', 'i18n_claves.json')
const deServidor = fs.existsSync(servidor) ? JSON.parse(fs.readFileSync(servidor, 'utf8')).filter(util) : []
for (const k of deServidor) claves.add(k)
fs.writeFileSync(path.join(raiz, 'src', 'i18n', 'servidor.json'), JSON.stringify(deServidor.sort(), null, 1) + '\n')
const lista = [...claves].filter(util).sort()
fs.writeFileSync(path.join(raiz, 'src', 'i18n', 'claves.json'), JSON.stringify(lista, null, 1) + '\n')
console.log(`${lista.length} textos`)
