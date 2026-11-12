// Recorrido de humo en el navegador (docs/ARQUITECTURA.md · Calidad).
//
// Entra con cada usuario de la demostración, abre todas las pantallas (y un
// documento de cada tipo) en escritorio y en celular, y falla si alguna tiene
// un error de JavaScript, un error en la consola o una respuesta 4xx/5xx de la
// API. Una pantalla a la que el rol no tiene acceso redirige al inicio: eso se
// informa, no es un error.
//
// Necesita la demostración corriendo (SEED_DEMO=1, COOKIE_SEGURA=0):
//   npm run build && (cd ../backend && SEED_DEMO=1 COOKIE_SEGURA=0 uvicorn app.main:app --port 8765)
//   npm run e2e                       # todos los usuarios, escritorio y celular
//   E2E_URL=http://otra:8765 npm run e2e
//   E2E_CHROMIUM=/ruta/a/chrome npm run e2e   # un Chromium ya instalado
import { chromium } from 'playwright'
import { vigilarRed } from './quieto.mjs'

const BASE = process.env.E2E_URL || 'http://localhost:8765'
const USUARIOS = (process.env.E2E_USUARIOS || 'admin@demo.com,interno@demo.com,tnf@demo.com,vans@demo.com').split(',')
const ANCHOS = [1440, 390]
const CLAVE = 'Supplier2026'
const H = { 'X-Requested-With': 'fetch' }

const PANTALLAS = [
  '/', '/compras/resumen', '/facturacion/resumen', '/logistica/resumen', '/integraciones', '/configuracion', '/ordenes', '/facturas', '/productos', '/productos/catalogo', '/productos/nuevo', '/productos/configuracion', '/transporte', '/reportes', '/tableros/compras', '/tableros/facturacion',
  '/seguimiento', '/seguimiento?vista=embarques', '/seguimiento?vista=documentos', '/seguimiento?vista=leadtimes',
  '/mantenimiento', '/mantenimiento?catalogo=listas', '/mantenimiento?catalogo=tipos_unidad', '/mantenimiento?catalogo=liberaciones',
  '/mantenimiento?catalogo=atributos', '/mantenimiento?catalogo=articulos', '/mantenimiento?catalogo=acuerdos',
  '/mantenimiento?catalogo=escalas',
  
  '/etiquetas', '/etiquetas/disenos', '/etiquetas/configuracion', '/etiquetas/configuracion?vista=tipos',
  '/etiquetas/configuracion?vista=familias', '/etiquetas/configuracion?vista=campos', '/etiquetas/configuracion?vista=historial',
  '/etiquetas/trabajos/nuevo?paso=que',
  '/leadtimes', '/aranceles', '/familias', '/plantillas', '/importar', '/empresa', '/perfil', '/plataforma',
  '/admin', '/admin?tab=roles', '/admin?tab=proveedores', '/admin?tab=flujo', '/admin?tab=bitacora',
]

async function entrar(ctx, email) {
  const r = await (await ctx.request.post(`${BASE}/api/auth/login`, { data: { email, password: CLAVE }, headers: H })).json()
  if (r.dos_pasos !== false) {
    await ctx.request.post(`${BASE}/api/auth/verificar`, { data: { desafio: r.desafio, codigo: r.codigo_demo }, headers: H })
  }
}

// Un documento de cada tipo que el usuario puede abrir
async function documentos(ctx) {
  const get = async (u) => {
    const r = await ctx.request.get(`${BASE}/api${u}`, { headers: H })
    return r.ok() ? r.json() : {}
  }
  const rutas = []
  const facturas = (await get('/facturas?size=2')).items || []
  for (const f of facturas) rutas.push(`/facturas/${f.id}`)
  const pl = facturas[0] && (await get(`/facturas/${facturas[0].id}`)).packing_lists?.[0]
  if (pl) rutas.push(`/packing-lists/${pl.id}`)
  for (const p of (await get('/productos?estado=&size=2')).items || []) rutas.push(`/productos/${p.id}`)
  for (const o of (await get('/ordenes?solo_disponible=false&size=2')).items || []) rutas.push(`/ordenes/${o.id}`)
  const embarques = await get('/embarques')
  if (Array.isArray(embarques) && embarques[0]) rutas.push(`/transporte/embarques/${embarques[0].id}`)
  const yo = await get('/auth/me')
  if (yo.permisos?.includes('oc.editar')) rutas.push('/ordenes/nueva')
  if (yo.permisos?.includes('etiquetas.ver')) for (const x of (await get('/etiquetas/plantillas?size=2')).items || []) rutas.push(`/etiquetas/disenos/${x.id}`)
  if (yo.permisos?.includes('etiquetas.generar')) for (const x of (await get('/etiquetas/trabajos?estado=&size=2')).items || []) rutas.push(`/etiquetas/trabajos/${x.id}`)
  return rutas
}

const navegador = await chromium.launch(process.env.E2E_CHROMIUM ? { executablePath: process.env.E2E_CHROMIUM } : {})
let fallas = 0
for (const email of USUARIOS) {
  for (const ancho of ANCHOS) {
    const ctx = await navegador.newContext({ viewport: { width: ancho, height: ancho < 600 ? 844 : 900 } })
    await entrar(ctx, email)
    const rutas = [...PANTALLAS, ...(await documentos(ctx))]
    const p = await ctx.newPage()
    const quieto = vigilarRed(p)
    const problemas = []
    const avisos = []
    let ruta = ''
    p.on('pageerror', (e) => problemas.push(`[${ruta}] JavaScript: ${e.message}`))
    p.on('console', (m) => {
      if (m.type() !== 'error') return
      // Al salir sin haber tocado nada, una pantalla no debe creer que tiene cambios sin guardar
      const texto = m.text().includes('beforeunload') ? 'pide confirmar «cambios sin guardar» sin que nadie editara' : m.text().slice(0, 200)
      problemas.push(`[${ruta}] consola: ${texto}`)
    })
    p.on('response', (r) => {
      if (r.url().includes('/api/') && r.status() >= 400) problemas.push(`[${ruta}] ${r.status()} ${r.url().replace(BASE, '')}`)
    })
    for (ruta of rutas) {
      await p.goto(BASE + ruta)
      await quieto({ maximo: 10000 })
      await p.waitForTimeout(300)
      // Una tabla no se encoge dentro de su contenedor (p. ej. un estilo que se filtra a .td-compacta)
      const angostas = await p.evaluate(() => [...document.querySelectorAll('.td')].filter((t) => {
        const w = t.getBoundingClientRect().width, wp = t.parentElement?.getBoundingClientRect().width || 0
        return wp > 300 && w < wp * 0.5
      }).length)
      if (angostas) problemas.push(`[${ruta}] ${angostas} tabla(s) encogida(s) dentro de su contenedor`)
      const final = new URL(p.url()).pathname
      if (final === '/' && ruta !== '/' && !ruta.startsWith('/?')) avisos.push(ruta)
    }
    await ctx.close()
    console.log(`${email} · ${ancho}px · ${rutas.length} pantallas · ${problemas.length ? `${problemas.length} problemas` : 'sin problemas'}` +
      (avisos.length ? ` · sin acceso (redirige al inicio): ${avisos.join(', ')}` : ''))
    for (const x of problemas) console.log(`  ${x}`)
    fallas += problemas.length
  }
}
await navegador.close()
process.exit(fallas ? 1 : 0)
