<script setup>
import { opcionesLista } from '@/nucleo/listas.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { errorApi } from '@/stores/ui'
import { puede } from '@/stores/sesion'
import { plural } from '@/nucleo/utils'

// Lead time efectivo: elige Región → País → Puerto y muestra la cadena que
// resulta después de aplicar la herencia (Global → Región → País → Puerto),
// qué viene de cada nivel y qué fue sobrescrito.
const route = useRoute()
const router = useRouter()
const amb = ref({ regiones: [], paises: [], puertos: [], pasos: [] })
const sel = reactive({ region: route.query.region || '', pais: route.query.pais || '', puerto: route.query.puerto || '', modo: route.query.modo || '' })
const datos = ref(null)
const MODOS = computed(() => [{ valor: '', texto: t('All modes (general)') }, ...opcionesLista('modo_transporte').map(([valor, texto]) => ({ valor, texto }))])
const NIVEL = { GLOBAL: t('Global'), REGION: t('Region'), PAIS: t('Country'), PUERTO: t('Port') }

const paises = computed(() => amb.value.paises.filter((p) => !sel.region || p.region === sel.region))
const puertos = computed(() => amb.value.puertos.filter((p) => (!sel.pais || p.pais === sel.pais) && (!sel.region || paises.value.some((x) => x.valor === p.pais))))
// Elegir un nivel más específico completa los de arriba; cambiar uno de arriba limpia los de abajo si no corresponden
watch(() => sel.puerto, (v) => { const p = amb.value.puertos.find((x) => x.valor === v); if (p) sel.pais = p.pais })
watch(() => sel.pais, (v) => {
  const p = amb.value.paises.find((x) => x.valor === v)
  if (p?.region) sel.region = p.region
  if (sel.puerto && !puertos.value.some((x) => x.valor === sel.puerto)) sel.puerto = ''
})
watch(() => sel.region, () => { if (sel.pais && !paises.value.some((x) => x.valor === sel.pais)) sel.pais = '' })

async function cargar() {
  try {
    datos.value = await api.get('/leadtimes/efectivo', { region: sel.region || undefined, pais: sel.pais || undefined, puerto: sel.puerto || undefined, modo: sel.modo || undefined })
    router.replace({ query: Object.fromEntries(Object.entries(sel).filter(([, v]) => v)) })
  } catch (e) {
    errorApi(e)
  }
}
watch(sel, cargar)
onMounted(async () => {
  try {
    amb.value = await api.get('/leadtimes/ambitos')
    // Un puerto o país elegido trae su país y su región
    const pu = amb.value.puertos.find((x) => x.valor === sel.puerto)
    if (pu) sel.pais = pu.pais
    const pa = amb.value.paises.find((x) => x.valor === sel.pais)
    if (pa?.region) sel.region = pa.region
  } catch (e) {
    errorApi(e)
  }
  cargar()
})

const nombre = (c) => amb.value.pasos.find((p) => p.codigo === c)?.nombre || c
const hitoTxt = (h) => amb.value.hitos?.find((x) => x.valor === h)?.texto
// Pasos que aplican al modo elegido: el del modo exacto o, si no hay, el general
const pasos = computed(() => {
  const todos = datos.value?.pasos || []
  const out = []
  for (const p of todos) {
    if (p.modo && p.modo !== sel.modo) continue
    if (!p.modo && todos.some((q) => q.paso === p.paso && q.modo && q.modo === sel.modo)) continue
    out.push(p)
  }
  return out
})
const dias = computed(() => datos.value?.dias || {})
const ancla = computed(() => datos.value?.ancla)
const diasTxt = (n, habiles) => (habiles ? plural(n, t('business day'), t('business days')) : plural(n, t('day'), t('days')))
const relTxt = (p) => (!p.ref ? t('Anchor of the lead time') : p.dias === 0 ? t('Same day as {0}', [nombre(p.ref)])
  : t('{0} {1} {2}', [diasTxt(Math.abs(p.dias), p.habiles), p.dias < 0 ? t('before') : t('after'), nombre(p.ref)]))
const cortoTxt = (p) => (!p.ref ? '0' : `${p.dias > 0 ? '+' : p.dias < 0 ? '−' : ''}${Math.abs(p.dias)}${p.habiles ? ' bd' : ' d'}`)

const diaTxt = (d) => (d === undefined ? '—' : d === 0 ? '0' : `${d > 0 ? '+' : '−'}${Math.abs(d)} d`)
const documentoTxt = (d) => amb.value.documentos?.find((x) => x.valor === d)?.texto || t('No document')
const numero = (p) => pasos.value.indexOf(p) + 1

// Ancho real de la pista, para que los números del mismo tramo no se encimen
const lineaEl = ref(null)
const anchoPista = ref(900)
const obs = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(([e]) => { anchoPista.value = Math.max(e.contentRect.width - 160, 200) })
watch(lineaEl, (el, viejo) => { if (viejo) obs?.unobserve(viejo); if (el) obs?.observe(el) })
onBeforeUnmount(() => obs?.disconnect())

// Línea de tiempo: un carril por documento (la OC, el embarque…) y cada paso
// con su número en el día que le toca respecto del ancla. Los pasos del mismo
// día se apilan en vez de encimarse; el nombre está en la lista de abajo.
const linea = computed(() => {
  const xs = pasos.value.filter((p) => dias.value[p.paso] !== undefined)
  if (!xs.length) return { carriles: [], eje: [], min: 0, max: 0 }
  const vals = xs.map((p) => dias.value[p.paso])
  const min = Math.min(...vals, 0)
  const max = Math.max(...vals, 0)
  const ancho = Math.max(max - min, 1)
  const separa = (26 / anchoPista.value) * 100
  const orden = [...(amb.value.documentos || []).map((d) => d.valor), null]
  const carriles = orden.map((doc) => {
    const filas = []
    const marcas = xs.filter((p) => (p.documento || null) === doc).sort((a, b) => dias.value[a.paso] - dias.value[b.paso]).map((p) => {
      const pos = ((dias.value[p.paso] - min) / ancho) * 100
      let fila = 0
      while (filas[fila] !== undefined && pos - filas[fila] < separa) fila++
      filas[fila] = pos
      return { p, pos, fila, n: numero(p) }
    })
    return { doc, marcas, filas: Math.max(1, filas.length) }
  }).filter((c) => c.marcas.length)
  const eje = []
  const pasoEje = ancho > 120 ? 30 : ancho > 50 ? 10 : 5
  for (let d = Math.ceil(min / pasoEje) * pasoEje; d <= max; d += pasoEje) eje.push({ d, pos: ((d - min) / ancho) * 100 })
  return { carriles, eje, min, max, cero: ((0 - min) / ancho) * 100 }
})
const totalDias = computed(() => linea.value.max - linea.value.min)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Effective lead time') }}</h1>
      <p>{{ t('Steps that apply to a region, country or port after inheritance (Port > Country > Region > Global).') }}</p>
    </div>
    <div class="acciones">
      <router-link class="btn" to="/mantenimiento?catalogo=pasos_lt"><Icono nombre="lista" :tam="15" />{{ t('Steps catalog') }}</router-link>
      <router-link v-if="puede('catalogos.editar')" class="btn btn-primario" to="/mantenimiento?catalogo=leadtimes"><Icono nombre="editar" :tam="15" />{{ t('Lead time rules') }}</router-link>
    </div>
  </div>

  <div class="filtros selectores">
    <SelectBusqueda v-model="sel.region" :opciones="amb.regiones" :vacio="t('All regions')" :etiqueta="t('Region')" />
    <SelectBusqueda v-model="sel.pais" :opciones="paises" :vacio="t('All countries')" :etiqueta="t('Country')" />
    <SelectBusqueda v-model="sel.puerto" :opciones="puertos" :vacio="t('All ports')" :etiqueta="t('Port')" />
    <SelectBusqueda v-model="sel.modo" :opciones="MODOS" :etiqueta="t('Transport mode')" :busqueda="false" />
  </div>

  <template v-if="datos">
    <!-- Niveles de la herencia, de lo general a lo específico -->
    <ol class="niveles" :aria-label="t('Inheritance')">
      <li v-for="n in datos.niveles" :key="n.nivel" :class="[`n-${n.nivel}`, { vacio: !n.cambios }]"
          :title="tx(n.cambios ? t('{0} changes', [n.cambios]) : n.regla_id ? t('No changes') : t('No rule: inherits everything'))">
        <i></i><span v-if="n.nivel !== 'GLOBAL'" class="nivel">{{ tx(NIVEL[n.nivel]) }}</span><b>{{ tx(n.nombre) }}</b>
        <span class="cuenta">{{ n.cambios || '—' }}</span>
      </li>
    </ol>
    <p v-if="datos.errores.length" class="nota error bloque"><Icono nombre="alerta" />{{ tx(datos.errores.join(' ')) }}</p>

    <!-- Línea de tiempo por documento -->
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Timeline') }}</h2>
        <p>{{ t('Days relative to {0}. Total span: {1} days.', [nombre(ancla), totalDias]) }}</p></div></div>
      <div ref="lineaEl" class="linea" role="img" :aria-label="tx(pasos.map((p) => `${numero(p)}. ${p.nombre} ${diaTxt(dias[p.paso])}`).join(', '))">
        <div class="eje-fila">
          <span></span>
          <div class="eje">
            <span v-for="m in linea.eje" :key="m.d" class="tick" :class="{ cero: m.d === 0 }" :style="{ insetInlineStart: m.pos + '%' }">{{ m.d > 0 ? '+' : '' }}{{ m.d }}</span>
          </div>
        </div>
        <div v-for="c in linea.carriles" :key="c.doc || '-'" class="carril">
          <span class="doc">{{ tx(documentoTxt(c.doc)) }}</span>
          <div class="pista" :style="{ '--filas': c.filas }">
            <span class="ancla" :style="{ insetInlineStart: linea.cero + '%' }"></span>
            <span v-for="m in c.marcas" :key="m.p.paso + m.p.modo" class="marca" :class="[`n-${m.p.origen.nivel}`, { medido: m.p.hito }]"
                  :style="{ insetInlineStart: m.pos + '%', '--fila': m.fila }" :title="tx(`${m.n}. ${m.p.nombre} · ${diaTxt(dias[m.p.paso])} · ${relTxt(m.p)}`)">{{ m.n }}</span>
          </div>
        </div>
      </div>
      <div class="leyenda">
        <span v-for="n in datos.niveles" :key="n.nivel" :class="`n-${n.nivel}`"><i></i>{{ tx(n.nombre) }}</span>
        <span class="medido-ley"><i></i>{{ t('Measured') }}</span>
      </div>
    </section>

    <!-- Pasos en el orden definido -->
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Steps in order') }}</h2></div></div>
      <div class="tabla-marco tabla-captura">
        <table class="tabla tabla-pasos">
          <thead><tr><th>#</th><th>{{ t('Step') }}</th><th>{{ t('Document') }}</th><th class="col-sec">{{ t('Rule') }}</th>
            <th class="num">{{ t('Day') }}</th><th>{{ t('Level') }}</th></tr></thead>
          <tbody>
            <tr v-for="p in pasos" :key="p.paso + p.modo" :class="[`n-${p.origen.nivel}`, { sobrescrito: p.previo }]">
              <td :data-label="'#'"><span class="num-paso" :class="{ medido: p.hito }">{{ numero(p) }}</span></td>
              <td :data-label="t('Step')" class="envolver"><b>{{ tx(p.nombre) }}</b>
                <Icono v-if="p.hito" nombre="reloj" :tam="12" class="icono-medido" :title="tx(t('Measured') + ': ' + (hitoTxt(p.hito) || ''))" />
                <span v-if="p.modo" class="etiqueta acento">{{ tx(MODOS.find((m) => m.valor === p.modo)?.texto) }}</span>
                <span v-if="p.historial?.length" class="sub">
                  <template v-for="h in p.historial" :key="h.origen.nivel"><s>{{ tx(h.origen.nombre) }} {{ tx(cortoTxt(h)) }}</s> → </template>{{ tx(cortoTxt(p)) }}</span></td>
              <td :data-label="t('Document')">{{ tx(documentoTxt(p.documento)) }}</td>
              <td :data-label="t('Rule')" class="col-sec apagado">{{ tx(relTxt(p)) }}</td>
              <td :data-label="t('Day')" class="num fuerte">{{ tx(diaTxt(dias[p.paso])) }}</td>
              <td :data-label="t('Level')"><span class="origen" :class="`n-${p.origen.nivel}`">{{ tx(p.origen.nombre) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="datos.quitados.length" class="ayuda">{{ t('Removed: {0}', [datos.quitados.map((q) => `${q.nombre} (${q.quitado_por.nombre})`).join(', ')]) }}</p>
    </section>
  </template>
</template>

<style scoped>
.selectores { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin-bottom: 14px; }
.selectores :deep(.sb) { min-width: 0; max-width: none; width: 100%; }
.n-GLOBAL { --c: var(--tinta-3); }
.n-REGION { --c: var(--info); }
.n-PAIS { --c: var(--ok); }
.n-PUERTO { --c: var(--acento); }
.niveles { list-style: none; margin: 0 0 14px; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.niveles li { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: var(--radio-pildora); border: 1px solid var(--linea); background: var(--superficie); font-size: var(--t-sm); }
.niveles li i, .leyenda i { width: 9px; height: 9px; border-radius: 50%; background: var(--c); display: inline-block; flex: none; }
.niveles li.vacio { opacity: 0.6; }
.nivel { font-size: var(--t-2xs); text-transform: uppercase; letter-spacing: 0.04em; color: var(--tinta-3); font-weight: 700; }
.cuenta { font-size: var(--t-2xs); font-weight: 700; color: var(--c); background: color-mix(in srgb, var(--c) 12%, transparent); border-radius: 99px; padding: 0 7px; }
.panel { margin-bottom: 14px; }
/* Línea de tiempo: rótulo del carril a la izquierda y la pista con los números */
.linea { display: flex; flex-direction: column; gap: 4px; }
.eje-fila, .carril { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 10px; align-items: center; }
.eje { position: relative; height: 18px; margin-inline: 14px; }
.tick { position: absolute; transform: translateX(-50%); font-size: var(--t-2xs); color: var(--tinta-3); font-variant-numeric: tabular-nums; }
.tick.cero { color: var(--tinta); font-weight: 700; }
.doc { font-size: var(--t-xs); font-weight: 650; color: var(--tinta-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pista { position: relative; height: calc(12px + var(--filas) * 26px); margin-inline: 14px; background: var(--superficie-2); border-radius: var(--radio); }
.pista::before { content: ''; position: absolute; inset-inline: 0; top: 50%; height: 1px; background: var(--linea); }
.ancla { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--tinta-3); opacity: 0.5; }
.marca { position: absolute; top: calc(6px + var(--fila) * 26px); transform: translateX(-50%); width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center;
  font-size: var(--t-2xs); font-weight: 700; color: var(--c); background: var(--superficie); border: 2px solid var(--c); cursor: default; font-variant-numeric: tabular-nums; }
.marca.medido { background: var(--c); color: var(--superficie); }
.leyenda { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: var(--t-xs); color: var(--tinta-2); margin-top: 12px; }
.leyenda span { display: inline-flex; align-items: center; gap: 5px; }
.medido-ley i { background: var(--tinta-3); }
.leyenda > span:not(.medido-ley) i { background: transparent; border: 2px solid var(--c); width: 10px; height: 10px; }
.num-paso { width: 24px; height: 24px; border-radius: 50%; display: inline-grid; place-items: center; font-size: var(--t-xs); font-weight: 700; color: var(--c); border: 2px solid var(--c); }
.num-paso.medido { background: var(--c); color: var(--superficie); }
.icono-medido { color: var(--tinta-3); margin-inline-start: 4px; vertical-align: -1px; }
.tabla-pasos tr.sobrescrito > td { background: color-mix(in srgb, var(--c) 6%, transparent); }
.tabla-pasos s { color: var(--tinta-3); }
.origen { font-size: var(--t-xs); font-weight: 650; color: var(--c); padding: 2px 8px; border-radius: 99px; background: color-mix(in srgb, var(--c) 12%, transparent); white-space: nowrap; }
/* Celular: cada paso en dos renglones (número · paso · día / documento · nivel) */
@media (max-width: 720px) {
  .tabla-pasos thead, .tabla-pasos .col-sec { display: none; }
  .tabla-pasos, .tabla-pasos tbody { display: block; }
  .tabla-pasos tr { display: grid; grid-template-columns: 32px minmax(0, 1fr) auto; align-items: center; column-gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--linea-suave); }
  .tabla-pasos td { padding: 0; border: 0; white-space: normal; min-width: 0; max-width: none; }
  .tabla-pasos td:nth-child(1) { grid-row: span 2; }
  .tabla-pasos td:nth-child(3) { grid-column: 2; grid-row: 2; font-size: var(--t-xs); color: var(--tinta-3); }
  .tabla-pasos td:nth-child(5) { grid-column: 3; grid-row: 1; }
  .tabla-pasos td:nth-child(6) { grid-column: 3; grid-row: 2; text-align: end; }
}
@media (max-width: 600px) {
  .eje-fila, .carril { grid-template-columns: 1fr; gap: 2px; }
  .eje-fila > span:first-child { display: none; }
}
</style>
