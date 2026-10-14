// Recorrido del asistente de etiquetado en el navegador (complementa recorrido.mjs):
//
// - las rutas anteriores (/etiquetas/generar, /etiquetas/masiva) llevan al
//   asistente con su origen (OC, artículo, lista de empaque o familia);
// - en «Generar», el usuario elige cómo se reparten las etiquetas en archivos:
//   las carpetas y el patrón de nombres aparecen solo cuando aplican, PNG y SVG
//   van siempre una por archivo, y lo elegido se guarda en el trabajo.
//
// Necesita la demostración corriendo, igual que recorrido.mjs:
//   npm run build && (cd ../backend && SEED_DEMO=1 COOKIE_SEGURA=0 uvicorn app.main:app --port 8765)
//   node e2e/etiquetado.mjs
import { chromium } from 'playwright'
import { vigilarRed } from './quieto.mjs'

const BASE = process.env.E2E_URL || 'http://localhost:8765'
const H = { 'X-Requested-With': 'fetch' }
const fallas = []
const revisar = (cond, msg) => { if (!cond) fallas.push(msg); console.log(`${cond ? 'ok   ' : 'FALLA'} ${msg}`) }

async function entrar(ctx, email, password = 'Supplier2026') {
  const r = await (await ctx.request.post(`${BASE}/api/auth/login`, { data: { email, password }, headers: H })).json()
  if (r.dos_pasos !== false) await ctx.request.post(`${BASE}/api/auth/verificar`, { data: { desafio: r.desafio, codigo: r.codigo_demo }, headers: H })
}
const api = (ctx) => ({
  get: async (u) => (await ctx.request.get(`${BASE}/api${u}`, { headers: H })).json(),
  post: async (u, d) => (await ctx.request.post(`${BASE}/api${u}`, { data: d, headers: H })),
  patch: async (u, d) => (await ctx.request.patch(`${BASE}/api${u}`, { data: d, headers: H })),
})

const navegador = await chromium.launch(process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {})
const ctx = await navegador.newContext({ viewport: { width: 1440, height: 900 } })
await entrar(ctx, 'interno@demo.com')
const a = api(ctx)
const p = await ctx.newPage()
const quieto = vigilarRed(p)
const errores = []
p.on('pageerror', (e) => errores.push(`JavaScript: ${e.message}`))
p.on('response', (r) => { if (r.url().includes('/api/') && r.status() >= 500) errores.push(`${r.status()} ${r.url().replace(BASE, '')}`) })

// ---- Rutas anteriores ------------------------------------------------------------------------------
const oc = (await a.get('/ordenes?solo_disponible=false&size=1')).items[0]
// Una familia con un artículo de esa OC (la demostración no trae familias de etiquetado)
let familia = (await a.get('/etiquetas/familias'))[0]
if (!familia) {
  familia = await (await a.post('/etiquetas/familias', { codigo: 'E2E', nombre: 'E2E family' })).json()
  const art = (await a.get(`/etiquetas/oc/${oc.id}`)).lineas.find((x) => x.articulo_id)
  await a.post('/etiquetas/articulos/familia', { familia_id: familia.id, ids: [art.articulo_id] })
}
for (const [ruta, espera] of [[`/etiquetas/generar?oc=${oc.id}`, /\/etiquetas\/trabajos\/\d+/],
  [`/etiquetas/masiva?familia=${familia.id}`, /\/etiquetas\/trabajos\/\d+/]]) {
  await p.goto(BASE + ruta)
  await p.waitForURL(espera, { timeout: 15000 }).catch(() => {})
  revisar(espera.test(new URL(p.url()).pathname), `${ruta} lleva al asistente (${new URL(p.url()).pathname})`)
}
{
  const t = await a.get(`/etiquetas/trabajos/${new URL(p.url()).pathname.split('/').pop()}`)
  revisar(Number(t.parametros?.familia_id) === Number(familia.id), 'la familia de /etiquetas/masiva llega al trabajo')
}

// ---- Paso «Generar»: agrupación del ZIP ----------------------------------------------------------
const lineas = (await a.get(`/etiquetas/oc/${oc.id}`)).lineas.filter((x) => x.articulo_id).slice(0, 2)
const t = await (await a.post('/etiquetas/trabajos', { origen: 'OC', parametros: { oc_ids: [oc.id], posiciones: lineas.map((x) => x.id) } })).json()
await a.post(`/etiquetas/trabajos/${t.id}/validar`, {})
const actual = await a.get(`/etiquetas/trabajos/${t.id}`)
await a.patch(`/etiquetas/trabajos/${t.id}`, { paso: 6, version: actual.version })
await p.goto(`${BASE}/etiquetas/trabajos/${t.id}`)
await quieto()
const campo = (re) => p.locator('label.campo', { hasText: re })
const elegir = async (re, opcion) => {
  await campo(re).locator('button.sb-boton').click()
  await p.getByRole('option', { name: opcion }).first().click()
  await p.waitForTimeout(200)
}
const AGRUPAR = /Split into files|Repartir en archivos/
const CARPETAS = /Folders in the ZIP|Carpetas del ZIP/
const NOMBRES = /File names|Nombres de archivo/
revisar(await campo(AGRUPAR).isVisible(), 'el paso «Generar» muestra «Repartir en archivos»')
revisar(!(await p.locator('fieldset', { hasText: CARPETAS }).isVisible()), 'un PDF por diseño: sin carpetas')
await elegir(AGRUPAR, /folder|carpeta/i)
revisar(await p.locator('fieldset', { hasText: CARPETAS }).isVisible(), 'un PDF por carpeta: se eligen carpetas')
revisar(!(await campo(NOMBRES).isVisible()), 'un PDF por carpeta: sin patrón de nombres por etiqueta')
await elegir(AGRUPAR, /One file per label|Un archivo por etiqueta/)
revisar(await campo(NOMBRES).isVisible(), 'un archivo por etiqueta: patrón de nombres')
await elegir(/Files inside the job ZIP|Archivos dentro del ZIP/, /PNG/)
revisar(!(await campo(AGRUPAR).isVisible()), 'PNG: siempre una por archivo (sin elegir agrupación)')
await elegir(/Files inside the job ZIP|Archivos dentro del ZIP/, /^PDF$/)
await elegir(AGRUPAR, /single PDF|único PDF/i)
// Lo elegido se guarda en el trabajo (al salir del paso o al generar)
const guardar = p.getByRole('button', { name: /Save|Guardar/ }).first()
if (await guardar.isVisible().catch(() => false)) await guardar.click()
await p.waitForTimeout(800)
const guardado = (await a.get(`/etiquetas/trabajos/${t.id}`)).parametros.zip || {}
revisar(guardado.agrupar === 'unico', `la agrupación se guarda en el trabajo (${JSON.stringify(guardado)})`)

await ctx.close()

revisar(errores.length === 0, `sin errores de JavaScript ni 5xx${errores.length ? `: ${errores.join(' | ')}` : ''}`)
await navegador.close()
console.log(fallas.length ? `${fallas.length} fallas` : 'recorrido de etiquetado sin fallas')
process.exit(fallas.length ? 1 : 0)
