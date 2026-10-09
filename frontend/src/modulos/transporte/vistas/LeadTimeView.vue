<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
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
const MODOS = [{ valor: '', texto: t('All modes (general)') }, { valor: 'MARITIMO', texto: t('Ocean') }, { valor: 'AEREO', texto: t('Air') }, { valor: 'TERRESTRE', texto: t('Road') }]
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
const offTxt = (d) => (d === undefined ? '' : d === 0 ? tx(nombre(ancla.value)) : `${nombre(ancla.value)} ${d > 0 ? '+' : '−'}${Math.abs(d)} d`)

// Línea de tiempo: cada paso en su día respecto del ancla; las etiquetas se
// reparten en carriles para que no se encimen
const linea = computed(() => {
  const xs = pasos.value.filter((p) => dias.value[p.paso] !== undefined)
  if (!xs.length) return { marcas: [], min: 0, max: 0, carriles: 1 }
  const vals = xs.map((p) => dias.value[p.paso])
  const min = Math.min(...vals, 0)
  const max = Math.max(...vals, 0)
  const ancho = Math.max(max - min, 1)
  const ultimos = []
  const marcas = [...xs].sort((a, b) => dias.value[a.paso] - dias.value[b.paso]).map((p) => {
    const pos = ((dias.value[p.paso] - min) / ancho) * 100
    let carril = 0
    while (ultimos[carril] !== undefined && pos - ultimos[carril] < 14) carril++
    ultimos[carril] = pos
    return { p, pos, carril }
  })
  const marcasEje = []
  const pasoEje = ancho > 120 ? 30 : ancho > 50 ? 10 : 5
  for (let d = Math.ceil(min / pasoEje) * pasoEje; d <= max; d += pasoEje) marcasEje.push({ d, pos: ((d - min) / ancho) * 100 })
  return { marcas, min, max, carriles: Math.max(1, ultimos.length), eje: marcasEje }
})
const totalDias = computed(() => linea.value.max - linea.value.min)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Effective lead time') }}</h1>
      <p>{{ t('The lead time that applies to a region, country or port after inheritance: Port > Country > Region > Global. Each step shows the level it comes from and what it overrides.') }}</p>
    </div>
    <div class="fila-flex">
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
    <!-- Niveles de la herencia -->
    <ol class="niveles" :aria-label="t('Inheritance')">
      <li v-for="n in datos.niveles" :key="n.nivel" :class="[`n-${n.nivel}`, { vacio: !n.cambios }]">
        <span class="nivel">{{ tx(NIVEL[n.nivel]) }}</span>
        <b>{{ tx(n.nombre) }}</b>
        <span class="sub">{{ tx(n.cambios ? t('{0} changes', [n.cambios]) : n.regla_id ? t('No changes') : t('No rule: inherits everything')) }}</span>
      </li>
    </ol>
    <p v-if="datos.errores.length" class="nota error bloque"><Icono nombre="alerta" />{{ tx(datos.errores.join(' ')) }}</p>

    <!-- Línea de tiempo -->
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Timeline') }}</h2>
        <p>{{ t('Days relative to {0}. Total span: {1} days.', [nombre(ancla), totalDias]) }}</p></div></div>
      <div class="linea" :style="{ '--carriles': linea.carriles }">
        <div class="eje"></div>
        <span v-for="m in linea.eje" :key="m.d" class="tick" :style="{ insetInlineStart: m.pos + '%' }">{{ m.d > 0 ? '+' : '' }}{{ m.d }}</span>
        <div v-for="m in linea.marcas" :key="m.p.paso + m.p.modo" class="marca" :class="`n-${m.p.origen.nivel}`"
             :style="{ insetInlineStart: m.pos + '%', '--carril': m.carril }" :title="tx(`${m.p.nombre}: ${relTxt(m.p)}`)">
          <span class="punto"></span>
          <span class="txt"><b>{{ tx(m.p.nombre) }}</b><small>{{ tx(offTxt(dias[m.p.paso])) }}</small></span>
        </div>
      </div>
      <div class="leyenda">
        <span v-for="n in datos.niveles" :key="n.nivel" :class="`n-${n.nivel}`"><i></i>{{ tx(n.nombre) }}</span>
      </div>
    </section>

    <!-- Pasos en el orden definido -->
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Steps in order') }}</h2><p>{{ t('The order and relations come from the rules; inherited values in grey, overrides highlighted.') }}</p></div></div>
      <ol class="pasos">
        <li v-for="(p, i) in pasos" :key="p.paso + p.modo" :class="[`n-${p.origen.nivel}`, { sobrescrito: p.previo }]">
          <span class="num">{{ i + 1 }}</span>
          <div class="cuerpo">
            <div class="titulo"><b>{{ tx(p.nombre) }}</b>
              <span v-if="p.hito" class="etiqueta" :title="tx(hitoTxt(p.hito))"><Icono nombre="reloj" :tam="11" />{{ t('Measured') }}</span>
              <span v-if="p.modo" class="etiqueta acento">{{ tx(MODOS.find((m) => m.valor === p.modo)?.texto) }}</span></div>
            <div class="sub">{{ tx(relTxt(p)) }}</div>
            <div v-if="p.historial?.length" class="sobre"><Icono nombre="historial" :tam="13" />
              <span v-for="h in p.historial" :key="h.origen.nivel" class="hist" :class="`n-${h.origen.nivel}`"><s>{{ tx(h.origen.nombre) }}: {{ tx(cortoTxt(h)) }}</s> →</span>
              <b class="hist" :class="`n-${p.origen.nivel}`">{{ tx(p.origen.nombre) }}: {{ tx(cortoTxt(p)) }}</b></div>
          </div>
          <div class="dia">{{ tx(offTxt(dias[p.paso])) }}</div>
          <span class="origen" :class="`n-${p.origen.nivel}`">{{ tx(p.origen.nombre) }}</span>
        </li>
      </ol>
      <p v-if="datos.quitados.length" class="ayuda">{{ t('Removed: {0}', [datos.quitados.map((q) => `${q.nombre} (${q.quitado_por.nombre})`).join(', ')]) }}</p>
    </section>
  </template>
</template>

<style scoped>
.selectores { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.selectores :deep(.sb) { min-width: 200px; }
.n-GLOBAL { --c: var(--tinta-3); }
.n-REGION { --c: #2f7dd3; }
.n-PAIS { --c: var(--ok); }
.n-PUERTO { --c: var(--acento); }
.niveles { list-style: none; margin: 0 0 14px; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; align-items: stretch; }
.niveles li { display: flex; flex-direction: column; padding: 8px 12px; border-radius: var(--radio); border: 1px solid var(--linea); border-inline-start: 4px solid var(--c); background: var(--superficie); min-width: 150px; }
.niveles li.vacio { opacity: 0.7; }
.niveles li + li::before { content: none; }
.nivel { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--c); font-weight: 700; }
.sub { font-size: 0.8rem; color: var(--tinta-3); }
.panel { margin-bottom: 14px; }
.linea { position: relative; height: calc(56px + var(--carriles) * 42px); margin: 10px 24px 6px; }
.eje { position: absolute; inset-inline: 0; top: 22px; height: 2px; background: var(--linea); }
.tick { position: absolute; top: 0; transform: translateX(-50%); font-size: 0.7rem; color: var(--tinta-3); }
.marca { position: absolute; top: 16px; transform: translateX(-50%); display: flex; flex-direction: column; align-items: center; }
.punto { width: 14px; height: 14px; border-radius: 50%; background: var(--c); border: 3px solid var(--superficie); box-shadow: 0 0 0 1px var(--c); }
.txt { margin-top: calc(6px + var(--carril) * 42px); display: flex; flex-direction: column; align-items: center; white-space: nowrap; font-size: 0.78rem; line-height: 1.2; }
.txt small { color: var(--tinta-3); }
.marca::after { content: ''; position: absolute; top: 14px; width: 1px; height: calc(6px + var(--carril) * 42px); background: color-mix(in srgb, var(--c) 50%, transparent); }
.leyenda { display: flex; flex-wrap: wrap; gap: 12px; font-size: 0.78rem; color: var(--tinta-2); margin-top: 6px; }
.leyenda i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: var(--c); margin-inline-end: 5px; vertical-align: -1px; }
.pasos { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.pasos li { display: grid; grid-template-columns: auto 1fr auto auto; gap: 10px; align-items: center; padding: 9px 12px; border: 1px solid var(--linea); border-inline-start: 4px solid var(--c); border-radius: var(--radio); background: var(--superficie); }
.pasos li.sobrescrito { background: color-mix(in srgb, var(--c) 7%, var(--superficie)); }
.num { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; background: var(--superficie-2); font-size: 0.78rem; font-weight: 700; }
.titulo { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.sobre { font-size: 0.78rem; color: var(--tinta-2); display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: center; margin-top: 2px; }
.hist { color: var(--c); }
.hist s { color: var(--tinta-3); }
.dia { font-variant-numeric: tabular-nums; font-size: 0.85rem; color: var(--tinta-2); white-space: nowrap; }
.origen { font-size: 0.75rem; font-weight: 650; color: var(--c); padding: 2px 8px; border-radius: 99px; background: color-mix(in srgb, var(--c) 12%, transparent); white-space: nowrap; }
@media (max-width: 640px) {
  .pasos li { grid-template-columns: auto 1fr; }
  .dia, .origen { grid-column: 2; justify-self: start; }
  .linea { margin-inline: 30px; }
}
</style>
