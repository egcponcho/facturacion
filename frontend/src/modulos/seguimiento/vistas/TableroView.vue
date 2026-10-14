<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import { fmtFecha, fmtMoneda, fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import Tendencia from '@/componentes/Tendencia.vue'
import Segmentos from '@/componentes/Segmentos.vue'

// Tablero de un módulo: los indicadores que la persona eligió (o los de su
// rol), cada uno con su fórmula, su período y su fuente. Los números los
// calcula el servidor con el alcance de datos del usuario.
const props = defineProps({ modulo: { type: String, default: '' } })
const route = useRoute()
const router = useRouter()
const d = ref(null)
const modulos = ref([])
const dias = ref([7, 30, 90, 365].includes(Number(route.query.dias)) ? Number(route.query.dias) : 30)
const cargando = ref(false)
const abiertos = ref(new Set()) // indicadores con la explicación a la vista
const PERIODOS = [[7, t('7 days')], [30, t('30 days')], [90, t('90 days')], [365, t('12 months')]]

async function cargar() {
  if (!props.modulo) {
    try {
      modulos.value = await api.get('/tableros')
      if (modulos.value.length) router.replace({ path: `/tableros/${modulos.value[0].clave}`, query: route.query })
    } catch (e) {
      errorApi(e)
    }
    return
  }
  cargando.value = true
  try {
    d.value = await api.get(`/tableros/${props.modulo}`, { dias: dias.value })
    modulos.value = d.value.modulos
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)
watch(() => props.modulo, cargar)
watch(dias, (v) => {
  router.replace({ query: { ...route.query, dias: v } })
  cargar()
})

const def = (clave) => d.value?.catalogo.find((c) => c.clave === clave) || {}
function cifra(i, v = i.valor) {
  if (v === null || v === undefined) return '—'
  const f = def(i.clave).formato
  const dec = Number.isInteger(Number(v)) ? 0 : 1
  if (f === 'moneda') return fmtMoneda(v, i.moneda || d.value.moneda_base)
  if (f === 'porcentaje') return `${fmtNum(v, dec)}%`
  if (f === 'dias') return t('{0} days', [fmtNum(v, dec)])
  return fmtNum(v)
}
// Base de un porcentaje o promedio: «n de m»
const baseTxt = (i) => (i.base && i.base.m ? (i.base.n === i.base.m ? t('{0} records', [fmtNum(i.base.m)]) : t('{0} of {1}', [fmtNum(i.base.n), fmtNum(i.base.m)])) : '')
// Variación frente al período anterior. Los porcentajes cambian en puntos
// (66.7 % → 100 % es +33.3 pp, no +50 %); el tono dice si es buena o mala.
function variacion(i) {
  if (i.anterior === null || i.anterior === undefined || i.valor === null || i.valor === undefined) return null
  const dif = i.valor - i.anterior
  const mejor = def(i.clave).mejor
  const tono = !dif || !mejor ? '' : (dif > 0) === (mejor === 'alto') ? 'ok' : 'aviso'
  if (!dif) return { texto: t('No change'), tono }
  const signo = dif > 0 ? '▲' : '▼'
  if (def(i.clave).formato === 'porcentaje') return { texto: t('{0} {1} pp', [signo, fmtNum(Math.abs(dif), 1)]), tono }
  const pct = i.anterior ? Math.round((dif * 100) / Math.abs(i.anterior)) : null
  return { texto: pct === null ? `${dif > 0 ? '+' : ''}${fmtNum(dif)}` : `${signo} ${fmtNum(Math.abs(pct))}%`, tono }
}
// Frente a la meta de la empresa (si tiene): cumple u no cumple
function frenteMeta(i) {
  if (i.meta === null || i.meta === undefined || i.valor === null || i.valor === undefined) return null
  const mejor = def(i.clave).mejor || 'alto'
  const cumple = mejor === 'bajo' ? i.valor <= i.meta : i.valor >= i.meta
  return { texto: t('Target {0}', [cifra(i, i.meta)]), tono: cumple ? 'ok' : 'aviso' }
}
const serie = (i) => i.serie.map((s) => ({ etiqueta: `${fmtFecha(s.desde)} – ${fmtFecha(s.hasta)}`, valor: s.valor }))
const ultimo = (i) => [...(i.serie || [])].reverse().find((s) => s.valor !== null && s.valor !== undefined)
function alternarExplicacion(clave) {
  const s = new Set(abiertos.value)
  if (s.has(clave)) s.delete(clave)
  else s.add(clave)
  abiertos.value = s
}
const periodoTxt = (i) => (def(i.clave).momento === 'hoy' ? t('Current state, today')
  : t('From {0} to {1}; compared with {2} to {3}', [fmtFecha(d.value.periodo.desde), fmtFecha(d.value.periodo.hasta),
    fmtFecha(d.value.periodo.anterior_desde), fmtFecha(d.value.periodo.anterior_hasta)]))
const ORIGEN = { usuario: t('Your selection'), rol: t('Selection of your role'), sistema: t('Default selection') }

// ---- Elegir y ordenar los indicadores ---------------------------------------------
const panel = ref(null) // { elegidos: [...], rol: '' }
const roles = ref([])
const ordenados = computed(() => {
  if (!panel.value) return []
  const resto = d.value.catalogo.map((c) => c.clave).filter((k) => !panel.value.elegidos.includes(k))
  return [...panel.value.elegidos, ...resto].map((k) => ({ ...def(k), elegido: panel.value.elegidos.includes(k) }))
})
async function abrirPanel() {
  panel.value = { elegidos: [...d.value.elegidos], rol: '',
    metas: Object.fromEntries(d.value.catalogo.map((c) => [c.clave, d.value.indicadores.find((i) => i.clave === c.clave)?.meta ?? ''])) }
  if (puede('admin') && !roles.value.length) {
    try {
      roles.value = (await api.get('/roles')).roles.filter((r) => r.activo).map((r) => ({ valor: r.id, texto: r.nombre }))
    } catch (e) {
      errorApi(e)
    }
  }
}
function alternar(clave) {
  const e = panel.value.elegidos
  panel.value.elegidos = e.includes(clave) ? e.filter((k) => k !== clave) : [...e, clave]
}
function mover(clave, paso) {
  const e = [...panel.value.elegidos]
  const i = e.indexOf(clave)
  const j = i + paso
  if (i < 0 || j < 0 || j >= e.length) return
  ;[e[i], e[j]] = [e[j], e[i]]
  panel.value.elegidos = e
}
async function guardarMetas() {
  try {
    const metas = Object.fromEntries(Object.entries(panel.value.metas).map(([k, v]) => [k, v === '' || v === null ? null : Number(v)]))
    await api.put('/tableros/metas', metas)
    avisar(t('Targets saved for the company.'))
    panel.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
async function guardar(destino) {
  try {
    if (destino === 'rol') {
      await api.put(`/tableros/${props.modulo}/rol/${panel.value.rol}`, { claves: panel.value.elegidos })
      avisar(t('Indicators saved for the role.'))
    } else {
      await api.put(`/tableros/${props.modulo}/propios`, { claves: destino === 'quitar' ? null : panel.value.elegidos })
      avisar(destino === 'quitar' ? t('You see the indicators of your role again.') : t('Your indicators were saved.'))
    }
    panel.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Indicators') }}</h1>
      <p>{{ t('How the operation is doing: each figure against the previous period, with its trend.') }}</p>
    </div>
    <div class="acciones">
      <Segmentos v-model="dias" :opciones="PERIODOS" :etiqueta="t('Period')" />
      <button v-if="d" type="button" class="btn" @click="abrirPanel"><Icono nombre="engrane" :tam="15" />{{ t('Choose indicators') }}</button>
    </div>
  </div>

  <nav v-if="modulos.length" class="pestanas" role="tablist" :aria-label="t('Modules')">
    <router-link v-for="m in modulos" :key="m.clave" :to="{ path: `/tableros/${m.clave}`, query: { dias } }" class="pestana" role="tab"
                 :aria-selected="m.clave === props.modulo">{{ tx(m.titulo) }}</router-link>
  </nav>

  <EstadoVacio v-if="!modulos.length && !cargando" icono="grafica" :titulo="t('No indicators for your role')"
               :texto="t('Indicators appear for the modules your role can see (orders, invoices, shipments, products).')" />

  <template v-if="d">
    <div v-if="d.indicadores.length" class="rejilla-indicadores">
      <article v-for="i in d.indicadores" :key="i.clave" class="panel kpi-tarjeta">
        <header class="kpi-cabeza">
          <h2>{{ tx(def(i.clave).titulo) }}</h2>
          <button type="button" class="btn-icono" :aria-expanded="abiertos.has(i.clave)" :aria-label="t('How is it calculated?')" :title="t('How is it calculated?')"
                  @click="alternarExplicacion(i.clave)"><Icono nombre="info" :tam="16" /></button>
        </header>
        <div class="kpi-cifra">
          <span class="kpi-valor">{{ cifra(i) }}</span>
          <span v-if="variacion(i)" class="etiqueta ms-0" :class="variacion(i).tono" :title="t('Previous period: {0}', [cifra(i, i.anterior)])">{{ tx(variacion(i).texto) }}</span>
          <span v-if="frenteMeta(i)" class="etiqueta ms-0" :class="frenteMeta(i).tono">{{ tx(frenteMeta(i).texto) }}</span>
        </div>
        <p v-if="i.otras?.length" class="kpi-otras" :title="t('Amounts in other currencies are shown apart, never added')">+ {{ tx(i.otras.map((o) => fmtMoneda(o.valor, o.moneda)).join(' · ')) }}</p>
        <p v-if="baseTxt(i) || i.mediana != null" class="kpi-ultimo">{{ tx([baseTxt(i), i.mediana != null ? t('median {0}', [cifra(i, i.mediana)]) : ''].filter(Boolean).join(' · ')) }}</p>
        <p v-if="i.valor === null && ultimo(i)" class="kpi-ultimo">{{ t('No data in this period · last: {0} ({1})', [cifra(i, ultimo(i).valor), fmtFecha(ultimo(i).hasta)]) }}</p>
        <Tendencia v-if="i.serie" :serie="serie(i)" :formato="(v) => cifra(i, v)" :tono="variacion(i)?.tono" />
        <div v-else class="kpi-hoy"><Icono nombre="reloj" :tam="13" />{{ t('Current state, today') }}</div>
        <ul v-if="i.desglose?.length" class="kpi-desglose">
          <li v-for="x in i.desglose" :key="x.etiqueta"><span>{{ tx(x.etiqueta) }}</span><b>{{ cifra(i, x.valor) }}</b>
            <small v-if="x.base?.m">{{ x.base.n === x.base.m ? fmtNum(x.base.m) : t('{0} of {1}', [fmtNum(x.base.n), fmtNum(x.base.m)]) }}</small></li>
        </ul>
        <div class="kpi-pie">
          <span class="ayuda">{{ tx(def(i.clave).momento === 'hoy' ? t('Today') : t('Last {0} days', [d.periodo.dias])) }}</span>
          <router-link v-if="i.ruta" :to="i.ruta" class="separar enlace-kpi">{{ t('See detail') }}<Icono nombre="derecha" :tam="13" /></router-link>
        </div>
        <dl v-if="abiertos.has(i.clave)" class="kpi-explicacion">
          <dt>{{ t('Formula') }}</dt><dd>{{ tx(def(i.clave).formula) }}</dd>
          <dt>{{ t('Period') }}</dt><dd>{{ tx(periodoTxt(i)) }}</dd>
          <dt>{{ t('Source') }}</dt><dd>{{ tx(def(i.clave).fuente) }}</dd>
          <template v-if="i.valor === null"><dt>{{ t('No value') }}</dt><dd>{{ t('There is no data in the period to calculate it.') }}</dd></template>
        </dl>
      </article>
    </div>
    <EstadoVacio v-else icono="grafica" :titulo="t('No indicators chosen')" :texto="t('Choose the indicators you want to follow in this module.')">
      <button type="button" class="btn btn-primario" @click="abrirPanel">{{ t('Choose indicators') }}</button>
    </EstadoVacio>
  </template>

  <Modal v-if="panel" :titulo="t('Choose indicators')" ancho="560px" @cerrar="panel = null">
    <p class="ayuda">{{ t('Showing: {0}.', [ORIGEN[d.origen]]) }} {{ t('Check the indicators you want to see and order them with the arrows. Your choice is only for you.') }}</p>
    <ul class="lista-kpis">
      <li v-for="c in ordenados" :key="c.clave">
        <label class="check"><input type="checkbox" :checked="c.elegido" @change="alternar(c.clave)" />
          <span><b>{{ tx(c.titulo) }}</b><small class="sub">{{ tx(c.formula) }}</small></span></label>
        <span v-if="c.elegido" class="mover">
          <button type="button" class="btn-icono" :aria-label="t('Move {0} up', [tx(c.titulo)])" @click="mover(c.clave, -1)"><Icono nombre="arriba" :tam="14" /></button>
          <button type="button" class="btn-icono" :aria-label="t('Move {0} down', [tx(c.titulo)])" @click="mover(c.clave, 1)"><Icono nombre="abajo" :tam="14" /></button>
        </span>
      </li>
    </ul>
    <section v-if="puede('admin')" class="panel-rol">
      <h3>{{ t('Company targets') }}</h3>
      <p class="ayuda">{{ t('Each card compares its value with the target. The formula does not change. Leave it empty for no target.') }}</p>
      <ul class="lista-metas">
        <li v-for="c in d.catalogo" :key="c.clave">
          <span>{{ tx(c.titulo) }}</span>
          <input v-model="panel.metas[c.clave]" class="entrada ancho-s" type="number" min="0" :max="c.formato === 'porcentaje' ? 100 : undefined" step="any"
                 :aria-label="t('Target for {0}', [tx(c.titulo)])" />
          <small class="ayuda">{{ tx(c.formato === 'porcentaje' ? '%' : c.formato === 'dias' ? t('days') : c.formato === 'moneda' ? d.moneda_base : '') }}</small>
        </li>
      </ul>
      <button type="button" class="btn btn-chico mt-chico" @click="guardarMetas">{{ t('Save targets') }}</button>
    </section>
    <section v-if="puede('admin')" class="panel-rol">
      <h3>{{ t('Default for a role') }}</h3>
      <p class="ayuda">{{ t('People of that role who have not chosen their own indicators see this selection.') }}</p>
      <div class="fila-flex">
        <SelectBusqueda v-model="panel.rol" :opciones="roles" :etiqueta="t('Role')" :placeholder="t('Choose a role…')" :prefijo="false" class="rol-sel" />
        <button type="button" class="btn" :disabled="!panel.rol" @click="guardar('rol')">{{ t('Save for the role') }}</button>
      </div>
    </section>
    <template #pie>
      <button v-if="d.origen === 'usuario'" type="button" class="btn btn-fantasma" @click="guardar('quitar')">{{ t('Use the ones of my role') }}</button>
      <button type="button" class="btn" @click="panel = null">{{ t('Cancel') }}</button>
      <button type="button" class="btn btn-primario" @click="guardar('propios')"><Icono nombre="check" :tam="15" />{{ t('Save for me') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.rejilla-indicadores { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: var(--e-4); margin-top: var(--e-3); align-items: start; }
.kpi-tarjeta { margin: 0; display: flex; flex-direction: column; gap: 10px; padding: 16px 18px; }
.kpi-cifra { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 10px; }
.kpi-otras { margin: -6px 0 0; font-size: 0.8rem; font-weight: 600; color: var(--tinta-2); }
.kpi-desglose { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; font-size: 0.8rem; }
.kpi-desglose li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px; align-items: baseline; }
.kpi-desglose span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--tinta-2); }
.kpi-desglose b { font-variant-numeric: tabular-nums; }
.kpi-desglose small { color: var(--tinta-3); }
.kpi-ultimo { margin: -6px 0 0; font-size: 0.78rem; color: var(--tinta-3); }
.kpi-hoy { height: 44px; display: flex; align-items: flex-end; gap: 6px; padding-bottom: 6px; font-size: 0.8rem; color: var(--tinta-3); border-bottom: 1px dashed var(--linea); }
.kpi-cabeza { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--e-2); }
.kpi-cabeza h2 { margin: 0; font-size: var(--t-sm); font-weight: 650; color: var(--tinta-2); }
.kpi-valor { font-size: var(--t-xl); font-weight: 750; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.kpi-pie { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 10px; }
.enlace-kpi { display: inline-flex; align-items: center; gap: 2px; font-size: var(--t-sm); }
.kpi-explicacion { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; margin: var(--e-2) 0 0; padding-top: var(--e-2);
  border-top: 1px solid var(--linea-suave); font-size: 0.84rem; }
.kpi-explicacion dt { color: var(--tinta-3); }
.kpi-explicacion dd { margin: 0; }
.lista-kpis { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.lista-kpis li { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--linea-suave); }
.lista-kpis .check { align-items: flex-start; }
.mover { display: inline-flex; flex: none; }
.lista-metas { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.lista-metas li { display: grid; grid-template-columns: minmax(0, 1fr) 110px 40px; gap: 8px; align-items: center; font-size: 0.86rem; }
.panel-rol h3 { margin: 8px 0 4px; font-size: var(--t-sm); }
.rol-sel { min-width: 220px; flex: 1; }
</style>
