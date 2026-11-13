<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import BarraSeleccion from '@/componentes/BarraSeleccion.vue'
import CampoFecha from '@/componentes/CampoFecha.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede, sesion } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtCant, fmtFecha, fmtMoneda, fmtNum } from '@/nucleo/utils'
import GraficoPagosSemana from '../componentes/GraficoPagosSemana.vue'

// Facturas y pagos a proveedores (diseño v3): las facturas finalizadas por
// pagar con su vencimiento, saldo y el cuadre de tres vías (OC = factura =
// recibido), los pagos de las próximas semanas y la antigüedad del saldo. Se
// eligen facturas para programar su pago; cada factura se abre en un panel con
// el cuadre línea por línea y sus pagos (pagar, anular, cambiar vencimiento).
const route = useRoute()
const router = useRouter()
const VISTAS_VALIDAS = ['por_pagar', 'diferencias', 'pagadas', 'todas']
const vista = ref(VISTAS_VALIDAS.includes(route.query.vista) ? route.query.vista : 'por_pagar')
const datos = ref({ items: [], cuentas: {}, truncado: false })
const resumen = ref(null)
const cargando = ref(false)
const seleccion = ref([])
const gestiona = computed(() => puede('pago.gestionar'))

async function cargar() {
  cargando.value = true
  try {
    const prov = sesion.proveedorId || undefined
    const [l, r] = await Promise.all([
      api.get('/pagos/facturas', { vista: vista.value, proveedor_id: prov }),
      api.get('/pagos/resumen', { proveedor_id: prov }).catch(() => null), // sin ver precios no hay resumen
    ])
    datos.value = l
    resumen.value = r
  } catch (err) {
    errorApi(err)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)
alCambiar(() => cargar(), ['/pagos', '/facturas', '/recepciones'])
function cambiarVista(v) {
  seleccion.value = []
  router.replace({ query: v === 'por_pagar' ? {} : { vista: v } })
  cargar()
}

const VISTAS = computed(() => [
  ['por_pagar', t('To pay'), datos.value.cuentas.por_pagar],
  ['diferencias', t('With differences'), datos.value.cuentas.diferencias],
  ['pagadas', t('Paid invoices'), datos.value.cuentas.pagadas],
  ['todas', t('All invoices'), datos.value.cuentas.todas],
])

// Cuadre y estado de pago: texto y tono (con su marca, nunca solo color)
const CUADRE = {
  CUADRA: [t('PO = invoice = received'), 'ok'],
  POR_RECIBIR: [t('Not fully received'), 'neutro'],
  PRECIO: [t('Price differs from PO'), 'error'],
  CANTIDAD: [t('Received ≠ invoiced'), 'aviso'],
}
const PAGO = {
  PENDIENTE: [t('Pending'), 'aviso'], PROGRAMADA: [t('Scheduled'), 'info'],
  VENCIDA: [t('Overdue'), 'error'], PAGADA: [t('Paid'), 'ok'],
}
const ESTADO_PAGO = { PROGRAMADO: [t('Scheduled'), 'info'], PAGADO: [t('Paid'), 'ok'], ANULADO: [t('Voided'), 'neutro'] }
const dinero = (v, m) => fmtMoneda(v, m)

const columnas = [
  { clave: 'numero', texto: t('Invoice'), fija: true, prioridad: 1 },
  { clave: 'proveedor', texto: t('Supplier'), prioridad: 1, textoValor: (v) => v?.nombre || '', exporta: (f) => f.proveedor.nombre },
  { clave: 'ocs', texto: t('PO'), prioridad: 3, textoValor: (v) => (v || []).join(', '), exporta: (f) => f.ocs.join(', ') },
  { clave: 'fecha', texto: t('Issued'), prioridad: 3, textoValor: (v) => fmtFecha(v) },
  { clave: 'vence', texto: t('Due'), prioridad: 2, textoValor: (v) => fmtFecha(v) },
  { clave: 'importe', texto: t('Amount'), num: true, prioridad: 2 },
  { clave: 'saldo', texto: t('Balance'), num: true, prioridad: 1 },
  { clave: 'cuadre', texto: t('PO / invoice / receipt'), prioridad: 2, textoValor: (v) => CUADRE[v]?.[0] || v },
  { clave: 'estado_pago', texto: t('Status'), prioridad: 1, textoValor: (v) => PAGO[v]?.[0] || v },
]

// ---- Antigüedad del saldo ----
const TRAMOS = { por_vencer: [t('Not yet due'), 'ok'], '1_15': [t('1–15 days'), 'aviso'], '16_30': [t('16–30 days'), 'aviso'], mas_30: [t('Over 30 days'), 'error'] }

// ---- Programar pagos de las facturas elegidas ----
const modal = ref(null)
const ocupado = ref(false)
const hoyIso = () => new Date().toISOString().slice(0, 10)
const elegidas = computed(() => datos.value.items.filter((f) => seleccion.value.includes(f.id)))
const puedeProgramar = (f) => f.estado_pago !== 'PAGADA' && f.saldo > f.programado
function abrirProgramar() {
  const proximo = elegidas.value.map((f) => f.vence).filter(Boolean).sort()[0]
  modal.value = { tipo: 'programar', fecha: proximo && proximo > hoyIso() ? proximo : hoyIso() }
}
async function programar() {
  ocupado.value = true
  try {
    const r = await api.post('/pagos/programar', { factura_ids: seleccion.value, fecha: modal.value.fecha })
    avisar(t('{0} payments scheduled', [r.programados]))
    modal.value = null
    seleccion.value = []
    await cargar()
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}

// ---- Panel de una factura ----
const abierta = ref(null)
async function abrir(f) {
  try {
    abierta.value = await api.get(`/pagos/facturas/${f.id}`)
  } catch (err) {
    errorApi(err)
  }
}
async function accion(fn, mensaje) {
  ocupado.value = true
  try {
    abierta.value = await fn()
    avisar(mensaje)
    modal.value = null
    await cargar()
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}
const pagar = () => accion(() => api.post(`/pagos/${modal.value.pago.id}/pagar`, { fecha: modal.value.fecha, referencia: modal.value.referencia }), t('Payment recorded'))
const anular = (p) => accion(() => api.post(`/pagos/${p.id}/anular`), t('Payment voided'))
const guardarVence = () => accion(() => api.put(`/pagos/facturas/${abierta.value.id}/vence`, { vence: modal.value.vence || null }), t('Due date saved'))
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Invoices and payments') }}</h1>
      <p>{{ t('Three-way match: purchase order, supplier invoice and warehouse receipt.') }}</p>
    </div>
    <div v-if="gestiona" class="acciones">
      <button type="button" class="btn btn-primario" :disabled="!seleccion.length" @click="abrirProgramar"><Icono nombre="calendario" />{{ t('Schedule payments') }}</button>
    </div>
  </div>

  <div v-if="resumen" class="pagos-arriba mb">
    <GraficoPagosSemana :resumen="resumen" />
    <section class="panel" :aria-label="t('Balance aging')">
      <div class="panel-cabeza"><h2>{{ t('Balance aging') }}</h2></div>
      <ul class="tramos">
        <li v-for="tr in resumen.antiguedad" :key="tr.tramo">
          <span>{{ TRAMOS[tr.tramo][0] }}</span>
          <span class="tramo-barra" aria-hidden="true"><i :class="`tono-${TRAMOS[tr.tramo][1]}`" :style="{ width: `${tr.porcentaje}%` }"></i></span>
          <b>{{ fmtNum(tr.porcentaje, 1) }} %</b>
          <span class="sub">{{ dinero(tr.importe, resumen.moneda) }}</span>
        </li>
      </ul>
      <p class="ayuda">{{ t('Balance to pay: {0}', [dinero(resumen.saldo, resumen.moneda)]) }}</p>
      <p v-if="resumen.otras?.length" class="ayuda">{{ t('Also in other currencies (not in the chart): {0}', [resumen.otras.map((o) => dinero(o.valor, o.moneda)).join(' · ')]) }}</p>
    </section>
  </div>

  <p v-if="datos.truncado" class="nota aviso mb"><Icono nombre="alerta" />{{ t('Only the most recent invoices are shown.') }}</p>

  <TablaDatos :key="vista" :tabla="`pagos-${vista}`" :columnas="columnas" :filas="datos.items" clave-fila="id" :cargando="cargando"
              :etiqueta="t('Invoices and payments')" :seleccionable="gestiona && vista !== 'pagadas'" :puede-seleccionar="puedeProgramar"
              v-model:seleccion="seleccion" fila-clicable @fila="abrir">
    <template #barra>
      <Segmentos v-model="vista" :opciones="VISTAS" :etiqueta="t('View')" @change="cambiarVista" />
    </template>
    <template #celda-numero="{ fila: f }"><b class="codigo enlace">{{ tx(f.numero || `#${f.id}`) }}</b></template>
    <template #celda-proveedor="{ fila: f }">{{ tx(f.proveedor.nombre) }}</template>
    <template #celda-ocs="{ fila: f }"><span class="codigo">{{ tx(f.ocs.join(', ')) }}</span></template>
    <template #celda-fecha="{ fila: f }">{{ fmtFecha(f.fecha) }}</template>
    <template #celda-vence="{ fila: f }"><span :class="{ 'texto-error': f.estado_pago === 'VENCIDA' }">{{ fmtFecha(f.vence) }}</span></template>
    <template #celda-importe="{ fila: f }">{{ dinero(f.importe, f.moneda) }}</template>
    <template #celda-saldo="{ fila: f }"><b>{{ dinero(f.saldo, f.moneda) }}</b></template>
    <template #celda-cuadre="{ fila: f }"><span class="estado" :class="`estado-${CUADRE[f.cuadre][1]}`"><span class="estado-marca" aria-hidden="true"></span>{{ CUADRE[f.cuadre][0] }}</span></template>
    <template #celda-estado_pago="{ fila: f }">
      <span class="estado" :class="`estado-${PAGO[f.estado_pago][1]}`"><span class="estado-marca" aria-hidden="true"></span>{{ PAGO[f.estado_pago][0] }}</span>
      <span v-if="f.proximo_pago && f.estado_pago !== 'PAGADA'" class="sub">{{ fmtFecha(f.proximo_pago) }}</span>
    </template>
    <template #vacio>
      <Icono nombre="archivador" :tam="28" />
      <p>{{ t('No invoices in this view. Invoices appear here when the supplier finalizes them.') }}</p>
    </template>
  </TablaDatos>

  <BarraSeleccion :cantidad="seleccion.length" :singular="t('invoice selected')" :plural="t('invoices selected')" @limpiar="seleccion = []">
    <button type="button" class="btn btn-primario btn-chico" @click="abrirProgramar">{{ t('Schedule payments') }}</button>
  </BarraSeleccion>

  <PanelLateral v-if="abierta" :titulo="t('Invoice {0}', [abierta.numero || `#${abierta.id}`])" :detalle="`/facturas/${abierta.id}`" ancho="720px" @cerrar="abierta = null">
    <template #estado><span class="ayuda">{{ tx(abierta.proveedor.nombre) }} · {{ tx(abierta.ocs.join(', ')) }}</span></template>
    <dl class="datos-grilla">
      <div><dt>{{ t('Amount') }}</dt><dd>{{ dinero(abierta.importe, abierta.moneda) }}</dd></div>
      <div><dt>{{ t('Paid') }}</dt><dd>{{ dinero(abierta.pagado, abierta.moneda) }}</dd></div>
      <div><dt>{{ t('Balance') }}</dt><dd><b>{{ dinero(abierta.saldo, abierta.moneda) }}</b></dd></div>
      <div><dt>{{ t('Due') }}</dt><dd>{{ fmtFecha(abierta.vence) }}<span v-if="!abierta.vence_propio" class="sub">{{ t('From the payment terms') }}</span>
        <button v-if="gestiona" type="button" class="btn-texto" @click="modal = { tipo: 'vence', vence: abierta.vence_propio ? abierta.vence : '' }">{{ t('Change') }}</button></dd></div>
    </dl>

    <h3 class="mt">{{ t('Three-way match') }}</h3>
    <p class="ayuda"><span class="estado" :class="`estado-${CUADRE[abierta.cuadre][1]}`"><span class="estado-marca" aria-hidden="true"></span>{{ CUADRE[abierta.cuadre][0] }}</span></p>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>{{ t('PO line') }}</th><th>{{ t('Item') }}</th><th class="num">{{ t('PO price') }}</th><th class="num">{{ t('Invoice price') }}</th>
          <th class="num">{{ t('Invoiced') }}</th><th class="num">{{ t('Received') }}</th></tr></thead>
        <tbody>
          <tr v-for="l in abierta.lineas" :key="l.id">
            <td class="codigo">{{ tx(l.oc) }} · {{ tx(l.posicion) }}</td>
            <td><span class="codigo">{{ tx(l.codigo) }}</span><span class="sub">{{ tx(l.descripcion || '') }}</span></td>
            <td class="num">{{ dinero(l.precio_oc, abierta.moneda) }}</td>
            <td class="num" :class="{ 'texto-error': l.dif_precio }">{{ dinero(l.precio, abierta.moneda) }}<Icono v-if="l.dif_precio" nombre="alerta" :tam="14" /></td>
            <td class="num">{{ fmtCant(l.facturado) }} {{ tx(l.unidad) }}</td>
            <td class="num" :class="{ 'texto-aviso': l.dif_cantidad }">{{ fmtCant(l.recibido) }}<Icono v-if="l.dif_cantidad" nombre="alerta" :tam="14" /></td>
          </tr>
        </tbody>
      </table>
    </div>

    <h3 class="mt">{{ t('Payments') }}</h3>
    <p v-if="!abierta.pagos.length" class="ayuda">{{ t('No payments yet.') }}</p>
    <ul v-else class="lista-pagos">
      <li v-for="p in abierta.pagos" :key="p.id">
        <span><b>{{ dinero(p.importe, abierta.moneda) }}</b>
          <span class="sub">{{ p.estado === 'PAGADO' ? t('Paid on {0}', [fmtFecha(p.fecha_pago)]) : t('For {0}', [fmtFecha(p.fecha_programada)]) }}<template v-if="p.referencia"> · {{ tx(p.referencia) }}</template></span></span>
        <span class="estado" :class="`estado-${ESTADO_PAGO[p.estado][1]}`"><span class="estado-marca" aria-hidden="true"></span>{{ ESTADO_PAGO[p.estado][0] }}</span>
        <span v-if="gestiona && p.estado === 'PROGRAMADO'" class="fila-flex gap-2">
          <button type="button" class="btn btn-chico" :disabled="ocupado" @click="modal = { tipo: 'pagar', pago: p, fecha: hoyIso(), referencia: '' }">{{ t('Mark paid') }}</button>
          <button type="button" class="btn btn-chico btn-fantasma" :disabled="ocupado" @click="anular(p)">{{ t('Void') }}</button>
        </span>
      </li>
    </ul>
  </PanelLateral>

  <Modal v-if="modal?.tipo === 'programar'" :titulo="t('Schedule payments')" @cerrar="modal = null">
    <p>{{ t('The unscheduled balance of {0} invoices is scheduled for this date.', [elegidas.length]) }}</p>
    <label class="campo">{{ t('Payment date') }}<CampoFecha v-model="modal.fecha" required /></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.fecha" @click="programar">{{ t('Schedule') }}</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'pagar'" :titulo="t('Mark paid')" @cerrar="modal = null">
    <label class="campo">{{ t('Payment date') }}<CampoFecha v-model="modal.fecha" required /></label>
    <label class="campo">{{ t('Reference') }}<input v-model="modal.referencia" maxlength="80" :placeholder="t('Transfer or check number')" /></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.fecha" @click="pagar">{{ t('Mark paid') }}</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'vence'" :titulo="t('Due date')" @cerrar="modal = null">
    <label class="campo">{{ t('Due date') }}<CampoFecha v-model="modal.vence" /></label>
    <p class="ayuda">{{ t('Leave it empty to use the payment terms of the PO.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="guardarVence">{{ t('Save') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.pagos-arriba > * { margin: 0; }
.pagos-arriba { display: grid; grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr); gap: 16px; align-items: start; }
@media (max-width: 1100px) { .pagos-arriba { grid-template-columns: minmax(0, 1fr); } }
.tramos { list-style: none; margin: 0 0 8px; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.tramos li { display: grid; grid-template-columns: 1fr 90px 52px; grid-template-rows: auto auto; column-gap: 10px; align-items: center; font-size: var(--t-sm); }
.tramos li .sub { grid-column: 1 / -1; }
.tramos b { text-align: right; font-variant-numeric: tabular-nums; }
.tramo-barra { height: 6px; border-radius: 3px; background: var(--papel); overflow: hidden; }
.tramo-barra i { display: block; height: 100%; border-radius: 3px; }
.tono-ok { background: var(--ok); }
.tono-aviso { background: var(--aviso); }
.tono-error { background: var(--error); }
.datos-grilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 0; }
.datos-grilla dt { font-size: var(--t-sm); color: var(--tinta-3); }
.datos-grilla dd { margin: 2px 0 0; }
.lista-pagos { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.lista-pagos li { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--linea); }
.lista-pagos li > span:first-child { flex: 1; display: flex; flex-direction: column; }
.campo { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
</style>
