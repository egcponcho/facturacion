<script setup>
import { datosModo, modosTransporte } from '@/composables/useRutas'
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import { esInterno, sesion, ve } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { TIEMPO, fmtDiaMes, fmtFecha, fmtNum, porUnidadTxt } from '@/nucleo/utils'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import ExplosionPrepack from '@/componentes/ExplosionPrepack.vue'
import GraficoColumnas from '@/componentes/GraficoColumnas.vue'
import Icono from '@/componentes/Icono.vue'
import Kpi from '@/componentes/Kpi.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'

// Tablero de embarques: un renglón por embarque y su documento de transporte
// (BL, AWB o carta de porte). Se abre en sus unidades de carga y cada unidad
// en lo que lleva por orden de compra.
const props = defineProps({ filtros: { type: Object, required: true } })
const emit = defineEmits(['opciones', 'filtrar'])
const datos = ref({ items: [], total: 0, kpis: {}, por_estado: [], llegadas: [] })
const cargando = ref(true)
const tablaE = ref(null)
const explosiones = reactive({})
const explosion = ref(null)
const RIESGOS = TIEMPO

// La tabla filtra cada columna por sus valores en el servidor (/seguimiento/embarques/valores)
const base = () => ({ ...props.filtros, proveedor_id: sesion.proveedorId || undefined })
let ultima = null
async function cargar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/embarques', { ...base(), orden: c.orden || undefined, page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
    emit('opciones', datos.value.opciones)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const valores = (columna, buscar, otros) => api.get('/seguimiento/embarques/valores', { ...base(), columna, buscar, f: JSON.stringify(otros) })
const columnas = computed(() => [
  { clave: 'embarque', texto: t('Shipment'), fija: true, prioridad: 1 },
  { clave: 'modo', texto: t('Mode'), prioridad: 3, inicial: false, ordenable: true, opciones: modosTransporte().map((m) => [m.codigo, m.nombre]) },
  { clave: 'documento', texto: t('Transport document'), prioridad: 2 },
  { clave: 'estado', texto: t('Status'), prioridad: 1, opciones: datos.value.por_estado.map((e) => [e.clave, e.nombre]) },
  { clave: 'ruta', texto: t('Route'), prioridad: 3, ordenable: false },
  { clave: 'etd', texto: t('Departure'), prioridad: 3, textoValor: (v) => fmtFecha(v) },
  { clave: 'eta', texto: t('Arrival'), prioridad: 2, textoValor: (v) => fmtFecha(v) },
  { clave: 'holgura', texto: t('Vs. port deadline'), grupo: 'fechas_internas', prioridad: 3, opciones: Object.entries(RIESGOS).map(([k, [txt]]) => [k, txt]) },
  { clave: 'unidades', texto: t('Units'), num: true, prioridad: 2 },
  { clave: 'ocs', texto: t('POs'), num: true, prioridad: 3 },
  { clave: 'proveedores', texto: t('Supplier'), prioridad: 3, inicial: false, ordenable: false },
  { clave: 'contenido', texto: t('Contents'), num: true, prioridad: 3, filtro: false, ordenable: false },
])
const columnasLineas = [
  { clave: 'posicion', texto: t('Line'), fija: true, prioridad: 1 },
  { clave: 'sku', texto: 'SKU', prioridad: 1 },
  { clave: 'marca', texto: t('Brand · group'), prioridad: 2 },
  { clave: 'estilo', texto: t('Style · color'), prioridad: 2, valor: (l) => `${l.estilo} · ${l.color}` },
  { clave: 'talla', texto: t('Size'), prioridad: 1 },
  { clave: 'almacen', texto: t('Warehouse'), prioridad: 3, textoValor: (v) => v || '—' },
  { clave: 'unidad', texto: t('UoM'), prioridad: 3 },
  { clave: 'cantidad', texto: t('Quantity'), num: true, prioridad: 1 },
  { clave: 'factura', texto: t('Invoice / PL'), prioridad: 2 },
]
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
const llegadas = computed(() => datos.value.llegadas.map((s, i) => ({
  etiqueta: i === 0 ? t('This wk') : fmtDiaMes(s.desde),
  valor: s.embarques,
  detalle: `${fmtFecha(s.desde)} – ${fmtFecha(s.hasta)}`,
})))
const estados = computed(() => datos.value.por_estado.map((e) => ({ etiqueta: e.nombre, valor: e.total })))
const porModo = computed(() => Object.entries(datos.value.kpis.por_modo || {}).filter(([, n]) => n)
  .map(([m, n]) => `${fmtNum(n)} ${datosModo(m).nombre.toLowerCase()}`).join(' · ') || t('no shipments'))

watch(() => [props.filtros, sesion.proveedorId], () => {
  for (const k of Object.keys(explosiones)) delete explosiones[k]
  if (tablaE.value && tablaE.value.pagina !== 1) tablaE.value.pagina = 1
  else cargar()
}, { deep: true })
</script>

<template>
  <section class="kpis mb-4">
    <Kpi :titulo="t('Shipments')" :valor="datos.kpis.embarques" icono="ruta" :detalle="tx(porModo)" @abrir="emit('filtrar', {})" />
    <Kpi :titulo="t('Load units')" :valor="datos.kpis.unidades" icono="contenedor" :detalle="t('containers, air waybills and trucks')" @abrir="emit('filtrar', {})" />
    <Kpi :titulo="t('In transit')" :valor="datos.kpis.en_camino" icono="barco" :detalle="t('already departed')" @abrir="emit('filtrar', { estado: 'EN_TRANSITO' })" />
    <Kpi :titulo="t('Arriving in 7 days')" :valor="datos.kpis.llegan_7_dias" icono="reloj" :detalle="t('by ETA')" @abrir="emit('filtrar', {})" />
    <Kpi v-if="ve('fechas_internas')" :titulo="t('Late for the port deadline')" :valor="datos.kpis.atrasados" icono="alerta" :tono="datos.kpis.atrasados ? 'alerta' : 'exito'"
         :detalle="t('ETA after the in-store date')" @abrir="emit('filtrar', { riesgo: 'ATRASO' })" />
  </section>

  <div class="dos-columnas mb-4">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Arrivals per week') }}</h2><p>{{ t('Shipments not yet arrived, by week of their ETA.') }}</p></div></div>
      <GraficoColumnas :datos="llegadas" :titulo="t('Shipments by arrival week')" />
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Shipments by status') }}</h2><p>{{ t('According to the filters; use the status filter to see only one.') }}</p></div></div>
      <GraficoColumnas :datos="estados" :titulo="t('Shipments by status')" />
    </section>
  </div>

  <TablaDatos ref="tablaE" tabla="seguimiento_embarques" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              clave-fila="embarque_id" :valores="valores" expandible :etiqueta="t('Shipments')" @consulta="cargar">
    <template #celda-embarque="{ fila: e }">
      <router-link v-if="esInterno()" :to="`/transporte/embarques/${e.embarque_id}`" class="enlace-doc" @click.stop><strong class="codigo">{{ tx(e.embarque) }}</strong></router-link>
      <b v-else class="codigo">{{ tx(e.embarque) }}</b>
      <span class="sub"><Icono :nombre="datosModo(e.modo).icono" :tam="12" /> {{ datosModo(e.modo).nombre }}<template v-if="e.modalidad"> · {{ tx(e.modalidad) }}</template></span>
    </template>
    <template #celda-modo="{ fila: e }">{{ datosModo(e.modo).nombre }}</template>
    <template #celda-documento="{ fila: e }">
      <span class="codigo">{{ tx(e.documento || t('Pending')) }}</span>
      <span class="sub">{{ datosModo(e.modo).doc }}<template v-if="e.transportista"> · {{ tx(e.transportista) }}</template></span>
    </template>
    <template #celda-estado="{ fila: e }"><EstadoBadge :estado="e.estado" tipo="embarque" /></template>
    <template #celda-ruta="{ fila: e }">{{ tx(e.puerto_origen || '—') }} <Icono nombre="flecha" :tam="12" /> {{ tx(e.puerto_destino || '—') }}<span v-if="e.centro" class="sub">{{ t('plant {0}', [e.centro]) }}</span></template>
    <template #celda-etd="{ fila: e }">{{ fmtFecha(e.etd) }}</template>
    <template #celda-eta="{ fila: e }">{{ fmtFecha(e.eta) }}<span class="sub">{{ tx(e.arribado ? t('arrived') : e.dias_eta === null ? '' : e.dias_eta >= 0 ? t('in {0} d', [e.dias_eta]) : t('ETA overdue {0} d', [-e.dias_eta])) }}</span></template>
    <template #celda-holgura="{ fila: e }">
      <span v-if="e.riesgo" class="etiqueta ms-0" :class="RIESGOS[e.riesgo][1]">{{ tx(RIESGOS[e.riesgo][0]) }}</span>
      <span v-if="e.holgura != null" class="sub">{{ tx(e.holgura < 0 ? t('{0} d late', [-e.holgura]) : t('{0} d margin', [e.holgura])) }}</span>
    </template>
    <template #celda-proveedores="{ fila: e }">{{ tx([].concat(e.proveedores || []).join(', ') || '—') }}</template>
    <template #celda-contenido="{ fila: e }">{{ porUnidadTxt(e.por_unidad, null) }}<span class="sub">{{ tx(e.marcas.join(' · ')) }}</span></template>
    <template #detalle="{ fila: e }">
      <div v-for="u in e.detalle_unidades" :key="u.unidad_id" class="explosion-oc">
        <button type="button" class="explosion-oc-cabeza enlace-bloque" :aria-expanded="!!explosiones[u.unidad_id]" @click="alternarUnidad(u)">
          <Icono :nombre="explosiones[u.unidad_id] ? 'abajo' : 'derecha'" :tam="14" />
          <b class="codigo">{{ datosModo(e.modo).unidad }} {{ tx(u.contenedor) }}</b>
          <span class="etiqueta ms-0">{{ tx(u.tipo_nombre) }}</span>
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
            <TablaDatos tabla="seguimiento_unidad_lineas" :columnas="columnasLineas" :filas="o.lineas.map((l, i) => ({ ...l, _i: i }))" clave-fila="_i"
                        :vistas-guardadas="false" :etiqueta="t('PO {0}', [o.oc])">
              <template #celda-posicion="{ fila: l }"><span class="codigo">{{ tx(l.posicion) }}</span></template>
              <template #celda-sku="{ fila: l }"><span class="codigo">{{ tx(l.sku) }}</span></template>
              <template #celda-marca="{ fila: l }">{{ tx(l.marca) }}<span class="sub">{{ tx(l.grupo) }}</span></template>
              <template #celda-estilo="{ fila: l }">{{ tx(l.estilo) }} · {{ tx(l.color) }}</template>
              <template #celda-talla="{ fila: l }">
                <b>{{ tx(l.talla) }}</b>
                <button v-if="l.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" :title="t('See the prepack breakdown')"
                        @click="explosion = { sku: l.sku, cajas: l.cantidad }">{{ t('Prepack') }} <Icono nombre="lupa" :tam="12" /></button>
              </template>
              <template #celda-unidad="{ fila: l }"><span class="etiqueta ms-0">{{ tx(l.unidad) }}</span></template>
              <template #celda-cantidad="{ fila: l }">{{ fmtNum(l.cantidad) }}</template>
              <template #celda-factura="{ fila: l }">
                <router-link v-if="l.factura_id" :to="`/facturas/${l.factura_id}`" class="enlace codigo">{{ tx(l.factura) }}</router-link>
                <router-link v-if="l.pl_id" :to="`/packing-lists/${l.pl_id}`" class="sub enlace">{{ t('PL {0}', [l.pl]) }}</router-link>
              </template>
            </TablaDatos>
          </div>
        </template>
      </div>
    </template>
    <template #vacio>{{ t('No shipments with goods for these filters.') }}</template>
  </TablaDatos>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>
