<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { fmtFechaHora, fmtNum } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'
import { puede } from '@/stores/sesion'
import { UNIDADES, textoModalidad } from '@/modulos/etiquetado/etiquetas.js'
import { buscarArticulos, buscarOrdenes } from '@/modulos/etiquetado/componentes/buscadores.js'

// Lotes de etiquetas generados: quién, cuándo, de qué OC, con qué diseños y
// versiones. Descargar vuelve a dibujar el lote con la versión y los valores
// originales: el archivo es el mismo aunque el diseño o los datos cambien.
const route = useRoute()
const tabla = ref(null)
const filtros = reactive({ desde: '', hasta: '', estado: '', oc_id: route.query.oc_id ? Number(route.query.oc_id) : '',
  articulo_id: route.query.articulo_id ? Number(route.query.articulo_id) : '' })
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)

const columnas = computed(() => [
  { clave: 'id', texto: t('Batch'), fija: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'creada_en', texto: t('Date'), prioridad: 1, ordenable: false, filtro: false },
  { clave: 'oc', texto: t('PO'), prioridad: 1, ordenable: false, filtro: false },
  { clave: 'versiones', texto: t('Designs and versions'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'total', texto: t('Labels'), num: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'formato', texto: t('Format'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'creada_por', texto: t('By'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'estado', texto: t('Status'), prioridad: 2, ordenable: false, filtro: false },
])
let ultima = null
async function consultar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/etiquetas/generaciones', { ...Object.fromEntries(Object.entries(filtros).filter(([, v]) => v !== '')),
      page: c.page, size: c.size })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function recargar() {
  if (tabla.value?.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}

const detalle = ref(null)
async function abrir(g) {
  try {
    detalle.value = await api.get(`/etiquetas/generaciones/${g.id}`)
  } catch (e) {
    errorApi(e)
  }
}
async function descargar(formato) {
  try {
    await api.descargar(`/etiquetas/generaciones/${detalle.value.id}/archivo`, `labels-${detalle.value.id}`, { formato })
  } catch (e) {
    errorApi(e)
  }
}
// Datos de otros usuarios: se vuelven a pedir solo cuando cambian (nucleo/cambios.js)
alCambiar(() => consultar(), ['/etiquetas/generaciones'])
</script>

<template>
  <TablaDatos ref="tabla" tabla="etiquetas_historial" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              fila-clicable :etiqueta="t('Generated labels')" :externos="{ ...filtros }" @consulta="consultar" @fila="abrir">
    <template #filtros>
      <label class="campo-linea">{{ t('From') }} <input v-model="filtros.desde" type="date" @change="recargar" /></label>
      <label class="campo-linea">{{ t('To') }} <input v-model="filtros.hasta" type="date" @change="recargar" /></label>
      <SelectBusqueda v-model="filtros.oc_id" :buscar="buscarOrdenes" :etiqueta="t('PO')" :vacio="t('Any PO')" @change="recargar" />
      <SelectBusqueda v-model="filtros.articulo_id" :buscar="buscarArticulos" :etiqueta="t('Item')" :vacio="t('Any item')" @change="recargar" />
      <Seleccion v-model="filtros.estado" :aria-label="t('Status')" @change="recargar">
        <option value="">{{ t('Any status') }}</option>
        <option value="GENERADA">{{ t('Generated') }}</option>
        <option value="PRUEBA">{{ t('Test (not approved)') }}</option>
      </Seleccion>
    </template>
    <template #celda-id="{ fila: g }"><strong class="codigo">#{{ g.id }}</strong><span class="sub">{{ tx(textoModalidad(g.modalidad)) }} · {{ tx(UNIDADES()[g.unidad] || g.unidad) }}</span></template>
    <template #celda-creada_en="{ fila: g }">{{ fmtFechaHora(g.creada_en) }}</template>
    <template #celda-oc="{ fila: g }"><router-link v-if="g.oc_id" :to="`/ordenes/${g.oc_id}`" class="enlace" @click.stop>{{ g.oc }}</router-link><span v-else class="apagado">—</span></template>
    <template #celda-versiones="{ fila: g }">{{ g.versiones.map((v) => `${v.plantilla} v${v.version}`).join(' · ') }}</template>
    <template #celda-total="{ fila: g }">{{ fmtNum(g.total) }}</template>
    <template #celda-estado="{ fila: g }"><EstadoBadge :estado="g.estado" tipo="lote" /></template>
    <template #vacio>{{ t('No labels generated yet. Generate them from a purchase order.') }}</template>
  </TablaDatos>

  <PanelLateral v-if="detalle" :titulo="t('Label batch #{0}', [detalle.id])" ancho="680px" @cerrar="detalle = null">
    <template #estado><EstadoBadge :estado="detalle.estado" tipo="lote" /></template>
    <dl class="datos-lote">
      <dt>{{ t('Date') }}</dt><dd>{{ fmtFechaHora(detalle.creada_en) }}</dd>
      <dt>{{ t('By') }}</dt><dd>{{ detalle.creada_por || '—' }}</dd>
      <dt>{{ t('PO') }}</dt><dd>{{ detalle.oc || '—' }}</dd>
      <dt>{{ t('Labels') }}</dt><dd>{{ fmtNum(detalle.total) }} · {{ detalle.formato }}</dd>
      <dt>{{ t('Fingerprint') }}</dt><dd><code :title="detalle.sha256">{{ (detalle.sha256 || '').slice(0, 16) }}…</code></dd>
    </dl>
    <p class="ayuda">{{ t('Each download draws the batch again with the original versions and values: it is the same file even if the design or the data changed later.') }}</p>
    <table class="tabla mt">
      <thead><tr><th>{{ t('Origin') }}</th><th class="num">{{ t('Labels') }}</th><th>{{ t('Design') }}</th><th>{{ t('Why') }}</th></tr></thead>
      <tbody>
        <tr v-for="it in detalle.items" :key="it.id">
          <td>{{ it.referencia }}<span v-if="it.familia" class="sub">{{ tx(it.familia) }}</span></td>
          <td class="num">{{ fmtNum(it.cantidad) }}</td>
          <td>{{ tx(it.plantilla) }} <span class="etiqueta ms-0">v{{ it.version }}</span></td>
          <td class="ayuda">{{ tx(it.motivo || '') }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="detalle.advertencias.length" class="nota mt"><Icono nombre="alerta" :tam="16" />
      <div>{{ t('Warnings accepted when generating:') }}<ul><li v-for="(a, i) in detalle.advertencias.slice(0, 10)" :key="i">{{ a.referencia }}: {{ tx(a.mensaje) }}</li></ul></div></div>
    <template v-if="puede('etiquetas.generar')" #pie>
      <button v-for="f in ['PDF', 'PNG', 'SVG', 'ZIP']" :key="f" type="button" class="btn" :class="{ 'btn-primario': f === detalle.formato }" @click="descargar(f)">
        <Icono nombre="descargar" :tam="15" />{{ f }}</button>
    </template>
  </PanelLateral>
</template>

<style scoped>
.campo-linea { display: inline-flex; align-items: center; gap: 6px; font-size: 0.86rem; color: var(--tinta-2); }
.datos-lote { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; margin: 0 0 12px; }
.datos-lote dt { color: var(--tinta-3); }
.datos-lote dd { margin: 0; }
</style>
