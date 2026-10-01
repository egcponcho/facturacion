<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from './Seleccion.vue'
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
import { filasDefecto } from '../stores/preferencias'

// Filtros de varios valores: se guardan como texto separado por comas
const lst = (v) => (v ? String(v).split(',').filter(Boolean) : [])

// Seguimiento de facturación y empaque: una fila por packing list (o por
// factura sin PL), con el paso en que va y lo que le falta.
const filtros = reactive({
  q: '', etapa: '', estado_factura: '', estado_pl: '', sociedad: '', centro: '', embarque_id: '', proveedor: '',
  con_pendientes: false, orden: 'dias:desc', page: 1, size: filasDefecto(),
})
const datos = ref({ items: [], total: 0, etapas: [], opciones: {}, kpis: {} })
const cargando = ref(true)

const TONO = {
  FACTURA_ABIERTA: 'aviso', EMPACANDO: 'aviso', POR_FINALIZAR_PL: 'info', POR_FINALIZAR_FACTURA: 'info',
  LISTO_EMBARQUE: 'ok', TENTATIVO: 'aviso', EN_CONTENEDOR: 'acento', EN_CAMINO: 'info', RECIBIDO: 'ok',
}
const CORTO = {
  FACTURA_ABIERTA: t('No PL'), EMPACANDO: t('Packing'), POR_FINALIZAR_PL: t('PL to final.'), POR_FINALIZAR_FACTURA: t('Inv. open'),
  LISTO_EMBARQUE: t('Ready'), TENTATIVO: t('Tentative'), EN_CONTENEDOR: t('Confirmed'), EN_CAMINO: t('On the way'), RECIBIDO: t('Received'),
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
  <div class="filtros" v-filtros>
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" :placeholder="t('Invoice, PL, PO or container')" :aria-label="t('Search')" @input="buscar" />
    </label>
    <SelectBusqueda v-if="esInterno()" multiple :model-value="lst(filtros.proveedor)" @update:model-value="(v) => (filtros.proveedor = v.join(','))" :opciones="datos.opciones.proveedores || []" :vacio="t('Supplier: all')" :etiqueta="t('Supplier')" @change="aplicar" />
    <SelectBusqueda v-if="(datos.opciones.sociedades || []).length > 1 || filtros.sociedad" multiple :model-value="lst(filtros.sociedad)" @update:model-value="(v) => (filtros.sociedad = v.join(','))" :opciones="datos.opciones.sociedades || []" :vacio="t('Bill to: all')" :etiqueta="t('Company')" @change="aplicar" />
    <SelectBusqueda v-if="(datos.opciones.centros || []).length > 1 || filtros.centro" multiple :model-value="lst(filtros.centro)" @update:model-value="(v) => (filtros.centro = v.join(','))" :opciones="datos.opciones.centros || []" :vacio="t('Plant: all')" :etiqueta="t('Plant')" @change="aplicar" />
    <Seleccion v-model="filtros.estado_factura" :aria-label="t('Invoice status')" @change="aplicar">
      <option value="">{{ t('Invoice: all') }}</option><option value="BORRADOR">{{ t('Draft') }}</option>
      <option value="EN_CORRECCION">{{ t('In correction') }}</option><option value="FINALIZADA">{{ t('Finalized') }}</option>
    </Seleccion>
    <Seleccion v-model="filtros.estado_pl" :aria-label="t('Packing list status')" @change="aplicar">
      <option value="">{{ t('Packing list: all') }}</option><option value="BORRADOR">{{ t('Draft') }}</option>
      <option value="EN_CORRECCION">{{ t('In correction') }}</option><option value="FINALIZADO">{{ t('Finalized') }}</option>
    </Seleccion>
    <SelectBusqueda multiple :model-value="lst(filtros.embarque_id)" @update:model-value="(v) => (filtros.embarque_id = v.join(','))" :opciones="(datos.opciones.embarques || []).map((e) => ({ valor: String(e.id), texto: e.codigo }))"
                    :vacio="t('Shipment: all')" :etiqueta="t('Shipment')" @change="aplicar" />
    <label class="check"><input v-model="filtros.con_pendientes" type="checkbox" @change="aplicar" /> {{ t('Only with pending data') }}</label>
    <BotonesExportar class="separar" ruta="/seguimiento/documentos/exportar" :params="paramsExportar" />
  </div>

  <section class="kpis" style="margin-bottom: 16px">
    <Kpi :titulo="t('Invoices')" :valor="datos.kpis.facturas" icono="factura" :detalle="tx(importeTxt)" @abrir="filtrar({})" />
    <Kpi :titulo="t('Open invoices')" :valor="datos.kpis.facturas_abiertas" icono="editar" :tono="datos.kpis.facturas_abiertas ? 'alerta' : 'exito'"
         :detalle="t('draft or in correction')" @abrir="filtrar({ estado_factura: 'BORRADOR' })" />
    <Kpi :titulo="t('Packing')" :valor="datos.kpis.empacando" icono="caja" :detalle="t('PL not finalized')" @abrir="filtrar({ etapa: 'EMPACANDO' })" />
    <Kpi :titulo="t('Ready to ship')" :valor="datos.kpis.listos" icono="check" tono="exito" :detalle="t('invoice and PL finalized')" @abrir="filtrar({ etapa: 'LISTO_EMBARQUE' })" />
    <Kpi :titulo="t('With pending data')" :valor="datos.kpis.con_pendientes" icono="alerta" :tono="datos.kpis.con_pendientes ? 'alerta' : 'exito'"
         :detalle="t('needed to finalize')" @abrir="filtrar({ con_pendientes: true })" />
  </section>
  <div class="dos-columnas" style="margin-bottom: 16px">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Documents by step') }}</h2><p>{{ t('From open invoice to received.') }}</p></div></div>
      <GraficoColumnas :datos="grafica" :titulo="t('Packing lists and invoices by step')" />
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Packed cargo') }}</h2><p>{{ t('According to the filters.') }}</p></div></div>
      <div class="doc-datos" style="margin-top: 0; padding-top: 0; border-top: 0">
        <div class="dato"><span>{{ t('Packing lists') }}</span><b>{{ fmtNum(datos.kpis.pls) }}</b></div>
        <div class="dato"><span>{{ t('Cartons') }}</span><b>{{ fmtNum(datos.kpis.cajas) }}</b></div>
        <div class="dato"><span>{{ t('Pallets') }}</span><b>{{ fmtNum(datos.kpis.pallets) }}</b></div>
        <div class="dato"><span>{{ t('Gross weight') }}</span><b>{{ t('{0} kg', [fmtNum(datos.kpis.peso_bruto, 1)]) }}</b></div>
        <div class="dato"><span>{{ t('Volume') }}</span><b>{{ fmtNum(datos.kpis.cbm, 2) }} m³</b></div>
      </div>
      <div class="chips" style="margin: 12px 0 0">
        <button v-for="e in datos.etapas" :key="e.clave" type="button" class="pildora" :aria-pressed="filtros.etapa === e.clave"
                @click="filtros.etapa = filtros.etapa === e.clave ? '' : e.clave; aplicar()">{{ tx(e.nombre) }}<span class="cuenta">{{ tx(e.total) }}</span></button>
      </div>
    </section>
  </div>


  <div class="tabla-marco tabla-fija">
    <table class="tabla" v-tarjetas>
      <thead>
        <tr>
          <ThOrden campo="factura" :orden="filtros.orden" @ordenar="ordenar">{{ t('Invoice') }}</ThOrden>
          <ThOrden v-if="!sesion.proveedorId" campo="proveedor" :orden="filtros.orden" @ordenar="ordenar">{{ t('Supplier') }}</ThOrden>
          <ThOrden class="col-sec" campo="centro" :orden="filtros.orden" @ordenar="ordenar">{{ t('Bill to / notify') }}</ThOrden>
          <ThOrden campo="estado_factura" :orden="filtros.orden" @ordenar="ordenar">{{ t('Invoice status') }}</ThOrden>
          <ThOrden campo="estado_pl" :orden="filtros.orden" @ordenar="ordenar">{{ t('Packing list') }}</ThOrden>
          <ThOrden campo="avance" :orden="filtros.orden" @ordenar="ordenar">{{ t('Packed') }}</ThOrden>
          <ThOrden class="col-sec" campo="cajas" :orden="filtros.orden" num @ordenar="ordenar">{{ t('Cartons · kg · m³') }}</ThOrden>
          <ThOrden campo="pendientes" :orden="filtros.orden" num @ordenar="ordenar">{{ t('Pending') }}</ThOrden>
          <ThOrden campo="etapa" :orden="filtros.orden" @ordenar="ordenar">{{ t('Step') }}</ThOrden>
          <ThOrden campo="embarque" :orden="filtros.orden" @ordenar="ordenar">{{ t('Load unit') }}</ThOrden>
          <ThOrden campo="dias" :orden="filtros.orden" num @ordenar="ordenar">{{ t('Days') }}</ThOrden>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td colspan="11" class="vacio">{{ t('Loading…') }}</td></tr>
        <tr v-else-if="!datos.items.length"><td colspan="11" class="vacio">{{ t('No documents match these filters.') }}</td></tr>
        <tr v-for="f in datos.items" :key="`${f.factura_id}-${f.pl_id}`">
          <td>
            <router-link :to="`/facturas/${f.factura_id}`" class="fuerte">{{ tx(f.factura) }}</router-link>
            <span class="sub codigo">{{ tx(f.ocs.join(', ')) }}</span>
          </td>
          <td v-if="!sesion.proveedorId">{{ tx(f.proveedor) }}</td>
          <td class="ajustar"><span class="codigo">{{ tx(f.sociedad) }} · {{ tx(f.centro || '—') }}</span><span class="sub">{{ t('destination {0} · {1}', [f.centro_destino || '—', fmtMoneda(f.importe, f.moneda)]) }}</span></td>
          <td><EstadoBadge :estado="f.estado_factura" /><span v-if="f.pendientes_factura" class="sub">{{ t('{0} fields to complete', [f.pendientes_factura]) }}</span></td>
          <td>
            <template v-if="f.pl_id">
              <router-link :to="`/packing-lists/${f.pl_id}`" class="cajas-rango">{{ tx(f.pl) }}</router-link> <EstadoBadge :estado="f.estado_pl" />
            </template>
            <span v-else class="ayuda">{{ t('No packing list') }}</span>
          </td>
          <td style="min-width: 100px"><Avance v-if="f.pl_id" :porcentaje="f.avance" /><span v-else class="ayuda">—</span></td>
          <td class="num">{{ fmtNum(f.cajas) }}<template v-if="f.pallets"> {{ t('· {0} pallets', [f.pallets]) }}</template><span class="sub">{{ t('{0} kg · {1} m³', [fmtNum(f.peso_bruto, 1), fmtNum(f.cbm, 2)]) }}</span></td>
          <td class="num"><span v-if="f.pendientes" class="etiqueta aviso">{{ tx(f.pendientes) }}</span><span v-else class="ayuda">0</span></td>
          <td><span class="etiqueta" :class="TONO[f.etapa]" style="margin-inline-start: 0">{{ tx(nombreEtapa[f.etapa] || f.etapa) }}</span></td>
          <td class="ajustar">
            <template v-if="f.embarque_id">
              <span class="codigo">{{ tx(f.contenedor) }}</span>
              <span class="sub">
                <router-link v-if="esInterno()" :to="`/transporte/embarques/${f.embarque_id}`">{{ tx(f.embarque) }}</router-link><template v-else>{{ tx(f.embarque) }}</template>
                {{ t('· ETA {0}', [fmtFecha(f.eta)]) }}
              </span>
            </template>
            <span v-else class="ayuda">—</span>
          </td>
          <td class="num">{{ tx(f.dias ?? '—') }}<span class="sub">{{ fmtFecha(f.fecha) }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total"
              @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
</template>
