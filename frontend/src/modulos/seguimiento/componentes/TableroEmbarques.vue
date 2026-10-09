<script setup>
import { datosModo } from '@/composables/useRutas'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import { siguienteOrden } from '@/composables/useTabla'
import { esInterno, sesion, ve } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { TIEMPO, fmtDiaMes, fmtFecha, fmtNum, porUnidadTxt } from '@/nucleo/utils'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import ExplosionPrepack from '@/componentes/ExplosionPrepack.vue'
import GraficoColumnas from '@/componentes/GraficoColumnas.vue'
import Icono from '@/componentes/Icono.vue'
import Kpi from '@/componentes/Kpi.vue'
import Paginacion from '@/componentes/Paginacion.vue'
import ThOrden from '@/componentes/ThOrden.vue'
import { filasDefecto } from '@/stores/preferencias'

// Tablero de embarques: un renglón por embarque y su documento de transporte
// (BL, AWB o carta de porte). Se abre en sus unidades de carga y cada unidad
// en lo que lleva por orden de compra.
const props = defineProps({ filtros: { type: Object, required: true } })
const emit = defineEmits(['opciones', 'filtrar'])
const datos = ref({ items: [], total: 0, kpis: {}, por_estado: [], llegadas: [] })
const cargando = ref(true)
const tabla = reactive({ orden: '', page: 1, size: filasDefecto() })
const abiertos = reactive({})
const explosiones = reactive({})
const explosion = ref(null)
const RIESGOS = TIEMPO

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/embarques', {
      ...props.filtros, ...tabla, proveedor_id: sesion.proveedorId || undefined,
    })
    emit('opciones', datos.value.opciones)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function alternar(e) {
  abiertos[e.embarque_id] = !abiertos[e.embarque_id]
}
async function alternarUnidad(u) {
  if (explosiones[u.unidad_id]) {
    delete explosiones[u.unidad_id]
    return
  }
  try {
    explosiones[u.unidad_id] = await api.get(`/seguimiento/unidades/${u.unidad_id}/explosion`,
      { ...props.filtros, proveedor_id: sesion.proveedorId || undefined })
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
  etiqueta: i === 0 ? t('This wk') : fmtDiaMes(s.desde),
  valor: s.embarques,
  detalle: `${fmtFecha(s.desde)} – ${fmtFecha(s.hasta)}`,
})))
const estados = computed(() => datos.value.por_estado.map((e) => ({ etiqueta: e.nombre, valor: e.total })))
const porModo = computed(() => Object.entries(datos.value.kpis.por_modo || {}).filter(([, n]) => n)
  .map(([m, n]) => `${fmtNum(n)} ${datosModo(m).nombre.toLowerCase()}`).join(' · ') || t('no shipments'))

watch(() => [props.filtros, sesion.proveedorId], () => {
  tabla.page = 1
  for (const k of Object.keys(explosiones)) delete explosiones[k]
  cargar()
}, { deep: true })
onMounted(cargar)
</script>

<template>
  <section class="kpis" style="margin-bottom: 16px">
    <Kpi :titulo="t('Shipments')" :valor="datos.kpis.embarques" icono="ruta" :detalle="tx(porModo)" @abrir="emit('filtrar', {})" />
    <Kpi :titulo="t('Load units')" :valor="datos.kpis.unidades" icono="contenedor" :detalle="t('containers, air waybills and trucks')" @abrir="emit('filtrar', {})" />
    <Kpi :titulo="t('In transit')" :valor="datos.kpis.en_camino" icono="barco" :detalle="t('already departed')" @abrir="emit('filtrar', { estado: 'EN_TRANSITO' })" />
    <Kpi :titulo="t('Arriving in 7 days')" :valor="datos.kpis.llegan_7_dias" icono="reloj" :detalle="t('by ETA')" @abrir="emit('filtrar', {})" />
    <Kpi v-if="ve('fechas_internas')" :titulo="t('Late for the port deadline')" :valor="datos.kpis.atrasados" icono="alerta" :tono="datos.kpis.atrasados ? 'alerta' : 'exito'"
         :detalle="t('ETA after the in-store date')" @abrir="emit('filtrar', { riesgo: 'ATRASO' })" />
  </section>

  <div class="dos-columnas" style="margin-bottom: 16px">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Arrivals per week') }}</h2><p>{{ t('Shipments not yet arrived, by week of their ETA.') }}</p></div></div>
      <GraficoColumnas :datos="llegadas" :titulo="t('Shipments by arrival week')" />
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Shipments by status') }}</h2><p>{{ t('According to the filters; use the status filter to see only one.') }}</p></div></div>
      <GraficoColumnas :datos="estados" :titulo="t('Shipments by status')" />
    </section>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla" v-tarjetas>
      <thead>
        <tr>
          <th><span class="oculto-visual">{{ t('Open') }}</span></th>
          <ThOrden campo="embarque" :orden="tabla.orden" @ordenar="ordenar">{{ t('Shipment') }}</ThOrden>
          <ThOrden campo="documento" :orden="tabla.orden" @ordenar="ordenar">{{ t('Transport document') }}</ThOrden>
          <ThOrden campo="estado" :orden="tabla.orden" @ordenar="ordenar">{{ t('Status') }}</ThOrden>
          <th>{{ t('Route') }}</th>
          <ThOrden campo="etd" :orden="tabla.orden" @ordenar="ordenar">{{ t('Departure') }}</ThOrden>
          <ThOrden campo="eta" :orden="tabla.orden" @ordenar="ordenar">{{ t('Arrival') }}</ThOrden>
          <ThOrden v-if="ve('fechas_internas')" campo="holgura" :orden="tabla.orden" :title="t('Port arrival against the port deadline: the in-store date minus the days to the warehouse, the warehouse entry and the re-export of its origin')" @ordenar="ordenar">{{ t('Vs. port deadline') }}</ThOrden>
          <ThOrden campo="unidades" :orden="tabla.orden" num @ordenar="ordenar">{{ t('Units') }}</ThOrden>
          <ThOrden campo="ocs" :orden="tabla.orden" num @ordenar="ordenar">{{ t('POs') }}</ThOrden>
          <th class="num">{{ t('Contents') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td colspan="11" class="vacio">{{ t('Loading…') }}</td></tr>
        <tr v-else-if="!datos.items.length"><td colspan="11" class="vacio">{{ t('No shipments with goods for these filters.') }}</td></tr>
        <template v-for="e in datos.items" :key="e.embarque_id">
          <tr class="clicable" @click="alternar(e)">
            <td>
              <button type="button" class="btn-icono" :aria-expanded="!!abiertos[e.embarque_id]" :aria-label="t('See the units of {0}', [e.embarque])">
                <Icono :nombre="abiertos[e.embarque_id] ? 'abajo' : 'derecha'" :tam="16" />
              </button>
            </td>
            <td>
              <router-link v-if="esInterno()" :to="`/transporte/embarques/${e.embarque_id}`" class="codigo fuerte" @click.stop>{{ tx(e.embarque) }}</router-link>
              <b v-else class="codigo">{{ tx(e.embarque) }}</b>
              <span class="sub"><Icono :nombre="datosModo(e.modo).icono" :tam="12" /> {{ datosModo(e.modo).nombre }}<template v-if="e.modalidad"> · {{ tx(e.modalidad) }}</template></span>
            </td>
            <td>
              <span class="codigo">{{ tx(e.documento || t('Pending')) }}</span>
              <span class="sub">{{ datosModo(e.modo).doc }}<template v-if="e.transportista"> · {{ tx(e.transportista) }}</template></span>
            </td>
            <td><EstadoBadge :estado="e.estado" tipo="embarque" /></td>
            <td>{{ tx(e.puerto_origen || '—') }} <Icono nombre="flecha" :tam="12" /> {{ tx(e.puerto_destino || '—') }}<span v-if="e.centro" class="sub">{{ t('plant {0}', [e.centro]) }}</span></td>
            <td>{{ fmtFecha(e.etd) }}</td>
            <td>{{ fmtFecha(e.eta) }}<span class="sub">{{ tx(e.arribado ? t('arrived') : e.dias_eta === null ? '' : e.dias_eta >= 0 ? t('in {0} d', [e.dias_eta]) : t('ETA overdue {0} d', [-e.dias_eta])) }}</span></td>
            <td v-if="ve('fechas_internas')">
              <span v-if="e.riesgo" class="etiqueta" :class="RIESGOS[e.riesgo][1]" style="margin-inline-start: 0">{{ tx(RIESGOS[e.riesgo][0]) }}</span>
              <span v-if="e.holgura != null" class="sub">{{ tx(e.holgura < 0 ? t('{0} d late', [-e.holgura]) : t('{0} d margin', [e.holgura])) }}</span>
            </td>
            <td class="num">{{ tx(e.unidades) }}</td>
            <td class="num">{{ tx(e.ocs) }}</td>
            <td class="num">{{ porUnidadTxt(e.por_unidad, null) }}<span class="sub">{{ tx(e.marcas.join(' · ')) }}</span></td>
          </tr>
          <tr v-if="abiertos[e.embarque_id]" class="fila-hija">
            <td colspan="11">
              <div class="subtabla">
                <div v-for="u in e.detalle_unidades" :key="u.unidad_id" class="explosion-oc">
                  <button type="button" class="explosion-oc-cabeza enlace-bloque" :aria-expanded="!!explosiones[u.unidad_id]" @click="alternarUnidad(u)">
                    <Icono :nombre="explosiones[u.unidad_id] ? 'abajo' : 'derecha'" :tam="14" />
                    <b class="codigo">{{ datosModo(e.modo).unidad }} {{ tx(u.contenedor) }}</b>
                    <span class="etiqueta" style="margin-inline-start: 0">{{ tx(u.tipo_nombre) }}</span>
                    <span v-if="u.modalidad" class="etiqueta acento">{{ tx(u.modalidad) }}</span>
                    <span class="ayuda">{{ t('{0} · {1} PO · {2}', [u.sello ? t('seal {0}', [u.sello]) : t('no seal'), u.ocs, u.facturas.join(', ') || t('no invoice')]) }}</span>
                    <span v-if="u.riesgo" class="etiqueta" :class="RIESGOS[u.riesgo][1]">{{ tx(RIESGOS[u.riesgo][0]) }}</span>
                    <span class="separar fuerte">{{ porUnidadTxt(u.por_unidad, null) }}</span>
                  </button>
                  <template v-if="explosiones[u.unidad_id]">
                    <div v-for="o in explosiones[u.unidad_id].ocs" :key="o.oc_id" class="explosion-sub">
                      <div class="explosion-oc-cabeza">
                        <b class="codigo">{{ t('PO {0}', [o.oc]) }}</b>
                        <span class="ayuda">{{ t('{0} · {1}/{2} · destination {3} · in store {4}', [o.proveedor, o.sociedad, o.centro, o.centro_destino || '—', fmtFecha(o.fecha_tienda)]) }}</span>
                        <span v-if="o.riesgo" class="etiqueta" :class="RIESGOS[o.riesgo][1]">{{ tx(RIESGOS[o.riesgo][0]) }}</span>
                        <span class="separar fuerte">{{ porUnidadTxt(o.por_unidad, null) }}</span>
                      </div>
                      <div class="tabla-marco" style="box-shadow: none">
                        <table class="tabla" v-tarjetas>
                          <thead><tr><th>{{ t('Line') }}</th><th>SKU</th><th>{{ t('Brand · group') }}</th><th>{{ t('Style · color') }}</th><th>{{ t('Size') }}</th><th>{{ t('Warehouse') }}</th><th>{{ t('UoM') }}</th><th class="num">{{ t('Quantity') }}</th><th>{{ t('Invoice / PL') }}</th></tr></thead>
                          <tbody>
                            <tr v-for="(l, i) in o.lineas" :key="i">
                              <td class="codigo">{{ tx(l.posicion) }}</td>
                              <td class="codigo">{{ tx(l.sku) }}</td>
                              <td>{{ tx(l.marca) }}<span class="sub">{{ tx(l.grupo) }}</span></td>
                              <td>{{ tx(l.estilo) }} · {{ tx(l.color) }}</td>
                              <td>
                                <b>{{ tx(l.talla) }}</b>
                                <button v-if="l.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" :title="t('See the prepack breakdown')"
                                        @click="explosion = { sku: l.sku, cajas: l.cantidad }">{{ t('Prepack') }} <Icono nombre="lupa" :tam="12" /></button>
                              </td>
                              <td>{{ tx(l.almacen || '—') }}</td>
                              <td><span class="etiqueta" style="margin-inline-start: 0">{{ tx(l.unidad) }}</span></td>
                              <td class="num">{{ fmtNum(l.cantidad) }}</td>
                              <td>
                                <router-link v-if="l.factura_id" :to="`/facturas/${l.factura_id}`">{{ tx(l.factura) }}</router-link>
                                <router-link v-if="l.pl_id" :to="`/packing-lists/${l.pl_id}`" class="sub">{{ t('PL {0}', [l.pl]) }}</router-link>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </template>
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
