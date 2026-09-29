<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { fmtFecha, fmtNum, porUnidadTxt } from '../utils'
import EstadoBadge from './EstadoBadge.vue'
import ExplosionPrepack from './ExplosionPrepack.vue'
import GraficoColumnas from './GraficoColumnas.vue'
import Icono from './Icono.vue'
import Kpi from './Kpi.vue'
import Paginacion from './Paginacion.vue'
import ThOrden from './ThOrden.vue'

// Tablero de contenedores y documentos de transporte (BL/AWB). Cada
// contenedor se abre para ver todo lo que lleva, agrupado por OC.
const props = defineProps({ filtros: { type: Object, required: true } })
const emit = defineEmits(['opciones', 'filtrar'])
const datos = ref({ items: [], total: 0, kpis: {}, por_estado: [], llegadas: [] })
const cargando = ref(true)
const tabla = reactive({ orden: '', page: 1, size: 25 })
const abiertos = reactive({})
const explosion = ref(null)
const RIESGOS = { ATRASO: ['Llega tarde', 'error'], JUSTO: ['Justo', 'aviso'], A_TIEMPO: ['A tiempo', 'ok'] }

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/contenedores', {
      ...props.filtros, ...tabla, proveedor_id: sesion.proveedorId || undefined,
    })
    emit('opciones', datos.value.opciones)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
async function alternar(c) {
  const k = `${c.embarque_id}|${c.contenedor}`
  if (abiertos[k]) {
    delete abiertos[k]
    return
  }
  try {
    abiertos[k] = await api.get(`/seguimiento/contenedores/${c.embarque_id}/explosion`,
      { contenedor: c.contenedor, proveedor_id: sesion.proveedorId || undefined })
  } catch (e) {
    errorApi(e)
  }
}
function ordenar(campo) {
  tabla.orden = siguienteOrden(tabla.orden, campo)
  tabla.page = 1
  cargar()
}
const llegadas = computed(() => datos.value.llegadas.map((s, i) => ({
  etiqueta: i === 0 ? 'Esta sem.' : fmtFecha(s.desde).slice(0, 5),
  valor: s.contenedores,
  detalle: `${fmtFecha(s.desde)} – ${fmtFecha(s.hasta)}`,
})))
const estados = computed(() => datos.value.por_estado.map((e) => ({ etiqueta: e.nombre, valor: e.total })))

watch(() => [props.filtros, sesion.proveedorId], () => { tabla.page = 1; cargar() }, { deep: true })
onMounted(cargar)
</script>

<template>
  <section class="kpis" style="margin-bottom: 16px">
    <Kpi titulo="Contenedores" :valor="datos.kpis.contenedores" icono="contenedor"
         :detalle="`${fmtNum(datos.kpis.documentos || 0)} documentos de transporte`" @abrir="emit('filtrar', {})" />
    <Kpi titulo="En tránsito" :valor="datos.kpis.en_camino" icono="barco" detalle="ya zarparon" @abrir="emit('filtrar', { estado: 'EN_TRANSITO' })" />
    <Kpi titulo="Llegan en 7 días" :valor="datos.kpis.llegan_7_dias" icono="reloj" detalle="por ETA" @abrir="emit('filtrar', {})" />
    <Kpi titulo="Llegan tarde a tienda" :valor="datos.kpis.atrasados" icono="alerta" :tono="datos.kpis.atrasados ? 'alerta' : 'exito'"
         detalle="ETA después de la fecha en tienda" @abrir="emit('filtrar', { riesgo: 'ATRASO' })" />
  </section>
  <p class="ayuda" style="margin: -6px 0 14px">Mercancía en contenedores: <b>{{ porUnidadTxt(datos.kpis.por_unidad, null) }}</b></p>

  <div class="dos-columnas" style="margin-bottom: 16px">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>Llegadas por semana</h2><p>Contenedores que aún no arriban, por semana de su ETA.</p></div></div>
      <GraficoColumnas :datos="llegadas" titulo="Contenedores por semana de llegada" />
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>Contenedores por estado</h2><p>Según los filtros; usa el filtro de estado para ver solo uno.</p></div></div>
      <GraficoColumnas :datos="estados" titulo="Contenedores por estado del embarque" />
    </section>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <th><span class="oculto-visual">Abrir</span></th>
          <ThOrden campo="contenedor" :orden="tabla.orden" @ordenar="ordenar">Contenedor</ThOrden>
          <ThOrden campo="documento" :orden="tabla.orden" @ordenar="ordenar">BL / AWB</ThOrden>
          <ThOrden campo="estado" :orden="tabla.orden" @ordenar="ordenar">Estado</ThOrden>
          <th>Ruta</th>
          <ThOrden campo="etd" :orden="tabla.orden" @ordenar="ordenar">Salida</ThOrden>
          <ThOrden campo="eta" :orden="tabla.orden" @ordenar="ordenar">Llegada</ThOrden>
          <ThOrden campo="holgura" :orden="tabla.orden" @ordenar="ordenar">Vs. tienda</ThOrden>
          <th>Marcas</th>
          <ThOrden campo="ocs" :orden="tabla.orden" num @ordenar="ordenar">OCs</ThOrden>
          <th class="num">Contenido</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td colspan="11" class="vacio">Cargando…</td></tr>
        <tr v-else-if="!datos.items.length"><td colspan="11" class="vacio">No hay contenedores con esos filtros.</td></tr>
        <template v-for="c in datos.items" :key="`${c.embarque_id}|${c.contenedor}`">
          <tr class="clicable" @click="alternar(c)">
            <td>
              <button type="button" class="btn-icono" :aria-expanded="!!abiertos[`${c.embarque_id}|${c.contenedor}`]" :aria-label="`Ver lo que lleva ${c.contenedor}`">
                <Icono :nombre="abiertos[`${c.embarque_id}|${c.contenedor}`] ? 'abajo' : 'derecha'" :tam="16" />
              </button>
            </td>
            <td>
              <b class="codigo">{{ c.contenedor }}</b>
              <span class="sub">
                <router-link v-if="esInterno()" :to="`/transporte/embarques/${c.embarque_id}`" @click.stop>{{ c.embarque }}</router-link>
                <template v-else>{{ c.embarque }}</template><template v-if="c.transportista"> · {{ c.transportista }}</template>
              </span>
            </td>
            <td class="codigo">{{ c.documento || 'Pendiente' }}</td>
            <td><EstadoBadge :estado="c.estado" /></td>
            <td>{{ c.puerto_origen || '—' }} <Icono nombre="flecha" :tam="12" /> {{ c.puerto_destino || '—' }}</td>
            <td>{{ fmtFecha(c.etd) }}</td>
            <td>{{ fmtFecha(c.eta) }}<span class="sub">{{ c.arribado ? 'arribó' : c.dias_eta === null ? '' : c.dias_eta >= 0 ? `en ${c.dias_eta} d` : `ETA vencida ${-c.dias_eta} d` }}</span></td>
            <td>
              <span v-if="c.riesgo" class="etiqueta" :class="RIESGOS[c.riesgo][1]" style="margin-left: 0">{{ RIESGOS[c.riesgo][0] }}</span>
              <span v-if="c.holgura !== null" class="sub">{{ c.holgura < 0 ? `${-c.holgura} d tarde` : `${c.holgura} d de margen` }}</span>
            </td>
            <td>{{ c.marcas.join(' · ') || '—' }}</td>
            <td class="num">{{ c.ocs }}</td>
            <td class="num">{{ porUnidadTxt(c.por_unidad, null) }}</td>
          </tr>
          <tr v-if="abiertos[`${c.embarque_id}|${c.contenedor}`]" class="fila-hija">
            <td colspan="11">
              <div class="subtabla">
                <div v-for="o in abiertos[`${c.embarque_id}|${c.contenedor}`].ocs" :key="o.oc_id" class="explosion-oc">
                  <div class="explosion-oc-cabeza">
                    <b class="codigo">OC {{ o.oc }}</b>
                    <span class="ayuda">{{ o.proveedor }} · {{ o.sociedad }}/{{ o.centro }} · destino {{ o.centro_destino || '—' }} · en tienda {{ fmtFecha(o.fecha_tienda) }}</span>
                    <span v-if="o.riesgo" class="etiqueta" :class="RIESGOS[o.riesgo][1]">{{ RIESGOS[o.riesgo][0] }}</span>
                    <span class="separar fuerte">{{ porUnidadTxt(o.por_unidad, null) }}</span>
                  </div>
                  <div class="tabla-marco" style="box-shadow: none">
                    <table class="tabla">
                      <thead><tr><th>Pos.</th><th>SKU</th><th>Marca · grupo</th><th>Estilo · color</th><th>Talla</th><th>Almacén</th><th>UM</th><th class="num">Cantidad</th><th>Factura / PL</th></tr></thead>
                      <tbody>
                        <tr v-for="(l, i) in o.lineas" :key="i">
                          <td class="codigo">{{ l.posicion }}</td>
                          <td class="codigo">{{ l.sku }}</td>
                          <td>{{ l.marca }}<span class="sub">{{ l.grupo }}</span></td>
                          <td>{{ l.estilo }} · {{ l.color }}</td>
                          <td>
                            <b>{{ l.talla }}</b>
                            <button v-if="l.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" title="Ver la explosión del prepack"
                                    @click="explosion = { sku: l.sku, cajas: l.cantidad }">Prepack <Icono nombre="lupa" :tam="12" /></button>
                          </td>
                          <td>{{ l.almacen || '—' }}</td>
                          <td><span class="etiqueta" style="margin-left: 0">{{ l.unidad }}</span></td>
                          <td class="num">{{ fmtNum(l.cantidad) }}</td>
                          <td>
                            <router-link v-if="l.factura_id" :to="`/facturas/${l.factura_id}`">{{ l.factura }}</router-link>
                            <router-link v-if="l.pl_id" :to="`/packing-lists/${l.pl_id}`" class="sub">PL {{ l.pl }}</router-link>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
  <Paginacion :page="tabla.page" :size="tabla.size" :total="datos.total" @cambiar="(p) => { tabla.page = p; cargar() }" @tamano="(t) => (tabla.size = t)" />
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>
