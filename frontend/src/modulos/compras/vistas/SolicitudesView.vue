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
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede, sesion } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtCant, fmtFecha, fmtMoneda } from '@/nucleo/utils'

// Solicitudes de compra (diseño v3): lo que piden las áreas antes de la OC.
// Por aprobar / Aprobadas / Todas; cada solicitud se abre en un panel con sus
// artículos y las acciones que permite su estado. Las aprobadas se eligen y se
// convierten en una OC en borrador, que sigue en el asistente de la OC.
const route = useRoute()
const router = useRouter()
const VALIDAS = ['por_aprobar', 'aprobadas', 'todas']
const vista = ref(VALIDAS.includes(route.query.vista) ? route.query.vista : 'por_aprobar')
const datos = ref({ items: [], cuentas: {} })
const cargando = ref(false)
const seleccion = ref([])
const crea = computed(() => puede('solicitud.crear'))
const convierte = computed(() => puede('solicitud.aprobar') && puede('oc.editar'))

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/solicitudes', { vista: vista.value })
  } catch (err) {
    errorApi(err)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)
alCambiar(() => cargar(), ['/solicitudes'])
function cambiarVista(v) {
  seleccion.value = []
  router.replace({ query: v === 'por_aprobar' ? {} : { vista: v } })
  cargar()
}

const VISTAS = computed(() => [
  ['por_aprobar', t('To approve'), datos.value.cuentas.por_aprobar],
  ['aprobadas', t('Approved requests'), datos.value.cuentas.aprobadas],
  ['todas', t('All requests'), datos.value.cuentas.todas],
])
const ESTADOS = {
  PENDIENTE: [t('Pending'), 'aviso'], APROBADA: [t('Approved'), 'ok'], RECHAZADA: [t('Rejected'), 'error'],
  CONVERTIDA: [t('Converted to PO'), 'info'], CANCELADA: [t('Cancelled'), 'neutro'],
}
const PRIORIDAD = { NORMAL: t('Normal'), URGENTE: t('Urgent') }
const columnas = [
  { clave: 'numero', texto: t('Request'), fija: true, prioridad: 1 },
  { clave: 'area', texto: t('Area'), prioridad: 1 },
  { clave: 'solicitante', texto: t('Requested by'), prioridad: 3 },
  { clave: 'fecha', texto: t('Date'), prioridad: 2, textoValor: (v) => fmtFecha(v) },
  { clave: 'articulos', texto: t('Items'), num: true, prioridad: 3 },
  { clave: 'estimado', texto: t('Estimate'), num: true, prioridad: 2 },
  { clave: 'prioridad', texto: t('Priority'), prioridad: 2, textoValor: (v) => PRIORIDAD[v] || v },
  { clave: 'estado', texto: t('Status'), prioridad: 1, textoValor: (v) => ESTADOS[v]?.[0] || v },
  { clave: 'oc', texto: t('PO'), prioridad: 3, textoValor: (v) => v?.numero || '', exporta: (f) => f.oc?.numero || '' },
]
const puedeElegir = (f) => f.estado === 'APROBADA'

// ---- Panel: ver una solicitud ----
const abierta = ref(null)
const ocupado = ref(false)
async function abrir(f) {
  try {
    abierta.value = await api.get(`/solicitudes/${f.id}`)
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
const aprobar = () => accion(() => api.post(`/solicitudes/${abierta.value.id}/aprobar`, {}), t('Request approved'))
const rechazar = () => accion(() => api.post(`/solicitudes/${abierta.value.id}/rechazar`, { comentario: modal.value.comentario }), t('Request rejected'))
const cancelar = () => accion(() => api.post(`/solicitudes/${abierta.value.id}/cancelar`), t('Request cancelled'))

// ---- Formulario: nueva o corregir ----
const form = ref(null)
const lineaVacia = () => ({ codigo_articulo: '', descripcion: '', cantidad: null, unidad: '', precio_estimado: null })
function nueva() {
  form.value = { id: null, area: '', prioridad: 'NORMAL', fecha_requerida: '', proveedor_id: '', motivo: '', lineas: [lineaVacia()] }
}
function corregir() {
  const s = abierta.value
  form.value = { id: s.id, area: s.area, prioridad: s.prioridad, fecha_requerida: s.fecha_requerida || '', proveedor_id: s.proveedor?.id || '',
    motivo: s.motivo || '', lineas: s.lineas.map((l) => ({ ...l, codigo_articulo: l.codigo_articulo || '', unidad: l.unidad || '' })) }
  abierta.value = null
}
const errores = ref({})
async function guardar() {
  ocupado.value = true
  errores.value = {}
  const f = form.value
  const cuerpo = { ...f, proveedor_id: f.proveedor_id || null, fecha_requerida: f.fecha_requerida || null }
  try {
    const s = f.id ? await api.put(`/solicitudes/${f.id}`, cuerpo) : await api.post('/solicitudes', cuerpo)
    avisar(f.id ? t('Request saved') : t('Request {0} sent for approval', [s.numero]))
    form.value = null
    abierta.value = s
    await cargar()
  } catch (err) {
    errores.value = Object.fromEntries((err?.detalle || []).map((e) => [e.campo, e.mensaje]))
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}
const opcionesProveedor = computed(() => sesion.proveedores.map((p) => ({ valor: p.id, texto: p.nombre })))
const totalForm = computed(() => (form.value?.lineas || []).reduce((s, l) => s + (Number(l.cantidad) || 0) * (Number(l.precio_estimado) || 0), 0))

// ---- Convertir en OC ----
const modal = ref(null)
const elegidas = computed(() => datos.value.items.filter((f) => seleccion.value.includes(f.id)))
function abrirConvertir(ids = seleccion.value) {
  const sugerido = datos.value.items.find((f) => ids.includes(f.id) && f.proveedor)?.proveedor?.id || abierta.value?.proveedor?.id || ''
  modal.value = { tipo: 'convertir', ids, proveedor_id: sugerido, oc: '' }
}
async function convertir() {
  ocupado.value = true
  try {
    const r = await api.post('/solicitudes/convertir', { solicitud_ids: modal.value.ids, proveedor_id: Number(modal.value.proveedor_id), oc: modal.value.oc })
    avisar(t('PO {0} created as a draft', [r.numero]))
    router.push(`/ordenes/${r.oc_id}/editar`)
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Purchase requests') }}</h1>
      <p>{{ t('What the areas request before it becomes a purchase order.') }}</p>
    </div>
    <div class="acciones">
      <button v-if="convierte" type="button" class="btn" :disabled="!seleccion.length" @click="abrirConvertir()"><Icono nombre="ordenes" />{{ t('Convert to PO') }}</button>
      <button v-if="crea" type="button" class="btn btn-primario" @click="nueva"><Icono nombre="mas" />{{ t('New request') }}</button>
    </div>
  </div>

  <TablaDatos :key="vista" :tabla="`solicitudes-${vista}`" :columnas="columnas" :filas="datos.items" clave-fila="id" :cargando="cargando"
              :etiqueta="t('Purchase requests')" :seleccionable="convierte && vista !== 'por_aprobar'" :puede-seleccionar="puedeElegir"
              v-model:seleccion="seleccion" fila-clicable @fila="abrir">
    <template #barra>
      <Segmentos v-model="vista" :opciones="VISTAS" :etiqueta="t('View')" @change="cambiarVista" />
    </template>
    <template #celda-numero="{ fila: f }"><b class="codigo enlace">{{ tx(f.numero) }}</b></template>
    <template #celda-area="{ fila: f }">{{ tx(f.area) }}<span v-if="f.proveedor" class="sub">{{ tx(f.proveedor.nombre) }}</span></template>
    <template #celda-solicitante="{ fila: f }">{{ tx(f.solicitante || '') }}</template>
    <template #celda-fecha="{ fila: f }">{{ fmtFecha(f.fecha) }}</template>
    <template #celda-estimado="{ fila: f }">{{ f.estimado ? fmtMoneda(f.estimado, f.moneda) : '—' }}</template>
    <template #celda-prioridad="{ fila: f }"><b v-if="f.prioridad === 'URGENTE'" class="texto-aviso">{{ PRIORIDAD[f.prioridad] }}</b><template v-else>{{ PRIORIDAD[f.prioridad] }}</template></template>
    <template #celda-estado="{ fila: f }"><span class="estado" :class="`estado-${ESTADOS[f.estado][1]}`"><span class="estado-marca" aria-hidden="true"></span>{{ ESTADOS[f.estado][0] }}</span></template>
    <template #celda-oc="{ fila: f }"><router-link v-if="f.oc" :to="`/ordenes/${f.oc.id}`" class="enlace codigo" @click.stop>{{ tx(f.oc.numero) }}</router-link><span v-else class="sub">—</span></template>
    <template #vacio>
      <Icono nombre="bandeja" :tam="28" />
      <p>{{ t('No requests in this view.') }}</p>
    </template>
  </TablaDatos>

  <BarraSeleccion :cantidad="seleccion.length" :singular="t('request selected')" :plural="t('requests selected')" @limpiar="seleccion = []">
    <button type="button" class="btn btn-primario btn-chico" @click="abrirConvertir()">{{ t('Convert to PO') }}</button>
  </BarraSeleccion>

  <!-- Una solicitud -->
  <PanelLateral v-if="abierta" :titulo="t('Request {0}', [abierta.numero])" ancho="640px" @cerrar="abierta = null">
    <template #estado><span class="estado estado-cabeza" :class="`estado-${ESTADOS[abierta.estado][1]}`"><span class="estado-marca" aria-hidden="true"></span>{{ ESTADOS[abierta.estado][0] }}</span></template>
    <dl class="datos-grilla">
      <div><dt>{{ t('Area') }}</dt><dd>{{ tx(abierta.area) }}</dd></div>
      <div><dt>{{ t('Requested by') }}</dt><dd>{{ tx(abierta.solicitante || '—') }}</dd></div>
      <div><dt>{{ t('Priority') }}</dt><dd>{{ PRIORIDAD[abierta.prioridad] }}</dd></div>
      <div><dt>{{ t('Needed by') }}</dt><dd>{{ fmtFecha(abierta.fecha_requerida) || '—' }}</dd></div>
      <div><dt>{{ t('Suggested supplier') }}</dt><dd>{{ tx(abierta.proveedor?.nombre || '—') }}</dd></div>
      <div><dt>{{ t('Estimate') }}</dt><dd>{{ abierta.estimado ? fmtMoneda(abierta.estimado, abierta.moneda) : '—' }}</dd></div>
    </dl>
    <p v-if="abierta.motivo" class="mt">{{ tx(abierta.motivo) }}</p>
    <p v-if="abierta.comentario_revision" class="nota mt" :class="abierta.estado === 'RECHAZADA' ? 'error' : 'info'">
      <Icono nombre="info" />{{ tx(abierta.comentario_revision) }}</p>
    <p v-if="abierta.oc" class="mt"><router-link :to="`/ordenes/${abierta.oc.id}`" class="enlace">{{ t('PO {0}', [abierta.oc.numero]) }}</router-link></p>

    <div class="tabla-marco mt">
      <table class="tabla">
        <thead><tr><th>{{ t('Item') }}</th><th class="num">{{ t('Quantity') }}</th><th class="num">{{ t('Estimated price') }}</th></tr></thead>
        <tbody>
          <tr v-for="l in abierta.lineas" :key="l.id">
            <td>{{ tx(l.descripcion) }}<span v-if="l.codigo_articulo" class="sub codigo">{{ tx(l.codigo_articulo) }}</span></td>
            <td class="num">{{ fmtCant(l.cantidad) }} {{ tx(l.unidad || '') }}</td>
            <td class="num">{{ l.precio_estimado !== null ? fmtMoneda(l.precio_estimado, abierta.moneda) : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <template #pie>
      <button v-if="abierta.puede.cancelar" type="button" class="btn btn-fantasma" :disabled="ocupado" @click="cancelar">{{ t('Cancel request') }}</button>
      <button v-if="abierta.puede.editar" type="button" class="btn" :disabled="ocupado" @click="corregir">{{ t('Edit') }}</button>
      <button v-if="abierta.puede.aprobar" type="button" class="btn" :disabled="ocupado" @click="modal = { tipo: 'rechazar', comentario: '' }">{{ t('Reject') }}</button>
      <button v-if="abierta.puede.aprobar" type="button" class="btn btn-primario" :disabled="ocupado" @click="aprobar">{{ t('Approve') }}</button>
      <button v-if="abierta.puede.convertir" type="button" class="btn btn-primario" :disabled="ocupado" @click="abrirConvertir([abierta.id])">{{ t('Convert to PO') }}</button>
    </template>
  </PanelLateral>

  <!-- Nueva o corregir -->
  <PanelLateral v-if="form" :titulo="form.id ? t('Edit request') : t('New request')" ancho="760px" @cerrar="form = null">
    <div class="form-grilla">
      <label class="campo">{{ t('Area') }}<input v-model="form.area" maxlength="80" :placeholder="t('Maintenance, warehouse, store…')" :aria-invalid="!!errores.area" />
        <span v-if="errores.area" class="campo-error">{{ tx(errores.area) }}</span></label>
      <label class="campo">{{ t('Priority') }}
        <select v-model="form.prioridad"><option value="NORMAL">{{ t('Normal') }}</option><option value="URGENTE">{{ t('Urgent') }}</option></select></label>
      <label class="campo">{{ t('Needed by') }}<CampoFecha v-model="form.fecha_requerida" /></label>
      <div class="campo">{{ t('Suggested supplier') }}<SelectBusqueda v-model="form.proveedor_id" :opciones="opcionesProveedor" :vacio="t('No supplier yet')" :etiqueta="t('Suggested supplier')" /></div>
    </div>
    <label class="campo">{{ t('Reason') }}<textarea v-model="form.motivo" rows="2" maxlength="500"></textarea></label>

    <h3 class="mt">{{ t('Items') }}</h3>
    <p v-if="errores.lineas" class="campo-error">{{ tx(errores.lineas) }}</p>
    <div class="tabla-marco">
      <table class="tabla lineas-form">
        <thead><tr><th>{{ t('Description') }}</th><th>{{ t('Item code') }}</th><th class="num">{{ t('Quantity') }}</th><th>{{ t('Unit') }}</th><th class="num">{{ t('Estimated price') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-for="(l, i) in form.lineas" :key="i">
            <td><input v-model="l.descripcion" maxlength="300" :aria-label="t('Description')" /></td>
            <td><input v-model="l.codigo_articulo" maxlength="40" class="codigo" :aria-label="t('Item code')" :placeholder="t('Optional')" /></td>
            <td><input v-model.number="l.cantidad" type="number" min="0" step="any" class="num" :aria-label="t('Quantity')" :aria-invalid="!!errores[`lineas.${i}.cantidad`]" /></td>
            <td><input v-model="l.unidad" maxlength="5" :aria-label="t('Unit')" /></td>
            <td><input v-model.number="l.precio_estimado" type="number" min="0" step="any" class="num" :aria-label="t('Estimated price')" /></td>
            <td><button type="button" class="btn-icono" :aria-label="t('Remove line')" :disabled="form.lineas.length === 1" @click="form.lineas.splice(i, 1)"><Icono nombre="cerrar" :tam="16" /></button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="fila-flex mt" style="justify-content: space-between">
      <button type="button" class="btn btn-chico" @click="form.lineas.push(lineaVacia())"><Icono nombre="mas" :tam="14" />{{ t('Add line') }}</button>
      <span class="ayuda">{{ t('Estimate') }}: <b>{{ fmtMoneda(totalForm) }}</b></span>
    </div>
    <template #pie>
      <button type="button" class="btn" @click="form = null">{{ t('Back') }}</button>
      <button type="button" class="btn btn-primario" :disabled="ocupado" @click="guardar">{{ form.id ? t('Save') : t('Send for approval') }}</button>
    </template>
  </PanelLateral>

  <Modal v-if="modal?.tipo === 'rechazar'" :titulo="t('Reject request')" @cerrar="modal = null">
    <label class="campo">{{ t('Why is it rejected?') }}<textarea v-model="modal.comentario" rows="3" maxlength="500"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.comentario.trim()" @click="rechazar">{{ t('Reject') }}</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'convertir'" :titulo="t('Convert to PO')" @cerrar="modal = null">
    <p>{{ t('The items of {0} approved requests go into a draft PO of this supplier. You continue in the PO assistant.', [modal.ids.length || elegidas.length]) }}</p>
    <div class="campo">{{ t('Supplier') }}<SelectBusqueda v-model="modal.proveedor_id" :opciones="opcionesProveedor" :vacio="t('Choose a supplier')" :etiqueta="t('Supplier')" /></div>
    <label class="campo">{{ t('PO number') }}<input v-model="modal.oc" maxlength="40" /></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.proveedor_id || !modal.oc.trim()" @click="convertir">{{ t('Create draft PO') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.datos-grilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 0; }
.datos-grilla dt { font-size: var(--t-sm); color: var(--tinta-3); }
.datos-grilla dd { margin: 2px 0 0; }
.form-grilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0 16px; }
.campo { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.campo-error { color: var(--error); font-size: var(--t-sm); }
.lineas-form input { width: 100%; min-width: 60px; }
.lineas-form td { padding: 6px; }
.lineas-form th:first-child { width: 34%; }
.estado-cabeza { align-self: flex-start; }
</style>
