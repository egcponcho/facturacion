<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import { ACCIONES, cantTxt, fmtFecha, fmtFechaHora, fmtMoneda, fmtNum } from '@/nucleo/utils'
import { camposPropios, valorPropio, ve } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import Avance from '@/componentes/Avance.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import { confirmar } from '@/stores/confirmar'

// Detalle de la orden de compra (solo lectura): su estado, lo acordado, las
// líneas, el avance logístico, las aprobaciones y el historial. Se edita en el
// asistente; las acciones dependen del estado y del rol (las decide el servidor).
const props = defineProps({ id: { type: String, required: true } })
const route = useRoute()
const router = useRouter()

const d = ref(null)
const historial = ref([])
const TABS = [
  ['lineas', t('Lines'), 'lista'],
  ['avance', t('Progress'), 'ruta'],
  ['aprobaciones', t('Approvals'), 'check'],
  ['historial', t('History'), 'historial'],
]
const tab = ref(TABS.some(([k]) => k === route.query.tab) ? route.query.tab : 'lineas')
const modal = ref(null) // { accion, motivo }
const ocupado = ref(false)

async function cargar() {
  try {
    d.value = await api.get(`/ordenes/${props.id}`)
    if (tab.value === 'historial') historial.value = await api.get(`/ordenes/${props.id}/historial`)
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)
watch(() => props.id, cargar)
watch(tab, async (v) => {
  router.replace({ query: { ...route.query, tab: v } })
  if (v === 'historial') {
    try {
      historial.value = await api.get(`/ordenes/${props.id}/historial`)
    } catch (e) {
      errorApi(e)
    }
  }
})

const oc = computed(() => d.value?.oc)
const puede = computed(() => d.value?.puede || {})
const pasoActual = computed(() => d.value?.aprobaciones.find((a) => a.actual))
const pasosCompletos = computed(() => (d.value?.pasos || []).filter((p) => p.clave !== 'revision' && p.completo).length)
const lineasBorrador = computed(() => (d.value?.posiciones.length ? [] : d.value?.borrador?.lineas || []))
const facturas = computed(() => {
  const vistas = new Map()
  for (const p of d.value?.posiciones || []) for (const f of p.facturas) vistas.set(f.id, f)
  return [...vistas.values()]
})
const avance = computed(() => d.value?.avance)
const enCurso = computed(() => ['APROBADA', 'CERRADA'].includes(oc.value?.estado))

// Qué pide cada acción antes de hacerse
const ACCION = {
  aprobar: { titulo: t('Approve purchase order'), boton: t('Approve'), clase: 'btn-primario', motivo: false,
    texto: t('Your approval is recorded with your name. If another step follows, the PO waits for it; otherwise it is released to invoice.') },
  rechazar: { titulo: t('Reject purchase order'), boton: t('Reject'), clase: 'btn-peligro', motivo: true,
    texto: t('The PO goes back to whoever created it to correct and send it again.') },
  cancelar: { titulo: t('Cancel purchase order'), boton: t('Cancel PO'), clase: 'btn-peligro', motivo: true,
    texto: t('It can no longer be invoiced. Not possible while it has active invoices.') },
  cerrar: { titulo: t('Close purchase order'), boton: t('Close PO'), clase: 'btn-primario', motivo: true,
    texto: t('Its pending balance is no longer offered to invoice. It can be reopened later.') },
  reabrir: { titulo: t('Reopen purchase order'), boton: t('Reopen'), clase: 'btn-primario', motivo: true,
    texto: t('Its pending balance can be invoiced again.') },
}
function abrir(accion) {
  modal.value = { accion, motivo: '' }
}
async function ejecutarAccion() {
  const { accion, motivo } = modal.value
  ocupado.value = true
  try {
    const cuerpo = accion === 'aprobar' ? { comentario: motivo || null } : { motivo }
    d.value = await api.post(`/ordenes/${props.id}/${accion}`, cuerpo)
    modal.value = null
    avisar({
      aprobar: d.value.oc.estado === 'APROBADA' ? t('Purchase order approved.') : t('Approval recorded; the next step is pending.'),
      rechazar: t('Purchase order rejected.'), cancelar: t('Purchase order cancelled.'), cerrar: t('Purchase order closed.'), reabrir: t('Purchase order reopened.'),
    }[accion])
    if (tab.value === 'historial') historial.value = await api.get(`/ordenes/${props.id}/historial`)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function eliminar() {
  if (!(await confirmar(t('Delete draft PO {0}? This cannot be undone.', [oc.value.numero]), { boton: t('Delete draft'), peligro: true }))) return
  ocupado.value = true
  try {
    await api.del(`/ordenes/${props.id}`)
    avisar(t('Draft deleted.'))
    router.push('/ordenes')
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

const ACCIONES_OC = {
  borrador_creado: t('Created the draft'),
  vuelve_a_borrador: t('Edited after the rejection'),
  enviada: t('Sent'),
  paso_aprobado: t('Approved a step'),
  aprobada: t('Approved'),
  rechazada: t('Rejected'),
  cancelada: t('Cancelled'),
  cerrada: t('Closed'),
  reabierta: t('Reopened'),
  importada: t('Loaded from the ERP file'),
  actualizada: t('Updated from the ERP file'),
}
function resumen(h) {
  const x = h.detalle || {}
  if (h.accion === 'enviada' && x.lineas != null) {
    return [t('{0} lines', [x.lineas]), x.total != null ? fmtMoneda(x.total, x.moneda) : null, x.pasos?.length ? t('Approval: {0}', [x.pasos.join(' → ')]) : null]
      .filter(Boolean).join(' · ')
  }
  if (['aprobada', 'paso_aprobado', 'rechazada'].includes(h.accion)) return [x.regla, x.comentario].filter(Boolean).join(' · ')
  return ''
}
const propios = computed(() => camposPropios('ordenes').filter((c) => oc.value?.extra?.[c.clave] != null && oc.value.extra[c.clave] !== ''))
const estadoAprobacion = (e) => ({ PENDIENTE: 'EN_APROBACION', APROBADA: 'APROBADA', RECHAZADA: 'RECHAZADA' }[e] || e)
</script>

<template>
  <template v-if="d">
    <router-link to="/ordenes" class="volver"><Icono nombre="atras" :tam="15" />{{ t('Purchase orders') }}</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ t('PO {0}', [oc.numero]) }}</span>
        <EstadoBadge :estado="oc.estado" tipo="oc" />
        <EstadoBadge v-if="enCurso && avance" :estado="avance.codigo" tipo="avance" />
        <div class="doc-acciones">
          <MasOpciones v-if="puede.cancelar || puede.cerrar || puede.reabrir || puede.eliminar">
            <button v-if="puede.reabrir" type="button" class="btn" @click="abrir('reabrir')">{{ t('Reopen') }}</button>
            <button v-if="puede.cerrar" type="button" class="btn" @click="abrir('cerrar')">{{ t('Close PO') }}</button>
            <button v-if="puede.eliminar" type="button" class="btn btn-peligro" :disabled="ocupado" @click="eliminar"><Icono nombre="basura" :tam="15" />{{ t('Delete draft') }}</button>
            <button v-else-if="puede.cancelar" type="button" class="btn btn-peligro" @click="abrir('cancelar')">{{ t('Cancel PO') }}</button>
          </MasOpciones>
          <router-link v-if="puede.editar" :to="`/ordenes/${oc.id}/editar`" class="btn" :class="{ 'btn-primario': !puede.enviar }"><Icono nombre="editar" :tam="16" />{{ tx(oc.estado === 'RECHAZADA' ? t('Correct') : t('Continue editing')) }}</router-link>
          <router-link v-if="puede.enviar" :to="{ path: `/ordenes/${oc.id}/editar`, query: { paso: 'revision' } }" class="btn btn-primario"><Icono nombre="enviar" :tam="16" />{{ t('Review and send') }}</router-link>
          <button v-if="puede.rechazar" type="button" class="btn" @click="abrir('rechazar')">{{ t('Reject') }}</button>
          <button v-if="puede.aprobar" type="button" class="btn btn-primario" @click="abrir('aprobar')"><Icono nombre="check" :tam="16" />{{ t('Approve') }}</button>
        </div>
      </div>
      <div class="doc-meta">
        <span>{{ t('Supplier') }} <b>{{ tx(oc.proveedor) }}</b></span>
        <span v-if="ve('codigos_internos') && oc.sociedad">{{ t('Company') }} <b>{{ tx(oc.sociedad) }}</b></span>
        <span v-if="ve('precios')">{{ t('Total') }} <b>{{ fmtMoneda(oc.total, oc.moneda) }}</b></span>
        <span v-if="oc.creada_por">{{ t('Created by') }} <b>{{ tx(oc.creada_por) }}</b></span>
        <span v-if="oc.enviada_en">{{ t('Sent') }} <b>{{ fmtFechaHora(oc.enviada_en) }}</b></span>
        <span v-if="oc.aprobada_en">{{ t('Approved') }} <b>{{ fmtFechaHora(oc.aprobada_en) }}</b></span>
        <span v-if="oc.origen !== 'PLATAFORMA'" class="etiqueta">{{ t('From the ERP') }}</span>
      </div>
    </section>

    <!-- Qué pasa ahora con la OC -->
    <div v-if="oc.estado === 'BORRADOR'" class="nota info">
      <Icono nombre="info" :tam="16" /><span>{{ t('Draft: {0} of 5 steps complete. It does not reserve or release anything until it is sent and approved.', [pasosCompletos]) }}</span>
    </div>
    <div v-else-if="oc.estado === 'EN_APROBACION' && pasoActual" class="nota aviso">
      <Icono nombre="reloj" :tam="16" /><span>{{ t('Waiting for approval: {0} (role {1}).', [pasoActual.regla, tx(pasoActual.rol || '—')]) }}</span>
    </div>
    <div v-else-if="oc.motivo_estado && ['RECHAZADA', 'CANCELADA', 'CERRADA'].includes(oc.estado)" class="nota" :class="oc.estado === 'CERRADA' ? 'info' : 'error'">
      <Icono nombre="alerta" :tam="16" /><span>{{ t('Reason: {0}', [oc.motivo_estado]) }}</span>
    </div>
    <div v-else-if="oc.estado === 'APROBADA' && !oc.liberada" class="nota aviso">
      <Icono nombre="alerta" :tam="16" /><span>{{ t('Approved but not released to invoice ({0}).', [[oc.comercial_txt, oc.liberacion_txt].filter(Boolean).join(' · ')]) }}</span>
    </div>

    <!-- Lo acordado, agrupado por tema -->
    <div class="resumen-oc">
      <section class="panel">
        <h2>{{ t('General data') }}</h2>
        <dl class="datos">
          <dt>{{ t('PO date') }}</dt><dd>{{ fmtFecha(oc.fecha) }}</dd>
          <template v-if="ve('codigos_internos')"><dt>{{ t('Company (bill to)') }}</dt><dd>{{ tx(oc.sociedad || '—') }}</dd></template>
          <dt>{{ t('Origin') }}</dt><dd>{{ tx(oc.origen === 'PLATAFORMA' ? t('Created in the platform') : t('ERP file')) }}</dd>
        </dl>
      </section>
      <section class="panel">
        <h2>{{ t('Commercial terms') }}</h2>
        <dl class="datos">
          <dt>{{ t('Currency') }}</dt><dd>{{ tx(oc.moneda || '—') }}</dd>
          <dt>{{ t('Incoterm') }}</dt><dd>{{ tx(oc.incoterm || '—') }}</dd>
          <dt>{{ t('Payment terms') }}</dt><dd>{{ tx(oc.condicion_pago_txt || oc.condicion_pago || '—') }}</dd>
          <template v-if="ve('precios')"><dt>{{ t('Total') }}</dt><dd><b>{{ fmtMoneda(oc.total, oc.moneda) }}</b></dd></template>
        </dl>
      </section>
      <section class="panel">
        <h2>{{ t('Logistics and dates') }}</h2>
        <dl class="datos">
          <dt>{{ t('Ship date (XF)') }}</dt><dd>{{ fmtFecha(oc.fecha_xf) }}<s v-if="oc.fecha_xf_original && oc.fecha_xf_original !== oc.fecha_xf" class="sub"> {{ fmtFecha(oc.fecha_xf_original) }}</s></dd>
          <dt>{{ t('In-store date') }}</dt><dd>{{ fmtFecha(oc.fecha_tienda) }}</dd>
          <dt>{{ t('Port of loading') }}</dt><dd>{{ tx(oc.puerto_despacho || '—') }}</dd>
          <template v-if="ve('codigos_internos')"><dt>{{ t('Plants') }}</dt><dd v-if="oc.centro || oc.centro_destino">{{ tx(oc.centro || '—') }} → {{ tx(oc.centro_destino || '—') }}<template v-if="oc.centro_destino_nombre"> · {{ tx(oc.centro_destino_nombre) }}</template></dd><dd v-else>—</dd></template>
          <dt>{{ t('Country of origin') }}</dt><dd>{{ tx(oc.pais_origen || '—') }}<template v-if="oc.pais_procedencia"> · {{ t('from {0}', [oc.pais_procedencia]) }}</template></dd>
        </dl>
      </section>
      <section v-if="oc.notas || propios.length" class="panel">
        <h2>{{ t('Documentation and extras') }}</h2>
        <dl class="datos">
          <template v-if="oc.notas"><dt>{{ t('Notes') }}</dt><dd class="notas">{{ tx(oc.notas) }}</dd></template>
          <template v-for="c in propios" :key="c.clave"><dt>{{ c.etiqueta }}</dt><dd>{{ valorPropio(c, oc.extra[c.clave]) }}</dd></template>
        </dl>
      </section>
    </div>

    <div class="pestanas" role="tablist">
      <button v-for="[clave, texto, icono] in TABS" :key="clave" type="button" class="pestana" role="tab" :aria-selected="tab === clave" @click="tab = clave">
        <Icono :nombre="icono" :tam="16" />{{ tx(texto) }}
        <span v-if="clave === 'lineas'" class="cuenta">{{ tx(d.posiciones.length || lineasBorrador.length) }}</span>
        <span v-if="clave === 'aprobaciones' && d.aprobaciones.length" class="cuenta">{{ tx(d.aprobaciones.length) }}</span>
      </button>
    </div>

    <!-- Líneas -->
    <section v-if="tab === 'lineas'" class="panel">
      <template v-if="d.posiciones.length">
        <div class="tabla-marco">
          <table class="tabla" v-tarjetas>
            <thead><tr>
              <th>{{ t('Line') }}</th><th>{{ t('Item') }}</th><th class="num">{{ t('Quantity') }}</th>
              <th v-if="ve('precios')" class="num">{{ t('Unit price') }}</th><th v-if="ve('precios')" class="num">{{ t('Amount') }}</th>
              <th class="num">{{ t('Invoiced') }}</th><th class="num">{{ t('Available') }}</th><th>{{ t('Delivery') }}</th><th>{{ t('Status') }}</th>
            </tr></thead>
            <tbody>
              <tr v-for="p in d.posiciones" :key="p.id">
                <td class="codigo" :data-etiqueta="t('Line')">{{ tx(p.posicion) }}</td>
                <td :data-etiqueta="t('Item')"><span class="codigo">{{ tx(p.codigo_sap) }}</span> {{ tx([p.estilo, p.color, p.talla].filter(Boolean).join(' · ')) }}
                  <span class="sub">{{ tx(p.descripcion || '') }}<template v-if="p.almacen"> · {{ t('Warehouse {0}', [p.almacen]) }}</template></span></td>
                <td class="num" :data-etiqueta="t('Quantity')">{{ cantTxt(p.cantidad, p.unidad) }}</td>
                <td v-if="ve('precios')" class="num" :data-etiqueta="t('Unit price')">{{ p.precio == null ? '—' : fmtNum(p.precio) }}</td>
                <td v-if="ve('precios')" class="num" :data-etiqueta="t('Amount')">{{ p.importe == null ? '—' : fmtMoneda(p.importe, oc.moneda) }}</td>
                <td class="num" :data-etiqueta="t('Invoiced')">{{ fmtNum(p.facturado) }}</td>
                <td class="num" :data-etiqueta="t('Available')">{{ fmtNum(p.disponible) }}</td>
                <td :data-etiqueta="t('Delivery')">{{ fmtFecha(p.fecha_entrega) }}</td>
                <td :data-etiqueta="t('Status')"><EstadoBadge :estado="p.estado" :title="tx(p.motivo || '')" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
      <template v-else-if="lineasBorrador.length">
        <p class="ayuda">{{ t('Lines of the draft: they become PO lines when it is sent.') }}</p>
        <div class="tabla-marco">
          <table class="tabla">
            <thead><tr><th>#</th><th>{{ t('Item') }}</th><th class="num">{{ t('Quantity') }}</th><th class="num">{{ t('Unit price') }}</th></tr></thead>
            <tbody>
              <tr v-for="(l, i) in lineasBorrador" :key="i">
                <td>{{ tx(i + 1) }}</td><td class="codigo">{{ tx(l.codigo_sap || '—') }}</td>
                <td class="num">{{ l.cantidad ? cantTxt(l.cantidad, l.unidad) : '—' }}</td><td class="num">{{ l.precio ? fmtNum(l.precio) : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
      <EstadoVacio v-else icono="lista" :titulo="t('No lines yet')" :texto="t('Add the items in the assistant.')" />
    </section>

    <!-- Avance logístico (separado del estado de la OC) -->
    <section v-else-if="tab === 'avance'" class="panel">
      <template v-if="enCurso && avance">
        <p class="ayuda">{{ tx(avance.base === 'valor' ? t('Percentages by value of the lines.') : t('Percentages by number of lines (some lines have no price).')) }}</p>
        <div class="avances">
          <div><span>{{ t('Invoiced') }}</span><Avance :porcentaje="avance.facturado" /></div>
          <div><span>{{ t('Shipped') }}</span><Avance :porcentaje="avance.embarcado" /></div>
          <div><span>{{ t('Received') }}</span><Avance :porcentaje="avance.recibido" /></div>
        </div>
        <h3 v-if="facturas.length" class="mt">{{ t('Invoices') }}</h3>
        <ul v-if="facturas.length" class="lista-facturas">
          <li v-for="f in facturas" :key="f.id"><router-link :to="`/facturas/${f.id}`">{{ tx(f.nombre) }}</router-link> <EstadoBadge :estado="f.estado" /></li>
        </ul>
      </template>
      <EstadoVacio v-else icono="ruta" :titulo="t('No progress yet')" :texto="t('Invoicing, shipping and receiving start once the PO is approved.')" />
    </section>

    <!-- Aprobaciones -->
    <section v-else-if="tab === 'aprobaciones'" class="panel">
      <ol v-if="d.aprobaciones.length" class="aprobaciones">
        <li v-for="a in d.aprobaciones" :key="a.paso" :class="{ actual: a.actual }">
          <div class="ap-cabeza"><b>{{ tx(a.regla) }}</b><EstadoBadge :estado="estadoAprobacion(a.estado)" tipo="oc" /></div>
          <div class="ayuda">{{ t('Approves: role {0}', [tx(a.rol || '—')]) }}<template v-if="a.usuario"> · {{ tx(a.usuario) }} · {{ fmtFechaHora(a.fecha) }}</template></div>
          <div v-if="a.comentario">{{ tx(a.comentario) }}</div>
        </li>
      </ol>
      <EstadoVacio v-else icono="check" :titulo="t('No approval steps')"
                   :texto="tx(oc.estado === 'BORRADOR' ? t('The approval rules of your company apply when the PO is sent.') : t('No approval rule applied to this PO.'))" />
    </section>

    <!-- Historial -->
    <section v-else class="panel">
      <ul class="linea-tiempo">
        <li v-for="h in historial" :key="h.id">
          <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<br />{{ tx(h.usuario || t('System')) }}</span>
          <div>
            <b>{{ tx(ACCIONES_OC[h.accion] || ACCIONES[h.accion] || h.accion) }}</b>
            <div v-if="h.motivo">{{ t('Reason: {0}', [h.motivo]) }}</div>
            <div v-if="resumen(h)" class="ayuda">{{ tx(resumen(h)) }}</div>
          </div>
        </li>
        <li v-if="!historial.length"><span></span><span class="ayuda">{{ t('No activity.') }}</span></li>
      </ul>
    </section>
  </template>

  <Modal v-if="modal" :titulo="tx(ACCION[modal.accion].titulo)" @cerrar="modal = null">
    <p>{{ tx(ACCION[modal.accion].texto) }}</p>
    <label class="campo"><span :class="{ req: ACCION[modal.accion].motivo }">{{ tx(ACCION[modal.accion].motivo ? t('Reason') : t('Comment (optional)')) }}</span>
      <textarea v-model="modal.motivo" class="entrada" rows="3" maxlength="500"></textarea></label>
    <template #pie>
      <button type="button" class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button type="button" class="btn" :class="ACCION[modal.accion].clase" :disabled="ocupado || (ACCION[modal.accion].motivo && !modal.motivo.trim())" @click="ejecutarAccion">
        {{ tx(ACCION[modal.accion].boton) }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.nota { margin-bottom: 16px; }
.resumen-oc { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; margin-bottom: 16px; }
.resumen-oc .panel { margin: 0; }
.resumen-oc h2 { font-size: 0.95rem; margin: 0 0 10px; }
.datos { display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; margin: 0; font-size: 0.9rem; }
.datos dt { color: var(--tinta-2); }
.datos dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.datos .notas { white-space: pre-line; }
.avances { display: grid; gap: 12px; max-width: 520px; }
.avances > div { display: grid; grid-template-columns: 110px 1fr; align-items: center; gap: 12px; }
.lista-facturas { list-style: none; padding: 0; margin: 8px 0 0; display: flex; flex-direction: column; gap: 6px; }
.aprobaciones { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.aprobaciones li { border: 1px solid var(--linea); border-radius: 10px; padding: 10px 14px; display: flex; flex-direction: column; gap: 4px; }
.aprobaciones li.actual { border-color: var(--aviso-borde); background: var(--aviso-suave); }
.ap-cabeza { display: flex; align-items: center; gap: 8px; }
</style>
