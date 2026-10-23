// Recorrido del asistente de etiquetado en el navegador (complementa recorrido.mjs):
//
// - las rutas anteriores (/etiquetas/generar, /etiquetas/masiva, /etiquetas?vista=…,
//   /etiquetas/plantillas/:id) llevan a su lugar nuevo (asistente, Configuración, Diseños);
// - la configuración es una guía en orden (sin pestañas): abre en el primer paso
//   que falta y cada paso dice si está listo;
// - el asistente de una familia se deja como borrador, se retoma desde la guía y
//   al terminar se aplica de una vez;
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
  put: async (u, d) => (await ctx.request.put(`${BASE}/api${u}`, { data: d, headers: H })),
  del: async (u) => (await ctx.request.delete(`${BASE}/api${u}`, { headers: H })),
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
const posiciones = (await a.get(`/ordenes/${oc.id}`)).posiciones.filter((x) => x.codigo_articulo)
// Una familia con un artículo de esa OC
let familia = (await a.get('/etiquetas/familias'))[0]
if (!familia) familia = await (await a.post('/grupos-producto', { clase: 'FAMILIA', codigo: 'E2E', nombre: 'E2E family' })).json()
const art = (await a.get(`/etiquetas/articulos?q=${encodeURIComponent(posiciones[0].codigo_articulo)}`)).items?.[0]
if (art && !art.familia_id) await a.post('/grupos-producto/articulos/familia', { familia_id: familia.id, ids: [art.id] })
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
// Las vistas viejas de /etiquetas?vista= llevan a su lugar nuevo
for (const [ruta, camino, vista] of [['/etiquetas?vista=familias', '/etiquetas/configuracion', 'familias'],
  ['/etiquetas?vista=campos', '/etiquetas/configuracion', 'campos'], ['/etiquetas?vista=plantillas', '/etiquetas/disenos', null]]) {
  await p.goto(BASE + ruta)
  await quieto()
  const u = new URL(p.url())
  revisar(u.pathname === camino && (vista === null || [u.searchParams.get('vista'), u.searchParams.get('paso')].includes(vista)), `${ruta} → ${u.pathname}${u.search}`)
}
const diseno = (await a.get('/etiquetas/plantillas?size=1')).items?.[0]
if (diseno) {
  await p.goto(`${BASE}/etiquetas/plantillas/${diseno.id}`)
  await quieto()
  revisar(new URL(p.url()).pathname === `/etiquetas/disenos/${diseno.id}`, 'el editor de plantillas pasa a /etiquetas/disenos/:id')
}

// ---- Configuración: guía paso a paso ------------------------------------------------------------
await p.goto(`${BASE}/etiquetas/configuracion`)
await quieto()
{
  const pasos = p.locator('.guia-paso')
  revisar(await pasos.count() === 6 && !(await p.locator('[role=tab]', { hasText: /Families and items|Familias y artículos/ }).count()), 'la configuración es una guía de 6 pasos, sin pestañas')
  const paso = new URL(p.url()).searchParams.get('paso')
  const actual = await p.locator('.guia-paso.actual').getAttribute('class')
  revisar(!!paso && (actual.includes('falta') || paso === 'matriz'), `abre en el primer paso que falta (${paso})`)
  await pasos.filter({ hasText: /Which design goes on what|Qué diseño va en qué/ }).click()
  await quieto()
  revisar(await p.locator('.matriz, table').first().isVisible() && new URL(p.url()).searchParams.get('paso') === 'matriz', 'el paso «Qué diseño va en qué» muestra la matriz')
  await p.getByRole('button', { name: /^(Next|Siguiente): / }).click()
  await quieto()
  revisar(new URL(p.url()).searchParams.get('paso') === 'campos', '«Siguiente» lleva al paso que sigue')
}

// ---- Asistente de familia: borrador, retomar y terminar -------------------------------------------
{
  const sinFamilia = (await a.get('/etiquetas/productos?familia=sin&size=5')).items?.[0]
  await p.goto(`${BASE}/etiquetas/configuracion/familia/nueva`)
  await quieto()
  const datos = p.locator('.af-cuerpo input')
  await datos.nth(0).fill('E2EWIZ')
  await datos.nth(1).fill('E2E wizard')
  await p.getByRole('button', { name: /^(Next|Siguiente): / }).click()
  await quieto()
  if (sinFamilia) {
    await p.locator('.af-cuerpo tbody tr', { hasText: sinFamilia.codigo_generico }).first().locator('input[type=checkbox]').check()
    revisar(await p.locator('.barra-seleccion, .bs').first().isVisible().catch(() => false) || await p.locator('.af-elegidos').isVisible(), 'lo elegido se ve arriba y en la barra flotante')
  }
  revisar(!(await a.get('/etiquetas/familias')).some((f) => f.codigo === 'E2EWIZ'), 'mientras se avanza, nada se aplica')
  await p.getByRole('button', { name: /Save draft and exit|Guardar borrador y salir/ }).click()
  await quieto()
  const borr = p.locator('.guia-borrador a', { hasText: 'E2E wizard' })
  revisar(await borr.isVisible(), 'el borrador aparece en la guía')
  revisar(!(await a.get('/etiquetas/familias')).some((f) => f.codigo === 'E2EWIZ'), 'guardar el borrador no crea la familia')
  await borr.click()
  await quieto()
  revisar(await p.locator('.af-borrador').isVisible() && (await p.locator('.af-elegidos').count()) === (sinFamilia ? 1 : 0), 'el borrador se retoma donde quedó')
  await p.locator('.af-paso').last().click()
  await quieto()
  await p.getByRole('button', { name: /Finish and apply|Terminar y aplicar/ }).click()
  await quieto()
  const fam = (await a.get('/etiquetas/familias')).find((f) => f.codigo === 'E2EWIZ')
  revisar(!!fam && (!sinFamilia || fam.productos === 1), 'al terminar se crea la familia con lo elegido')
  revisar(!(await a.get('/perfil/borradores')).length, 'al terminar el borrador desaparece')
  // Deja la demostración como estaba
  if (fam) {
    if (sinFamilia) await a.post('/grupos-producto/productos/familia', { familia_id: null, ids: [sinFamilia.id] })
    await a.del(`/grupos-producto/${fam.id}`)
  }
}

// ---- Motor de reglas: categoría con condiciones, probar, «no lleva» y matriz -----------------------
{
  const fam = (await a.get('/etiquetas/familias')).find((f) => f.activa && f.articulos > 0)
  const art1 = fam && (await a.get(`/etiquetas/articulos?familia=${fam.id}&size=1`)).items?.[0]
  if (fam && art1) {
    const codigo = `E2E${Date.now() % 1000000}`
    const nombre = `E2E category ${codigo}`
    await p.goto(`${BASE}/etiquetas/configuracion?paso=familias&familia=${fam.id}`)
    await quieto()
    await p.getByRole('button', { name: /^(New category|Nueva categoría)$/ }).click()
    const form = p.locator('.cats-form')
    await form.locator('input').nth(0).fill(codigo)
    await form.locator('input').nth(1).fill(nombre)
    const cond = form.locator('.condicion').first()
    await cond.locator('button.sb-boton').first().click()
    await p.getByRole('option', { name: /^(Item SKU|SKU|SKU del artículo)$/i }).first().click()
    await cond.locator(':scope > input').fill(art1.sku)
    await form.getByRole('button', { name: /Test with the items|Probar con los artículos/ }).click()
    await quieto()
    revisar(/\b1 (of|de)\b/.test(await form.locator('.cats-prueba').innerText()), 'probar dice cuántos artículos caen en la categoría antes de guardar')
    revisar(!(await a.get(`/grupos-producto/categorias?familia_id=${fam.id}`)).some((c) => c.codigo === codigo), 'probar no guarda nada')
    await form.getByRole('button', { name: /^(Create category|Crear categoría)$/ }).click()
    await quieto()
    const cat = (await a.get(`/grupos-producto/categorias?familia_id=${fam.id}`)).find((c) => c.codigo === codigo)
    revisar(cat?.articulos === 1, `la categoría se crea y reconoce su artículo (${cat?.articulos})`)
    // Su primera etiqueta: «no lleva»
    const tipo = (await a.get('/etiquetas/tipos')).find((x) => x.sujeto === 'ARTICULO')
    await p.locator('.cats-lista > li', { hasText: nombre }).locator('.cats-etiqueta').first().click()
    await quieto()
    await p.getByLabel(/Does not carry this label|No lleva esta etiqueta/).check()
    await quieto()
    revisar(await p.locator('.efecto').getByText(/will not carry|no llevarán/).isVisible(), '«qué cambia» cuenta los que no llevarán la etiqueta')
    await p.locator('.celda-pie .btn-primario').click()
    await quieto()
    const celda = await a.get(`/etiquetas/celda?tipo=${tipo.id}&nivel=CATEGORIA&destino_id=${cat.id}`)
    revisar(celda.normal?.accion === 'NO_LLEVA', 'la celda de la categoría guarda «no lleva»')
    const el = (await a.get(`/etiquetas/resolver?articulo_id=${art1.id}`)).elecciones.find((x) => x.tipo_etiqueta_id === tipo.id)
    revisar(el?.no_lleva === true, 'su artículo ya no lleva esa etiqueta (sin error)')
    await p.goto(`${BASE}/etiquetas/configuracion?paso=matriz`)
    await quieto()
    const filaCat = p.locator('tr.mz-categoria', { hasText: nombre })
    revisar(await filaCat.isVisible() && await filaCat.getByText(/Does not carry it|No la lleva/).isVisible(), 'la matriz muestra la categoría bajo su familia con «no la lleva»')
    // Deja la demostración como estaba
    await a.put('/etiquetas/usos/celda', { tipo_etiqueta_id: tipo.id, nivel: 'CATEGORIA', destino_id: cat.id, firma: celda.firma, normal: null })
    // La regla dada de baja queda en el historial: la categoría no se borra, se desactiva
    revisar((await a.del(`/grupos-producto/${cat.id}`)).status() === 409, 'una categoría con historial de reglas no se borra')
    await a.patch(`/grupos-producto/${cat.id}`, { activa: false })
    const m = await a.get('/etiquetas/matriz')
    revisar(!m.filas.some((f) => f.nivel === 'CATEGORIA' && f.id === cat.id), 'desactivada, sale de la matriz y sus artículos vuelven a la familia')
  }
}

// ---- Paso «Generar»: agrupación del ZIP ----------------------------------------------------------
const lineas = posiciones.slice(0, 2)
const t = await (await a.post('/etiquetas/trabajos', { origen: 'OC', parametros: { oc_ids: [oc.id], posiciones: lineas.map((x) => x.id) } })).json()
await a.post(`/etiquetas/trabajos/${t.id}/validar`, {})
const actual = await a.get(`/etiquetas/trabajos/${t.id}`)
await a.patch(`/etiquetas/trabajos/${t.id}`, { paso: 2, version: actual.version })
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

// ---- Reimprimir y anular una ejecución (con motivo) ---------------------------------------------------
{
  // Un trabajo sin datos que escribir a mano: el sticker de precio de una línea
  const precio = (await a.get('/etiquetas/tipos')).find((x) => x.codigo === 'PRECIO')
  const tg = await (await a.post('/etiquetas/trabajos', { origen: 'OC', parametros: { oc_ids: [oc.id], posiciones: [lineas[0].id],
    tipos: [precio.id] } })).json()
  const v = await (await a.post(`/etiquetas/trabajos/${tg.id}/validar`, {})).json()
  const g = await a.post(`/etiquetas/trabajos/${tg.id}/generar`, { formato: 'PDF', version: v.version, aceptar_advertencias: true })
  revisar(g.ok(), `el trabajo se genera para reimprimir y anular (${g.status()} ${g.ok() ? '' : await g.text()})`)
  await p.goto(`${BASE}/etiquetas/trabajos/${tg.id}`)
  await quieto()
  const fila = p.locator('.tj-tabla tbody tr').first()
  const REIMPRIMIR = /^(Reprint|Reimprimir)$/
  revisar(await fila.getByRole('button', { name: REIMPRIMIR }).isVisible(), 'cada ejecución ofrece «Reimprimir»')
  await fila.getByRole('button', { name: REIMPRIMIR }).click()
  // La reimpresión se llena en la misma tabla (debajo de su fila), sin ventana
  const enFila = p.locator('.tj-fila-detalle')
  revisar(await enFila.isVisible() && !(await p.locator('.modal').isVisible()), 'reimprimir se llena debajo de la fila, sin ventana')
  await enFila.locator('input[required]').first().fill('E2E printer jam')
  await enFila.getByRole('checkbox', { name: /All the labels|Todas las etiquetas/ }).uncheck()
  await enFila.locator('tbody input[type=checkbox]').first().check()
  await enFila.locator('tbody input[type=number]').nth(1).fill('1')
  const descarga = p.waitForEvent('download', { timeout: 15000 }).catch(() => null)
  await enFila.getByRole('button', { name: /^(Reprint|Reimprimir) 1/ }).click()
  const archivo = await descarga
  revisar(!!archivo && /reprint1/.test(archivo.suggestedFilename()), `la reimpresión se descarga (${archivo?.suggestedFilename()})`)
  await quieto()
  const e1 = (await a.get(`/etiquetas/trabajos/${tg.id}`)).ejecuciones[0]
  revisar(e1.reimpresiones?.length === 1 && e1.reimpresiones[0].total === 1 && e1.reimpresiones[0].motivo === 'E2E printer jam',
    `la reimpresión queda en el historial con su motivo (${JSON.stringify(e1.reimpresiones)})`)
  const aparece = (loc) => loc.first().waitFor({ timeout: 15000 }).then(() => true).catch(() => false)
  revisar(await aparece(fila.getByText(/Reprinted 1 times|Reimpresa 1 veces/)),
    `la fila muestra que se reimprimió (${JSON.stringify(await fila.innerText().catch(() => ''))})`)
  // Anular
  const modal = p.locator('.modal')
  await fila.getByRole('button', { name: /^(Void|Anular)$/ }).click()
  await modal.locator('input[required]').first().fill('E2E wrong data')
  await modal.getByRole('button', { name: /^(Void|Anular)$/ }).click()
  await quieto()
  const t2 = await a.get(`/etiquetas/trabajos/${tg.id}`)
  revisar(t2.ejecuciones[0].situacion === 'ANULADA' && t2.registros.every((r) => r.estado !== 'GENERADO'),
    `anular deja la ejecución anulada y los registros pendientes (${t2.ejecuciones[0].situacion}, ${t2.estado})`)
  revisar(await aparece(fila.getByText(/E2E wrong data/)) && !(await fila.getByRole('button', { name: REIMPRIMIR }).isVisible()),
    'la fila anulada muestra el motivo y ya no ofrece reimprimir')
}

await ctx.close()

revisar(errores.length === 0, `sin errores de JavaScript ni 5xx${errores.length ? `: ${errores.join(' | ')}` : ''}`)
await navegador.close()
console.log(fallas.length ? `${fallas.length} fallas` : 'recorrido de etiquetado sin fallas')
process.exit(fallas.length ? 1 : 0)
