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
import PanelLateral from '@/componentes/PanelLateral.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'

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
function cifra(i) {
  const v = i.valor
  if (v === null || v === undefined) return '—'
  const f = def(i.clave).formato
  if (f === 'moneda') return fmtMoneda(v, d.value.moneda_base)
  if (f === 'porcentaje') return `${fmtNum(v)}%`
  if (f === 'dias') return t('{0} days', [fmtNum(v)])
  return fmtNum(v)
}
// Variación frente al período anterior: el tono dice si es buena o mala según el indicador
function variacion(i) {
  if (i.anterior === null || i.anterior === undefined || i.valor === null || i.valor === undefined) return null
  const dif = i.valor - i.anterior
  const pct = i.anterior ? Math.round((dif * 100) / Math.abs(i.anterior)) : null
  const mejor = def(i.clave).mejor
  const tono = !dif || !mejor ? '' : (dif > 0) === (mejor === 'alto') ? 'ok' : 'aviso'
  const texto = !dif ? t('No change') : pct === null ? `${dif > 0 ? '+' : ''}${fmtNum(dif)}` : `${dif > 0 ? '▲' : '▼'} ${fmtNum(Math.abs(pct))}%`
  return { texto, tono }
}
function alternarExplicacion(clave) {
  const s = new Set(abiertos.value)
  if (s.has(clave)) s.delete(clave)
  else s.add(clave)
  abiertos.value = s
}
const periodoTxt = (i) => (def(i.clave).momento === 'hoy' ? t('Current state, today')
  : t('From {0} to {1}; compared with {2} to {3}', [fmtFecha(d.value.periodo.desde), fmtFecha(d.value.periodo.hasta),
    fmtFecha(d.value.periodo.anterior_desde), fmtFecha(d.value.periodo.anterior_hasta)]))
const ORIGEN = { usuario: t('Your selection'), rol: t('Selection of your role'), sistema: t('All the indicators of your role') }

// ---- Elegir y ordenar los indicadores ---------------------------------------------
const panel = ref(null) // { elegidos: [...], rol: '' }
const roles = ref([])
const ordenados = computed(() => {
  if (!panel.value) return []
  const resto = d.value.catalogo.map((c) => c.clave).filter((k) => !panel.value.elegidos.includes(k))
  return [...panel.value.elegidos, ...resto].map((k) => ({ ...def(k), elegido: panel.value.elegidos.includes(k) }))
})
async function abrirPanel() {
  panel.value = { elegidos: [...d.value.elegidos], rol: '' }
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
      <p>{{ t('The key figures of each module, with how they are calculated, the period they cover and where the data comes from. Each person chooses which ones to see.') }}</p>
    </div>
    <div class="acciones">
      <div class="segmentos" role="group" :aria-label="t('Period')">
        <button v-for="[v, txt] in PERIODOS" :key="v" type="button" class="segmento" :aria-pressed="dias === v" @click="dias = v">{{ tx(txt) }}</button>
      </div>
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
    <p class="ayuda">{{ t('Showing: {0}.', [ORIGEN[d.origen]]) }}</p>
    <div v-if="d.indicadores.length" class="rejilla-indicadores">
      <article v-for="i in d.indicadores" :key="i.clave" class="panel kpi-tarjeta">
        <header class="kpi-cabeza">
          <h2>{{ tx(def(i.clave).titulo) }}</h2>
          <button type="button" class="btn-icono" :aria-expanded="abiertos.has(i.clave)" :aria-label="t('How is it calculated?')" :title="t('How is it calculated?')"
                  @click="alternarExplicacion(i.clave)"><Icono nombre="info" :tam="16" /></button>
        </header>
        <div class="kpi-valor">{{ cifra(i) }}</div>
        <div class="kpi-pie">
          <span v-if="variacion(i)" class="etiqueta ms-0" :class="variacion(i).tono">{{ tx(variacion(i).texto) }}</span>
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

  <PanelLateral v-if="panel" :titulo="t('Choose indicators')" ancho="560px" @cerrar="panel = null">
    <p class="ayuda">{{ t('Check the indicators you want to see and order them with the arrows. Your choice is only for you.') }}</p>
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
  </PanelLateral>
</template>

<style scoped>
.rejilla-indicadores { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--e-4); margin-top: var(--e-3); align-items: start; }
.kpi-tarjeta { margin: 0; display: flex; flex-direction: column; gap: var(--e-2); }
.kpi-cabeza { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--e-2); }
.kpi-cabeza h2 { margin: 0; font-size: var(--t-sm); font-weight: 650; color: var(--tinta-2); }
.kpi-valor { font-size: var(--t-2xl); font-weight: 750; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
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
.panel-rol h3 { margin: 8px 0 4px; font-size: var(--t-sm); }
.rol-sel { min-width: 220px; flex: 1; }
</style>
