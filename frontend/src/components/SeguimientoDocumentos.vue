<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { fmtFecha, fmtMoneda, fmtNum } from '../utils'
import Avance from './Avance.vue'
import BotonesExportar from './BotonesExportar.vue'
import EstadoBadge from './EstadoBadge.vue'
import GraficoColumnas from './GraficoColumnas.vue'
import Kpi from './Kpi.vue'
import Icono from './Icono.vue'
import Paginacion from './Paginacion.vue'
import SelectBusqueda from './SelectBusqueda.vue'
import ThOrden from './ThOrden.vue'

// Seguimiento de facturación y empaque: una fila por packing list (o por
// factura sin PL), con el paso en que va y lo que le falta.
const filtros = reactive({
  q: '', etapa: '', estado_factura: '', estado_pl: '', sociedad: '', centro: '', embarque_id: '', proveedor: '',
  con_pendientes: false, orden: 'dias:desc', page: 1, size: 25,
})
const datos = ref({ items: [], total: 0, etapas: [], opciones: {}, kpis: {} })
const cargando = ref(true)

const TONO = {
  FACTURA_ABIERTA: 'aviso', EMPACANDO: 'aviso', POR_FINALIZAR_PL: 'info', POR_FINALIZAR_FACTURA: 'info',
  LISTO_EMBARQUE: 'ok', TENTATIVO: 'aviso', EN_CONTENEDOR: 'acento', EN_CAMINO: 'info', RECIBIDO: 'ok',
}
const CORTO = {
  FACTURA_ABIERTA: 'No PL', EMPACANDO: 'Packing', POR_FINALIZAR_PL: 'PL to final.', POR_FINALIZAR_FACTURA: 'Inv. open',
  LISTO_EMBARQUE: 'Ready', TENTATIVO: 'Tentative', EN_CONTENEDOR: 'Confirmed', EN_CAMINO: 'On the way', RECIBIDO: 'Received',
}
const grafica = computed(() => datos.value.etapas.map((e) => ({ etiqueta: CORTO[e.clave] || e.nombre, valor: e.total, detalle: e.nombre })))
const importeTxt = computed(() => Object.entries(datos.value.kpis.importe || {}).map(([m, v]) => fmtMoneda(v, m)).join(' · ') || '—')
function filtrar(obj) {
  Object.assign(filtros, { etapa: '', estado_factura: '', con_pendientes: false }, obj)
  aplicar()
}
const nombreEtapa = computed(() => Object.fromEntries(datos.value.etapas.map((e) => [e.clave, e.nombre])))
const paramsExportar = computed(() => {
  const p = { proveedor_id: sesion.proveedorId || undefined }
  for (const [k, v] of Object.entries(filtros)) if (v !== '' && v !== false && !['page', 'size'].includes(k)) p[k] = v === true ? '1' : v
  return p
})

async function cargar() {
  cargando.value = true
  try {
    const params = { proveedor_id: sesion.proveedorId || undefined }
    for (const [k, v] of Object.entries(filtros)) if (v !== '' && v !== false) params[k] = v
    datos.value = await api.get('/seguimiento/documentos', params)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function aplicar() {
  filtros.page = 1
  cargar()
}
function ordenar(campo) {
  filtros.orden = siguienteOrden(filtros.orden, campo)
  aplicar()
}
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(aplicar, 300)
}
watch(() => sesion.proveedorId, aplicar)
onMounted(cargar)
</script>

<template>
  <div class="filtros">
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" placeholder="Invoice, PL, PO or container" aria-label="Search" @input="buscar" />
    </label>
    <SelectBusqueda v-if="esInterno()" v-model="filtros.proveedor" :opciones="datos.opciones.proveedores || []" vacio="Supplier: all" etiqueta="Supplier" @change="aplicar" />
    <SelectBusqueda v-model="filtros.sociedad" :opciones="datos.opciones.sociedades || []" vacio="Bill to: all" etiqueta="Company" @change="aplicar" />
    <SelectBusqueda v-model="filtros.centro" :opciones="datos.opciones.centros || []" vacio="Plant: all" etiqueta="Plant" @change="aplicar" />
    <select v-model="filtros.estado_factura" aria-label="Invoice status" @change="aplicar">
      <option value="">Invoice: all</option><option value="BORRADOR">Draft</option>
      <option value="EN_CORRECCION">In correction</option><option value="FINALIZADA">Finalized</option>
    </select>
    <select v-model="filtros.estado_pl" aria-label="Packing list status" @change="aplicar">
      <option value="">Packing list: all</option><option value="BORRADOR">Draft</option>
      <option value="EN_CORRECCION">In correction</option><option value="FINALIZADO">Finalized</option>
    </select>
    <SelectBusqueda v-model="filtros.embarque_id" :opciones="(datos.opciones.embarques || []).map((e) => ({ valor: String(e.id), texto: e.codigo }))"
                    vacio="Shipment: all" etiqueta="Shipment" @change="aplicar" />
    <label class="check"><input v-model="filtros.con_pendientes" type="checkbox" @change="aplicar" /> Only with pending data</label>
    <BotonesExportar class="separar" ruta="/seguimiento/documentos/exportar" :params="paramsExportar" />
  </div>

  <section class="kpis" style="margin-bottom: 16px">
    <Kpi titulo="Invoices" :valor="datos.kpis.facturas" icono="factura" :detalle="importeTxt" @abrir="filtrar({})" />
    <Kpi titulo="Open invoices" :valor="datos.kpis.facturas_abiertas" icono="editar" :tono="datos.kpis.facturas_abiertas ? 'alerta' : 'exito'"
         detalle="draft or in correction" @abrir="filtrar({ estado_factura: 'BORRADOR' })" />
    <Kpi titulo="Packing" :valor="datos.kpis.empacando" icono="caja" detalle="PL not finalized" @abrir="filtrar({ etapa: 'EMPACANDO' })" />
    <Kpi titulo="Ready to ship" :valor="datos.kpis.listos" icono="check" tono="exito" detalle="invoice and PL finalized" @abrir="filtrar({ etapa: 'LISTO_EMBARQUE' })" />
    <Kpi titulo="With pending data" :valor="datos.kpis.con_pendientes" icono="alerta" :tono="datos.kpis.con_pendientes ? 'alerta' : 'exito'"
         detalle="needed to finalize" @abrir="filtrar({ con_pendientes: true })" />
  </section>
  <div class="dos-columnas" style="margin-bottom: 16px">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>Documents by step</h2><p>From open invoice to received.</p></div></div>
      <GraficoColumnas :datos="grafica" titulo="Packing lists and invoices by step" />
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>Packed cargo</h2><p>According to the filters.</p></div></div>
      <div class="doc-datos" style="margin-top: 0; padding-top: 0; border-top: 0">
        <div class="dato"><span>Packing lists</span><b>{{ fmtNum(datos.kpis.pls) }}</b></div>
        <div class="dato"><span>Cartons</span><b>{{ fmtNum(datos.kpis.cajas) }}</b></div>
        <div class="dato"><span>Pallets</span><b>{{ fmtNum(datos.kpis.pallets) }}</b></div>
        <div class="dato"><span>Gross weight</span><b>{{ fmtNum(datos.kpis.peso_bruto, 1) }} kg</b></div>
        <div class="dato"><span>Volume</span><b>{{ fmtNum(datos.kpis.cbm, 2) }} m³</b></div>
      </div>
      <div class="chips" style="margin: 12px 0 0">
        <button v-for="e in datos.etapas" :key="e.clave" type="button" class="pildora" :aria-pressed="filtros.etapa === e.clave"
                @click="filtros.etapa = filtros.etapa === e.clave ? '' : e.clave; aplicar()">{{ e.nombre }}<span class="cuenta">{{ e.total }}</span></button>
      </div>
    </section>
  </div>


  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <ThOrden campo="factura" :orden="filtros.orden" @ordenar="ordenar">Invoice</ThOrden>
          <ThOrden v-if="!sesion.proveedorId" campo="proveedor" :orden="filtros.orden" @ordenar="ordenar">Supplier</ThOrden>
          <ThOrden campo="centro" :orden="filtros.orden" @ordenar="ordenar">Bill to / notify</ThOrden>
          <ThOrden campo="estado_factura" :orden="filtros.orden" @ordenar="ordenar">Invoice status</ThOrden>
          <ThOrden campo="estado_pl" :orden="filtros.orden" @ordenar="ordenar">Packing list</ThOrden>
          <ThOrden campo="avance" :orden="filtros.orden" @ordenar="ordenar">Packed</ThOrden>
          <ThOrden campo="cajas" :orden="filtros.orden" num @ordenar="ordenar">Cartons</ThOrden>
          <ThOrden campo="peso_bruto" :orden="filtros.orden" num @ordenar="ordenar">Gross kg</ThOrden>
          <ThOrden campo="cbm" :orden="filtros.orden" num @ordenar="ordenar">m³</ThOrden>
          <ThOrden campo="pendientes" :orden="filtros.orden" num @ordenar="ordenar">Pending</ThOrden>
          <ThOrden campo="etapa" :orden="filtros.orden" @ordenar="ordenar">Step</ThOrden>
          <ThOrden campo="embarque" :orden="filtros.orden" @ordenar="ordenar">Load unit</ThOrden>
          <ThOrden campo="dias" :orden="filtros.orden" num @ordenar="ordenar">Days</ThOrden>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td colspan="13" class="vacio">Loading…</td></tr>
        <tr v-else-if="!datos.items.length"><td colspan="13" class="vacio">No documents match these filters.</td></tr>
        <tr v-for="f in datos.items" :key="`${f.factura_id}-${f.pl_id}`">
          <td>
            <router-link :to="`/facturas/${f.factura_id}`" class="fuerte">{{ f.factura }}</router-link>
            <span class="sub codigo">{{ f.ocs.join(', ') }}</span>
          </td>
          <td v-if="!sesion.proveedorId">{{ f.proveedor }}</td>
          <td><span class="codigo">{{ f.sociedad }} · {{ f.centro || '—' }}</span><span class="sub">destination {{ f.centro_destino || '—' }} · {{ fmtMoneda(f.importe, f.moneda) }}</span></td>
          <td><EstadoBadge :estado="f.estado_factura" /><span v-if="f.pendientes_factura" class="sub">{{ f.pendientes_factura }} fields to complete</span></td>
          <td>
            <template v-if="f.pl_id">
              <router-link :to="`/packing-lists/${f.pl_id}`" class="cajas-rango">{{ f.pl }}</router-link> <EstadoBadge :estado="f.estado_pl" />
            </template>
            <span v-else class="ayuda">No packing list</span>
          </td>
          <td style="min-width: 120px"><Avance v-if="f.pl_id" :porcentaje="f.avance" /><span v-else class="ayuda">—</span></td>
          <td class="num">{{ fmtNum(f.cajas) }}<span v-if="f.pallets" class="sub">{{ f.pallets }} pallets</span></td>
          <td class="num">{{ fmtNum(f.peso_bruto, 1) }}</td>
          <td class="num">{{ fmtNum(f.cbm, 2) }}</td>
          <td class="num"><span v-if="f.pendientes" class="etiqueta aviso">{{ f.pendientes }}</span><span v-else class="ayuda">0</span></td>
          <td><span class="etiqueta" :class="TONO[f.etapa]" style="margin-left: 0">{{ nombreEtapa[f.etapa] || f.etapa }}</span></td>
          <td>
            <template v-if="f.embarque_id">
              <span class="codigo">{{ f.contenedor }}</span>
              <span class="sub">
                <router-link v-if="esInterno()" :to="`/transporte/embarques/${f.embarque_id}`">{{ f.embarque }}</router-link><template v-else>{{ f.embarque }}</template>
                · ETA {{ fmtFecha(f.eta) }}
              </span>
            </template>
            <span v-else class="ayuda">—</span>
          </td>
          <td class="num">{{ f.dias ?? '—' }}<span class="sub">{{ fmtFecha(f.fecha) }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total"
              @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
</template>
