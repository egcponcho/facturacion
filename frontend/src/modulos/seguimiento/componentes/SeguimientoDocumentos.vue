<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { api } from '@/nucleo/api'
import { esInterno, sesion } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { fmtFecha, fmtMoneda, fmtNum } from '@/nucleo/utils'
import Avance from '@/componentes/Avance.vue'
import BotonesExportar from '@/componentes/BotonesExportar.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import GraficoColumnas from '@/componentes/GraficoColumnas.vue'
import Kpi from '@/componentes/Kpi.vue'
import Icono from '@/componentes/Icono.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'

// Filtros de varios valores: se guardan como texto separado por comas
const lst = (v) => (v ? String(v).split(',').filter(Boolean) : [])

// Seguimiento de facturación y empaque: una fila por packing list (o por
// factura sin PL), con el paso en que va y lo que le falta.
const filtros = reactive({
  q: '', etapa: '', estado_factura: '', estado_pl: '', sociedad: '', centro: '', embarque_id: '', proveedor: '',
  con_pendientes: false,
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
// Filtros de la pantalla (los de cada columna los pone la tabla)
const base = () => {
  const p = { proveedor_id: sesion.proveedorId || undefined }
  for (const [k, v] of Object.entries(filtros)) if (v !== '' && v !== false) p[k] = v === true ? '1' : v
  return p
}
const tablaD = ref(null)
let ultima = null
const paramsExportar = computed(() => ({ ...base(), orden: ultima?.orden || undefined,
  f: ultima && Object.keys(ultima.filtros).length ? JSON.stringify(ultima.filtros) : undefined }))
async function cargar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/documentos', { ...base(), orden: c.orden || 'dias:desc', page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const valores = (columna, buscar, otros) => api.get('/seguimiento/documentos/valores', { ...base(), columna, buscar, f: JSON.stringify(otros) })
// Un filtro de la pantalla vuelve a la primera página
function aplicar() {
  if (tablaD.value && tablaD.value.pagina !== 1) tablaD.value.pagina = 1
  else cargar()
}
const ESTADOS_DOC = [['BORRADOR', t('Draft')], ['EN_CORRECCION', t('In correction')], ['FINALIZADA', t('Finalized')], ['FINALIZADO', t('Finalized')]]
const columnas = computed(() => [
  { clave: 'factura', texto: t('Invoice'), fija: true, prioridad: 1 },
  ...(sesion.proveedorId ? [] : [{ clave: 'proveedor', texto: t('Supplier'), prioridad: 2 }]),
  { clave: 'centro', texto: t('Bill to / notify'), prioridad: 3, inicial: false },
  { clave: 'estado_factura', texto: t('Invoice status'), prioridad: 2, opciones: ESTADOS_DOC },
  { clave: 'estado_pl', texto: t('Packing list'), prioridad: 2, opciones: ESTADOS_DOC },
  { clave: 'avance', texto: t('Packed'), prioridad: 3, textoValor: (v) => `${v}%` },
  { clave: 'cajas', texto: t('Cartons · kg · m³'), num: true, prioridad: 3, inicial: false },
  { clave: 'pendientes', texto: t('Pending'), num: true, prioridad: 2 },
  { clave: 'etapa', texto: t('Step'), prioridad: 1, opciones: datos.value.etapas.map((e) => [e.clave, e.nombre]) },
  { clave: 'embarque', texto: t('Load unit'), prioridad: 3 },
  { clave: 'dias', texto: t('Days'), num: true, prioridad: 3 },
])
const masActivos = computed(() => [filtros.sociedad, filtros.centro, filtros.estado_pl, filtros.embarque_id].filter(Boolean).length)
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(aplicar, 300)
}
watch(() => sesion.proveedorId, aplicar)
</script>

<template>
  <section class="kpis mb-4">
    <Kpi :titulo="t('Invoices')" :valor="datos.kpis.facturas" icono="factura" :detalle="tx(importeTxt)" @abrir="filtrar({})" />
    <Kpi :titulo="t('Open invoices')" :valor="datos.kpis.facturas_abiertas" icono="editar" :tono="datos.kpis.facturas_abiertas ? 'alerta' : 'exito'"
         :detalle="t('draft or in correction')" @abrir="filtrar({ estado_factura: 'BORRADOR' })" />
    <Kpi :titulo="t('Packing')" :valor="datos.kpis.empacando" icono="caja" :detalle="t('PL not finalized')" @abrir="filtrar({ etapa: 'EMPACANDO' })" />
    <Kpi :titulo="t('Ready to ship')" :valor="datos.kpis.listos" icono="check" tono="exito" :detalle="t('invoice and PL finalized')" @abrir="filtrar({ etapa: 'LISTO_EMBARQUE' })" />
    <Kpi :titulo="t('With pending data')" :valor="datos.kpis.con_pendientes" icono="alerta" :tono="datos.kpis.con_pendientes ? 'alerta' : 'exito'"
         :detalle="t('needed to finalize')" @abrir="filtrar({ con_pendientes: true })" />
  </section>
  <div class="dos-columnas mb-4">
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


  <TablaDatos ref="tablaD" tabla="seguimiento_documentos" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              :clave-fila="(f) => `${f.factura_id}-${f.pl_id}`" :valores="valores" :mas-filtros-activos="masActivos" :externos="{ q: filtros.q, etapa: filtros.etapa }"
              :etiqueta="t('Invoices and packing lists')" @consulta="cargar" @vista="(x) => { Object.assign(filtros, { q: x.q || '', etapa: x.etapa || '' }); aplicar() }">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="t('Invoice, PL, PO or container')" :aria-label="t('Search')" @input="buscar" />
      </label>
    </template>
    <template #filtros>
      <SelectBusqueda v-if="esInterno()" multiple :model-value="lst(filtros.proveedor)" @update:model-value="(v) => (filtros.proveedor = v.join(','))" :opciones="datos.opciones.proveedores || []" :vacio="t('Supplier: all')" :etiqueta="t('Supplier')" @change="aplicar" />
      <Seleccion v-model="filtros.estado_factura" :aria-label="t('Invoice status')" @change="aplicar">
        <option value="">{{ t('Invoice: all') }}</option><option value="BORRADOR">{{ t('Draft') }}</option>
        <option value="EN_CORRECCION">{{ t('In correction') }}</option><option value="FINALIZADA">{{ t('Finalized') }}</option>
      </Seleccion>
      <label class="check"><input v-model="filtros.con_pendientes" type="checkbox" @change="aplicar" /> {{ t('Only with pending data') }}</label>
      <BotonesExportar class="separar" ruta="/seguimiento/documentos/exportar" :params="paramsExportar" />
    </template>
    <template #mas-filtros>
      <SelectBusqueda v-if="(datos.opciones.sociedades || []).length > 1 || filtros.sociedad" multiple :model-value="lst(filtros.sociedad)" @update:model-value="(v) => (filtros.sociedad = v.join(','))" :opciones="datos.opciones.sociedades || []" :vacio="t('Bill to: all')" :etiqueta="t('Company')" @change="aplicar" />
      <SelectBusqueda v-if="(datos.opciones.centros || []).length > 1 || filtros.centro" multiple :model-value="lst(filtros.centro)" @update:model-value="(v) => (filtros.centro = v.join(','))" :opciones="datos.opciones.centros || []" :vacio="t('Plant: all')" :etiqueta="t('Plant')" @change="aplicar" />
      <Seleccion v-model="filtros.estado_pl" :aria-label="t('Packing list status')" @change="aplicar">
        <option value="">{{ t('Packing list: all') }}</option><option value="BORRADOR">{{ t('Draft') }}</option>
        <option value="EN_CORRECCION">{{ t('In correction') }}</option><option value="FINALIZADO">{{ t('Finalized') }}</option>
      </Seleccion>
      <SelectBusqueda multiple :model-value="lst(filtros.embarque_id)" @update:model-value="(v) => (filtros.embarque_id = v.join(','))" :opciones="(datos.opciones.embarques || []).map((e) => ({ valor: String(e.id), texto: e.codigo }))"
                      :vacio="t('Shipment: all')" :etiqueta="t('Shipment')" @change="aplicar" />
    </template>
    <template #celda-factura="{ fila: f }">
      <router-link :to="`/facturas/${f.factura_id}`" class="enlace-doc"><strong class="codigo">{{ tx(f.factura) }}</strong></router-link>
      <span class="sub codigo">{{ tx(f.ocs.join(', ')) }}</span>
    </template>
    <template #celda-proveedor="{ fila: f }">{{ tx(f.proveedor) }}</template>
    <template #celda-centro="{ fila: f }"><span class="codigo">{{ tx(f.sociedad) }} · {{ tx(f.centro || '—') }}</span><span class="sub">{{ t('destination {0} · {1}', [f.centro_destino || '—', fmtMoneda(f.importe, f.moneda)]) }}</span></template>
    <template #celda-estado_factura="{ fila: f }"><EstadoBadge :estado="f.estado_factura" /><span v-if="f.pendientes_factura" class="sub">{{ t('{0} fields to complete', [f.pendientes_factura]) }}</span></template>
    <template #celda-estado_pl="{ fila: f }">
      <template v-if="f.pl_id">
        <router-link :to="`/packing-lists/${f.pl_id}`" class="enlace codigo">{{ tx(f.pl) }}</router-link> <EstadoBadge :estado="f.estado_pl" />
      </template>
      <span v-else class="ayuda">{{ t('No packing list') }}</span>
    </template>
    <template #celda-avance="{ fila: f }"><div class="avance-doc"><Avance v-if="f.pl_id" :porcentaje="f.avance" /><span v-else class="ayuda">—</span></div></template>
    <template #celda-cajas="{ fila: f }">{{ fmtNum(f.cajas) }}<template v-if="f.pallets"> {{ t('· {0} pallets', [f.pallets]) }}</template><span class="sub">{{ t('{0} kg · {1} m³', [fmtNum(f.peso_bruto, 1), fmtNum(f.cbm, 2)]) }}</span></template>
    <template #celda-pendientes="{ fila: f }"><span v-if="f.pendientes" class="etiqueta aviso">{{ tx(f.pendientes) }}</span><span v-else class="ayuda">0</span></template>
    <template #celda-etapa="{ fila: f }"><span class="etiqueta ms-0" :class="TONO[f.etapa]">{{ tx(nombreEtapa[f.etapa] || f.etapa) }}</span></template>
    <template #celda-embarque="{ fila: f }">
      <template v-if="f.embarque_id">
        <span class="codigo">{{ tx(f.contenedor) }}</span>
        <span class="sub">
          <router-link v-if="esInterno()" :to="`/transporte/embarques/${f.embarque_id}`" class="enlace codigo">{{ tx(f.embarque) }}</router-link><template v-else>{{ tx(f.embarque) }}</template>
          {{ t('· ETA {0}', [fmtFecha(f.eta)]) }}
        </span>
      </template>
      <span v-else class="ayuda">—</span>
    </template>
    <template #celda-dias="{ fila: f }">{{ tx(f.dias ?? '—') }}<span class="sub">{{ fmtFecha(f.fecha) }}</span></template>
    <template #vacio>{{ t('No documents match these filters.') }}</template>
  </TablaDatos>
</template>

<style scoped>
.avance-doc { min-width: 100px; }
</style>
