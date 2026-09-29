<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { siguienteOrden } from '../composables/useTabla'
import { sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { COMERCIAL, LIBERACION, diasTxt, fmtFecha, fmtNum } from '../utils'
import GraficoColumnas from './GraficoColumnas.vue'
import Kpi from './Kpi.vue'
import Paginacion from './Paginacion.vue'
import ThOrden from './ThOrden.vue'

// Tablero de órdenes de compra: liberaciones (comercial y logística), cuánto
// falta por facturar, qué va en contenedor, en camino y recibido.
const props = defineProps({ filtros: { type: Object, required: true } })
const emit = defineEmits(['opciones', 'filtrar'])
const datos = ref({ items: [], total: 0, kpis: {}, estados: [] })
const cargando = ref(true)
const tabla = reactive({ orden: 'fecha_xf:asc', page: 1, size: 25 })
const TONO = {
  SIN_COMERCIAL: 'aviso', SIN_LOGISTICA: 'aviso', POR_FACTURAR: 'neutro', PARCIAL: 'info', FACTURADA: 'acento',
  EN_CAMINO: 'info', RECIBIDA: 'ok',
}
const RIESGOS = { ATRASO: ['Llega tarde', 'error'], JUSTO: ['Justo', 'aviso'], A_TIEMPO: ['A tiempo', 'ok'] }
// Tramos de la barra de avance: del pedido a lo recibido (un solo tono, de claro a oscuro)
const TRAMOS = [
  ['por_facturar', 'Por facturar', 'var(--tramo-1)'], ['facturado', 'Facturado', 'var(--tramo-2)'],
  ['en_contenedor', 'En contenedor', 'var(--tramo-3)'], ['en_camino', 'En camino', 'var(--tramo-4)'],
  ['recibido', 'Recibido', 'var(--tramo-5)'],
]
const nombreEstado = computed(() => Object.fromEntries(datos.value.estados.map((e) => [e.clave, e.nombre])))
const grafica = computed(() => datos.value.estados.map((e) => ({ etiqueta: e.nombre.split(' (')[0].replace('Sin liberación', 'Sin lib.'), valor: e.total, detalle: e.nombre })))

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/ordenes', { ...props.filtros, ...tabla, proveedor_id: sesion.proveedorId || undefined })
    emit('opciones', datos.value.opciones)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function ordenar(campo) {
  tabla.orden = siguienteOrden(tabla.orden, campo)
  tabla.page = 1
  cargar()
}
watch(() => [props.filtros, sesion.proveedorId], () => { tabla.page = 1; cargar() }, { deep: true })
onMounted(cargar)
</script>

<template>
  <section class="kpis" style="margin-bottom: 16px">
    <Kpi titulo="Órdenes de compra" :valor="datos.kpis.ocs" icono="ordenes" :detalle="`${fmtNum(datos.kpis.avance || 0, 1)}% facturado`" @abrir="emit('filtrar', {})" />
    <Kpi titulo="Liberadas" :valor="datos.kpis.liberadas" icono="check" tono="exito" detalle="comercial C y logística 300/301" @abrir="emit('filtrar', {})" />
    <Kpi titulo="Sin liberar" :valor="datos.kpis.sin_liberar" icono="candado" :tono="datos.kpis.sin_liberar ? 'alerta' : 'exito'"
         detalle="comercial P o logística 304" @abrir="emit('filtrar', { estado: 'SIN_COMERCIAL' })" />
    <Kpi titulo="XF vencida sin facturar" :valor="datos.kpis.xf_vencida" icono="reloj" :tono="datos.kpis.xf_vencida ? 'alerta' : 'exito'"
         detalle="ya pasó la fecha XF" @abrir="emit('filtrar', { xf_vencida: '1' })" />
    <Kpi titulo="Llegan tarde a tienda" :valor="datos.kpis.atraso" icono="alerta" :tono="datos.kpis.atraso ? 'alerta' : 'exito'"
         detalle="por ETA o sin embarque" @abrir="emit('filtrar', { riesgo: 'ATRASO' })" />
  </section>

  <section class="panel" style="margin-bottom: 16px">
    <div class="panel-cabeza">
      <div><h2>OCs por estado</h2><p>De la liberación a la recepción. Clic en un estado para filtrar la tabla.</p></div>
    </div>
    <GraficoColumnas :datos="grafica" titulo="Órdenes de compra por estado" />
    <div class="chips" style="margin: 10px 0 0">
      <button v-for="e in datos.estados" :key="e.clave" type="button" class="pildora" :aria-pressed="filtros.estado === e.clave"
              @click="emit('filtrar', { estado: filtros.estado === e.clave ? '' : e.clave })">
        {{ e.nombre }}<span class="cuenta">{{ e.total }}</span>
      </button>
    </div>
  </section>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <ThOrden campo="oc" :orden="tabla.orden" @ordenar="ordenar">Orden de compra</ThOrden>
          <ThOrden campo="centro" :orden="tabla.orden" @ordenar="ordenar">Sociedad · centro</ThOrden>
          <th>Liberaciones</th>
          <ThOrden campo="estado" :orden="tabla.orden" @ordenar="ordenar">Estado</ThOrden>
          <ThOrden campo="avance" :orden="tabla.orden" @ordenar="ordenar">Avance</ThOrden>
          <ThOrden campo="por_facturar" :orden="tabla.orden" num @ordenar="ordenar">Por facturar</ThOrden>
          <ThOrden campo="fecha_xf" :orden="tabla.orden" @ordenar="ordenar">XF</ThOrden>
          <ThOrden campo="fecha_tienda" :orden="tabla.orden" @ordenar="ordenar">En tienda</ThOrden>
          <ThOrden campo="holgura" :orden="tabla.orden" @ordenar="ordenar">Vs. tienda</ThOrden>
          <th>Embarques</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td colspan="10" class="vacio">Cargando…</td></tr>
        <tr v-else-if="!datos.items.length"><td colspan="10" class="vacio">No hay órdenes de compra con esos filtros.</td></tr>
        <tr v-for="o in datos.items" :key="o.oc_id">
          <td>
            <router-link :to="{ path: '/ordenes', query: { q: o.oc, solo_disponible: '0' } }" class="codigo fuerte">{{ o.oc }}</router-link>
            <span class="sub">{{ o.proveedor }}<template v-if="o.marcas.length"> · {{ o.marcas.join(', ') }}</template></span>
          </td>
          <td class="codigo">{{ o.sociedad }} · {{ o.centro }}<span class="sub">destino {{ o.centro_destino || '—' }}</span></td>
          <td>
            <span class="etiqueta" :class="COMERCIAL[o.liberacion_comercial]?.[1]" style="margin-left: 0" :title="COMERCIAL[o.liberacion_comercial]?.[2]">{{ COMERCIAL[o.liberacion_comercial]?.[0] }}</span>
            <span class="etiqueta" :class="LIBERACION[o.liberacion_logistica]?.[1]" :title="LIBERACION[o.liberacion_logistica]?.[2]">{{ LIBERACION[o.liberacion_logistica]?.[0] }}</span>
          </td>
          <td><span class="etiqueta" :class="TONO[o.estado]" style="margin-left: 0">{{ nombreEstado[o.estado] }}</span></td>
          <td style="min-width: 170px">
            <div class="apilada" role="img" :aria-label="TRAMOS.map(([k, t]) => `${t}: ${o.cantidades[k]}`).join(', ')">
              <span v-for="[k, t, c] in TRAMOS.filter(([k]) => o.cantidades[k])" :key="k"
                    :style="{ width: `${(o.cantidades[k] * 100) / o.total}%`, background: c }" :title="`${t}: ${fmtNum(o.cantidades[k])}`"></span>
            </div>
            <span class="sub">{{ fmtNum(o.avance, 0) }}% facturado · {{ fmtNum(o.total) }} {{ o.unidades.join('/') }}</span>
          </td>
          <td class="num">{{ fmtNum(o.por_facturar) }}</td>
          <td>{{ fmtFecha(o.fecha_xf) }}<span v-if="o.xf_vencida" class="sub" style="color: var(--error)">vencida</span></td>
          <td>{{ fmtFecha(o.fecha_tienda) }}<span class="sub">{{ diasTxt(o.dias_tienda) }}</span></td>
          <td>
            <span v-if="o.riesgo" class="etiqueta" :class="RIESGOS[o.riesgo][1]" style="margin-left: 0">{{ RIESGOS[o.riesgo][0] }}</span>
            <span v-if="o.holgura !== null" class="sub">{{ o.holgura < 0 ? `${-o.holgura} d tarde` : `${o.holgura} d de margen` }}</span>
          </td>
          <td class="codigo">{{ o.embarques.join(', ') || '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="tabla.page" :size="tabla.size" :total="datos.total" @cambiar="(p) => { tabla.page = p; cargar() }" @tamano="(t) => (tabla.size = t)" />
  <div class="leyenda-etapas">
    <span v-for="[k, t, c] in TRAMOS" :key="k"><i class="punto" :style="{ background: c }"></i>{{ t }}</span>
  </div>
</template>
