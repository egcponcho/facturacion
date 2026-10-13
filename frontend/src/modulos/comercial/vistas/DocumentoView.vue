<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import NavComercial from '@/modulos/comercial/componentes/NavComercial.vue'
import { opcionesLista } from '@/nucleo/listas.js'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtFecha, fmtMoneda, fmtNum } from '@/nucleo/utils'
import Seleccion from '@/componentes/Seleccion.vue'

// Un documento comercial: en borrador se edita (cabecera y líneas con sus
// impuestos; el servidor calcula los totales); emitido es de solo lectura y
// desde aquí se cobra o paga, se rectifica con una nota o se anula.
const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()
const op = ref(null) // opciones de los formularios
const d = ref(null) // el documento guardado
const ocupado = ref(false)
const modal = ref(null)
const errores = ref([])

const nuevo = computed(() => props.id === 'nuevo')
const editable = computed(() => puede('comercial.editar') && (nuevo.value || (d.value?.estado === 'BORRADOR' && !d.value?.factura_id)))
const hoy = () => new Date().toISOString().slice(0, 10)
const lineaVacia = () => ({ descripcion: '', cantidad: 1, unidad: '', precio_unitario: 0, descuento_pct: 0, impuestos: null })
const form = reactive({ tipo: 'FACTURA', sociedad: '', tercero_id: null, fecha: hoy(), moneda: '', condicion_pago: '',
  referencia_externa: '', notas: '', lineas: [lineaVacia()] })
const tipoForm = computed(() => op.value?.tipos.find((x) => x.codigo === (d.value?.tipo || form.tipo)))
const recibido = computed(() => tipoForm.value?.direccion === 'RECIBIDO')
const rolTercero = computed(() => (recibido.value ? 'PROVEEDOR' : 'CLIENTE'))
const terceroInicial = ref(null)

async function cargar() {
  try {
    op.value = op.value || await api.get('/comercial/opciones')
    if (nuevo.value) {
      d.value = null
      form.sociedad = form.sociedad || op.value.sociedades[0]?.codigo || ''
      return
    }
    d.value = await api.get(`/documentos/${props.id}`)
    Object.assign(form, {
      tipo: d.value.tipo, sociedad: d.value.sociedad, tercero_id: d.value.tercero_id, fecha: d.value.fecha || hoy(),
      moneda: d.value.moneda, condicion_pago: d.value.condicion_pago || '', referencia_externa: d.value.referencia_externa || '',
      notas: d.value.notas || '',
      lineas: d.value.lineas.map((l) => ({ descripcion: l.descripcion, cantidad: l.cantidad, unidad: l.unidad || '', precio_unitario: l.precio_unitario,
        descuento_pct: l.descuento_pct || 0, impuestos: l.impuestos_codigos, codigo: l.codigo, articulo_id: l.articulo_id, posicion_oc_id: l.posicion_oc_id })),
    })
    terceroInicial.value = { valor: d.value.tercero_id, texto: d.value.tercero }
  } catch (e) {
    errorApi(e)
  }
}
cargar()
watch(() => props.id, cargar)

// Tercero: búsqueda en el servidor (clientes para lo emitido, proveedores para lo recibido)
async function buscarTerceros(texto) {
  const r = await api.get('/terceros', { q: texto || undefined, rol: rolTercero.value, size: 30 })
  return r.items.map((x) => ({ valor: x.id, texto: x.nombre, sub: [x.codigo, x.id_fiscal, x.pais].filter(Boolean).join(' · '), datos: x }))
}
function alElegirTercero(o) {
  if (!o?.datos) return
  if (o.datos.moneda) form.moneda = o.datos.moneda
  if (o.datos.condicion_pago) form.condicion_pago = o.datos.condicion_pago
}
const opcionesImpuestos = computed(() => (op.value?.impuestos || []).map((x) => ({ valor: x.codigo, texto: x.nombre,
  sub: `${x.es_retencion ? t('Withholding') : t('Tax')} · ${fmtNum(x.tasa, 2)}${x.tipo === 'PORCENTAJE' ? ' %' : ''}` })))
const defectoImpuestos = computed(() => op.value?.impuestos_defecto?.[form.sociedad] || [])

function cuerpo() {
  return {
    fecha: form.fecha || null, moneda: form.moneda || undefined, condicion_pago: form.condicion_pago || null,
    referencia_externa: form.referencia_externa || null, notas: form.notas || null,
    lineas: form.lineas.filter((l) => l.descripcion || l.precio_unitario).map((l) => ({
      descripcion: l.descripcion, cantidad: Number(l.cantidad), unidad: l.unidad || null, precio_unitario: Number(l.precio_unitario),
      descuento_pct: Number(l.descuento_pct || 0), impuestos: l.impuestos === null && !recibido.value ? null : (l.impuestos || []),
      codigo: l.codigo || null, articulo_id: l.articulo_id || null, posicion_oc_id: l.posicion_oc_id || null,
    })),
  }
}
async function guardar() {
  ocupado.value = true
  errores.value = []
  try {
    if (nuevo.value) {
      const r = await api.post('/documentos', { tipo: form.tipo, sociedad: form.sociedad, tercero_id: form.tercero_id, ...cuerpo() })
      avisar(t('Draft saved.'))
      router.replace(`/comercial/documentos/${r.id}`)
    } else {
      d.value = await api.patch(`/documentos/${d.value.id}`, { version: d.value.version, ...cuerpo() })
      avisar(t('Draft saved.'))
    }
  } catch (e) {
    errores.value = e.detalle || []
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function accion(fn, mensaje) {
  ocupado.value = true
  try {
    await fn()
    if (mensaje) avisar(mensaje)
    modal.value = null
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
const emitir = () => accion(async () => { d.value = await api.post(`/documentos/${d.value.id}/emitir`, { version: d.value.version }) },
  t('Document issued.'))
async function eliminar() {
  ocupado.value = true
  try {
    await api.del(`/documentos/${d.value.id}`)
    avisar(t('Draft deleted.'))
    router.push('/comercial/documentos')
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
const anular = () => accion(() => api.post(`/documentos/${d.value.id}/anular`, { motivo: modal.value.motivo }), t('Document voided.'))
async function nota(tipo) {
  ocupado.value = true
  try {
    const r = await api.post(`/documentos/${d.value.id}/nota`, { tipo, motivo: modal.value.motivo })
    modal.value = null
    router.push(`/comercial/documentos/${r.id}`)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
const tipoNota = (clase) => op.value?.tipos.find((x) => x.clase === clase && x.direccion === d.value?.direccion)?.codigo
function abrirPago() {
  modal.value = { tipo: 'pago', importe: d.value.saldo, fecha: hoy(), metodo_pago: op.value.metodos_pago[0]?.codigo || '', referencia: '' }
}
const registrarPago = () => accion(() => api.post('/pagos', {
  direccion: d.value.direccion === 'EMITIDO' ? 'COBRO' : 'PAGO', tercero_id: d.value.tercero_id, sociedad: d.value.sociedad,
  fecha: modal.value.fecha, moneda: d.value.moneda, importe: Number(modal.value.importe), metodo_pago: modal.value.metodo_pago || null,
  referencia: modal.value.referencia || null, aplicaciones: [{ documento_id: d.value.id, importe: Number(modal.value.importe) }],
}), d.value?.direccion === 'EMITIDO' ? t('Collection registered.') : t('Payment registered.'))

const columnasLineas = [
  { clave: 'descripcion', texto: t('Description'), fija: true, prioridad: 1 },
  { clave: 'cantidad', texto: t('Quantity'), num: true, prioridad: 1 },
  { clave: 'precio_unitario', texto: t('Unit price'), num: true, prioridad: 1 },
  { clave: 'descuento', texto: t('Discount'), num: true, prioridad: 3 },
  { clave: 'subtotal', texto: t('Subtotal'), num: true, prioridad: 2 },
  { clave: 'impuestos', texto: t('Taxes'), num: true, prioridad: 2 },
  { clave: 'total', texto: t('Total'), num: true, prioridad: 1 },
]
const columnasVenc = [
  { clave: 'numero', texto: t('Installment'), prioridad: 1 },
  { clave: 'fecha', texto: t('Due date'), prioridad: 1 },
  { clave: 'importe', texto: t('Amount'), num: true, prioridad: 1 },
]
const errorDe = (campo) => errores.value.find((e) => e.campo === campo)?.mensaje
const titulo = computed(() => (nuevo.value ? t('New document') : d.value ? (d.value.numero || d.value.referencia_externa || t('Draft')) : ''))
</script>

<template>
  <router-link to="/comercial/documentos" class="volver"><Icono nombre="atras" :tam="15" />{{ t('Documents') }}</router-link>
  <NavComercial />
  <template v-if="op && (nuevo || d)">
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ tx(titulo) }}</span>
        <span v-if="tipoForm" class="etiqueta">{{ tx(tipoForm.nombre) }}</span>
        <EstadoBadge v-if="d" :estado="d.estado" tipo="documento" />
        <EstadoBadge v-if="d?.estado_cobro" :estado="d.estado_cobro" tipo="cobro" />
        <div class="doc-acciones">
          <template v-if="editable">
            <button v-if="d" class="btn btn-peligro" :disabled="ocupado" @click="modal = { tipo: 'eliminar' }"><Icono nombre="basura" />{{ t('Delete') }}</button>
            <button class="btn" :disabled="ocupado" @click="guardar"><Icono nombre="check" />{{ t('Save draft') }}</button>
            <button v-if="d && puede('comercial.emitir')" class="btn btn-primario" :disabled="ocupado" @click="modal = { tipo: 'emitir' }"><Icono nombre="enviar" />{{ t('Issue') }}</button>
          </template>
          <template v-else-if="d?.estado === 'EMITIDO'">
            <button v-if="puede('comercial.editar') && d.signo > 0 && tipoNota('NOTA_CREDITO')" class="btn" @click="modal = { tipo: 'nota', clase: 'NOTA_CREDITO', motivo: '' }">{{ t('Credit note') }}</button>
            <button v-if="puede('comercial.editar') && d.signo > 0 && tipoNota('NOTA_DEBITO')" class="btn" @click="modal = { tipo: 'nota', clase: 'NOTA_DEBITO', motivo: '' }">{{ t('Debit note') }}</button>
            <button v-if="puede('comercial.emitir') && !d.factura_id" class="btn btn-peligro" @click="modal = { tipo: 'anular', motivo: '' }">{{ t('Void') }}</button>
            <button v-if="puede('comercial.pagos') && d.signo > 0 && d.saldo > 0" class="btn btn-primario" @click="abrirPago">
              <Icono nombre="moneda" />{{ d.direccion === 'EMITIDO' ? t('Register collection') : t('Register payment') }}
            </button>
          </template>
        </div>
      </div>
      <div v-if="d" class="doc-meta">
        <span>{{ d.direccion === 'EMITIDO' ? t('Customer') : t('Supplier') }} <b>{{ tx(d.tercero) }}</b></span>
        <span>{{ t('Company') }} <b>{{ tx(d.sociedad) }}</b></span>
        <span>{{ t('Total') }} <b>{{ fmtMoneda(d.total, d.moneda) }}</b></span>
        <span v-if="d.estado === 'EMITIDO'">{{ t('Balance') }} <b>{{ fmtMoneda(d.saldo, d.moneda) }}</b></span>
        <span v-if="d.factura_id">{{ t('From supplier invoice') }} <router-link :to="`/facturas/${d.factura_id}`" class="enlace">{{ tx(d.referencia_externa) }}</router-link></span>
      </div>
      <p v-if="d?.estado === 'ANULADO'" class="nota error">{{ t('Voided: {0}', [d.motivo_anulacion || '—']) }}</p>

      <!-- Cabecera -->
      <div class="doc-datos">
        <label class="dato"><span class="req">{{ t('Document type') }}</span>
          <Seleccion v-if="nuevo" v-model="form.tipo" class="entrada">
            <option v-for="x in op.tipos" :key="x.codigo" :value="x.codigo">{{ tx(x.nombre) }}</option>
          </Seleccion>
          <b v-else>{{ tx(d.tipo_nombre) }}</b>
        </label>
        <label class="dato"><span class="req">{{ t('Company') }}</span>
          <Seleccion v-if="nuevo" v-model="form.sociedad" class="entrada">
            <option v-for="s in op.sociedades" :key="s.codigo" :value="s.codigo">{{ s.codigo }} · {{ tx(s.nombre) }}</option>
          </Seleccion>
          <b v-else>{{ tx(d.sociedad) }}</b>
        </label>
        <label class="dato col-2"><span class="req">{{ recibido ? t('Supplier') : t('Customer') }}</span>
          <SelectBusqueda v-if="nuevo" v-model="form.tercero_id" :buscar="buscarTerceros" :opciones="terceroInicial ? [terceroInicial] : []"
                          :etiqueta="recibido ? t('Supplier') : t('Customer')" :prefijo="false" @opcion="alElegirTercero" />
          <b v-else>{{ tx(d.tercero) }}</b>
          <small v-if="errorDe('tercero_id')" class="texto-error">{{ tx(errorDe('tercero_id')) }}</small>
        </label>
        <label class="dato"><span>{{ t('Date') }}</span>
          <CampoFecha v-if="editable" v-model="form.fecha" />
          <b v-else>{{ fmtFecha(d.fecha) }}</b>
        </label>
        <label class="dato"><span>{{ t('Currency') }}</span>
          <Seleccion v-if="editable" v-model="form.moneda" class="entrada">
            <option value="">{{ t('Of the company') }}</option>
            <option v-for="[c, n] in opcionesLista('moneda')" :key="c" :value="c">{{ c }} · {{ tx(n) }}</option>
          </Seleccion>
          <b v-else>{{ tx(d.moneda) }}<template v-if="d.tipo_cambio !== 1"> · {{ fmtNum(d.tipo_cambio, 4) }}</template></b>
        </label>
        <label class="dato"><span>{{ t('Payment terms') }}</span>
          <Seleccion v-if="editable" v-model="form.condicion_pago" class="entrada">
            <option value="">{{ t('Cash (due on its date)') }}</option>
            <option v-for="c in op.condiciones_pago" :key="c.codigo" :value="c.codigo">{{ tx(c.nombre) }}</option>
          </Seleccion>
          <b v-else>{{ tx(op.condiciones_pago.find((c) => c.codigo === d.condicion_pago)?.nombre || d.condicion_pago || '—') }}</b>
        </label>
        <label v-if="recibido" class="dato"><span class="req">{{ t("Supplier's number") }}</span>
          <input v-if="editable" v-model="form.referencia_externa" class="entrada" maxlength="60" />
          <b v-else>{{ tx(d.referencia_externa || '—') }}</b>
        </label>
        <label class="dato col-2"><span>{{ t('Notes') }}</span>
          <input v-if="editable" v-model="form.notas" class="entrada" maxlength="4000" />
          <b v-else>{{ tx(d.notas || '—') }}</b>
        </label>
      </div>
    </section>

    <!-- Líneas: editor del borrador -->
    <section v-if="editable" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Lines') }}</h2>
        <p>{{ t('Totals and taxes are calculated when you save, with the rate in force on the document date.') }}</p></div></div>
      <div class="tabla-marco tabla-captura">
        <table class="tabla" v-tarjetas>
          <thead><tr>
            <th>{{ t('Description') }}</th><th class="num">{{ t('Quantity') }}</th><th>{{ t('Unit') }}</th>
            <th class="num">{{ t('Unit price') }}</th><th class="num">{{ t('Discount %') }}</th><th>{{ t('Taxes') }}</th><th></th>
          </tr></thead>
          <tbody>
            <tr v-for="(l, i) in form.lineas" :key="i">
              <td><input v-model="l.descripcion" class="entrada" maxlength="300" :aria-label="t('Description')" /></td>
              <td class="num"><input v-model="l.cantidad" type="number" min="0.001" step="any" class="entrada num ancho-s" :aria-label="t('Quantity')" /></td>
              <td><Seleccion v-model="l.unidad" class="entrada" :aria-label="t('Unit')"><option value="">—</option>
                <option v-for="[c] in opcionesLista('unidad')" :key="c" :value="c">{{ c }}</option></Seleccion></td>
              <td class="num"><input v-model="l.precio_unitario" type="number" min="0" step="any" class="entrada num ancho-m" :aria-label="t('Unit price')" /></td>
              <td class="num"><input v-model="l.descuento_pct" type="number" min="0" max="100" step="any" class="entrada num ancho-s" :aria-label="t('Discount %')" /></td>
              <td style="min-width: 200px">
                <SelectBusqueda :model-value="l.impuestos ?? (recibido ? [] : defectoImpuestos)" multiple :opciones="opcionesImpuestos" :prefijo="false"
                                :placeholder="t('No taxes')" :etiqueta="t('Taxes')" @update:model-value="(v) => (l.impuestos = v)" />
              </td>
              <td><button type="button" class="btn-icono" :aria-label="t('Remove line')" :disabled="form.lineas.length === 1" @click="form.lineas.splice(i, 1)"><Icono nombre="basura" :tam="15" /></button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-for="e in errores.filter((x) => String(x.campo || '').startsWith('lineas'))" :key="e.campo" class="texto-error">{{ tx(e.mensaje) }}</p>
      <button type="button" class="btn mt" @click="form.lineas.push(lineaVacia())"><Icono nombre="mas" />{{ t('Add line') }}</button>
    </section>

    <!-- Documento guardado: líneas, impuestos y totales -->
    <section v-if="d" class="panel">
      <div class="panel-cabeza"><div><h2>{{ editable ? t('Calculated with the last save') : t('Lines') }}</h2></div></div>
      <TablaDatos tabla="documento_lineas" :columnas="columnasLineas" :filas="d.lineas" :vistas-guardadas="false" :etiqueta="t('Lines')">
        <template #celda-descripcion="{ fila: l }">{{ tx(l.descripcion) }}<span v-if="l.codigo" class="sub codigo">{{ tx(l.codigo) }}</span></template>
        <template #celda-cantidad="{ fila: l }">{{ fmtNum(l.cantidad, 3) }} <span class="sub">{{ tx(l.unidad || '') }}</span></template>
        <template #celda-precio_unitario="{ fila: l }">{{ fmtNum(l.precio_unitario, 2) }}</template>
        <template #celda-descuento="{ fila: l }">{{ l.descuento ? fmtNum(l.descuento, 2) : '—' }}</template>
        <template #celda-subtotal="{ fila: l }">{{ fmtNum(l.subtotal, 2) }}</template>
        <template #celda-impuestos="{ fila: l }">
          {{ fmtNum(l.impuestos - l.retenciones, 2) }}
          <span class="sub">{{ l.aplicados.map((a) => `${a.codigo} ${fmtNum(a.tasa, 2)}`).join(' · ') }}</span>
        </template>
        <template #celda-total="{ fila: l }"><span class="fuerte">{{ fmtNum(l.total, 2) }}</span></template>
        <template #vacio>{{ t('The document has no lines.') }}</template>
      </TablaDatos>
      <dl class="totales">
        <dt>{{ t('Subtotal') }}</dt><dd>{{ fmtMoneda(d.subtotal, d.moneda) }}</dd>
        <template v-for="i in d.impuestos_detalle" :key="i.codigo">
          <dt>{{ tx(i.nombre) }}</dt><dd>{{ i.es_retencion ? '−' : '' }}{{ fmtMoneda(i.importe, d.moneda) }}</dd>
        </template>
        <dt class="fuerte">{{ t('Total') }}</dt><dd class="fuerte">{{ fmtMoneda(d.total, d.moneda) }}</dd>
      </dl>
    </section>

    <section v-if="d && (d.vencimientos.length || d.aplicaciones.length || d.relaciones.length)" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Due dates and payments') }}</h2></div></div>
      <TablaDatos v-if="d.vencimientos.length" tabla="documento_vencimientos" :columnas="columnasVenc" :filas="d.vencimientos" :vistas-guardadas="false" :etiqueta="t('Due dates')">
        <template #celda-fecha="{ fila: v }">{{ fmtFecha(v.fecha) }}</template>
        <template #celda-importe="{ fila: v }">{{ fmtMoneda(v.importe, d.moneda) }}</template>
      </TablaDatos>
      <ul class="lista-simple mt">
        <li v-for="a in d.aplicaciones" :key="a.id" :class="{ apagado: !a.activa }">
          <template v-if="a.pago_id">{{ t('Payment #{0}', [a.pago_id]) }}</template>
          <router-link v-else-if="a.credito_id !== d.id" :to="`/comercial/documentos/${a.credito_id}`" class="enlace">{{ t('Credit note #{0}', [a.credito_id]) }}</router-link>
          <router-link v-else :to="`/comercial/documentos/${a.documento_id}`" class="enlace">{{ t('Applied to document #{0}', [a.documento_id]) }}</router-link>
          · <b>{{ fmtMoneda(a.importe, d.moneda) }}</b><template v-if="!a.activa"> · {{ t('voided') }}</template>
        </li>
        <li v-for="r in d.relaciones" :key="`${r.tipo}-${r.documento_id}`">
          {{ tx(r.sentido === 'a' ? t('Corrects') : t('Corrected by')) }}
          <router-link :to="`/comercial/documentos/${r.documento_id}`" class="enlace">{{ tx(r.tipo_documento) }} {{ tx(r.nombre) }}</router-link>
          <EstadoBadge :estado="r.estado" tipo="documento" />
        </li>
      </ul>
    </section>
  </template>

  <Modal v-if="modal?.tipo === 'emitir'" :titulo="t('Issue the document')" @cerrar="modal = null">
    <p>{{ t('It takes the next number of its series and its totals, parties and due dates become fixed. To correct it afterwards you will issue a credit or debit note.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="emitir">{{ t('Issue') }}</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'eliminar'" :titulo="t('Delete the draft')" @cerrar="modal = null">
    <p>{{ t('The draft is deleted. It never had a number.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="eliminar">{{ t('Delete') }}</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'anular' || modal?.tipo === 'nota'" :titulo="modal.tipo === 'anular' ? t('Void the document') : modal.clase === 'NOTA_CREDITO' ? t('Credit note') : t('Debit note')" @cerrar="modal = null">
    <p v-if="modal.tipo === 'anular'">{{ t('A voided document keeps its number and stops counting in balances. It can only be voided while it has no payments applied.') }}</p>
    <p v-else>{{ t('A draft note is created with all the lines of this document; adjust it before issuing.') }}</p>
    <label class="campo"><span class="req">{{ t('Reason') }}</span><input v-model="modal.motivo" class="entrada" maxlength="500" /></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button v-if="modal.tipo === 'anular'" class="btn btn-peligro" :disabled="ocupado || !modal.motivo.trim()" @click="anular">{{ t('Void') }}</button>
      <button v-else class="btn btn-primario" :disabled="ocupado || !modal.motivo.trim()" @click="nota(tipoNota(modal.clase))">{{ t('Create draft note') }}</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'pago'" :titulo="d.direccion === 'EMITIDO' ? t('Register collection') : t('Register payment')" @cerrar="modal = null">
    <div class="rejilla-formulario">
      <label class="campo"><span class="req">{{ t('Amount') }}</span><input v-model="modal.importe" type="number" min="0.01" step="any" class="entrada" /></label>
      <label class="campo"><span class="req">{{ t('Date') }}</span><CampoFecha v-model="modal.fecha" /></label>
      <label class="campo"><span>{{ t('Payment method') }}</span>
        <Seleccion v-model="modal.metodo_pago" class="entrada"><option v-for="m in op.metodos_pago" :key="m.codigo" :value="m.codigo">{{ tx(m.nombre) }}</option></Seleccion>
      </label>
      <label class="campo"><span>{{ t('Reference') }}</span><input v-model="modal.referencia" class="entrada" maxlength="80" /></label>
    </div>
    <p class="ayuda">{{ t('Balance {0}. A partial amount leaves the rest pending.', [fmtMoneda(d.saldo, d.moneda)]) }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !(Number(modal.importe) > 0)" @click="registrarPago">{{ t('Register') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.totales { display: grid; grid-template-columns: max-content max-content; justify-content: end; gap: 4px 24px; margin: 14px 0 0; }
.totales dt { color: var(--texto-suave); }
.totales dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
.lista-simple { list-style: none; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.rejilla-formulario { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
</style>
