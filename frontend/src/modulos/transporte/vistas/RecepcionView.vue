<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Asistente from '@/componentes/Asistente.vue'
import Avance from '@/componentes/Avance.vue'
import CampoFecha from '@/componentes/CampoFecha.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { avisar, errorApi, guardando } from '@/stores/ui'
import { fmtCant, fmtFecha, fmtFechaHora, pct, plural } from '@/nucleo/utils'

// Recepción en bodega de una unidad de carga (contenedor, guía, camión). Se
// recibe en una bodega o bodega fiscal, en una o varias partes; cada registro
// lleva la fecha en que se recibió. El registro es guiado: bodega y fecha →
// conteo → revisión (con faltantes, sobrantes y daños) → guardar. Las acciones
// cortas (confirmar lo pendiente sin conteo, cerrar con faltantes) van en una
// ventana pequeña.
const props = defineProps({ id: String })
const router = useRouter()
const d = ref(null)
const ocupado = ref(false)
const modal = ref(null)
const registro = ref(null) // { tipo, paso, centro, fecha, observacion, cantidades: {id: {cantidad, danada, observacion}}, filtroPl }

const hoy = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
const u = computed(() => d.value?.unidad)
const acc = computed(() => d.value?.acciones || {})
const bodegas = computed(() => (d.value?.bodegas || []).map((b) => ({ valor: b.codigo, texto: `${b.codigo} · ${b.nombre}`, sub: tx(tipoBodega(b.tipo)) })))
const nombreBodega = (c) => d.value?.bodegas.find((b) => b.codigo === c)?.nombre || c
const TIPOS_BODEGA = { BODEGA_FISCAL: t('Bonded warehouse'), ZONA_FRANCA: t('Free trade zone'), LOCAL: t('Local warehouse'), TIENDA: t('Store / DC') }
const tipoBodega = (c) => TIPOS_BODEGA[c] || c || ''
const TIPOS = { CONTEO: t('Count'), AJUSTE: t('Adjustment'), SIN_CONTEO: t('Confirmed without counting') }
const DIFERENCIA = { FALTANTE: t('Short'), SOBRANTE: t('Over'), DANO: t('Damaged') }
const avance = computed(() => (d.value ? pct(d.value.totales.recibido, d.value.totales.enviado) : 0))

async function cargar() {
  try {
    d.value = await api.get(`/unidades/${props.id}/recepcion`)
  } catch (err) {
    errorApi(err)
    if (err.status === 404) router.push('/transporte')
  }
}
onMounted(cargar)

// ---- Registro guiado (conteo o ajuste) ------------------------------------
function iniciar(tipo) {
  registro.value = {
    tipo, paso: 0, centro: u.value.centro || u.value.embarque.centro || bodegas.value[0]?.valor || '', fecha: hoy(), observacion: '',
    cantidades: Object.fromEntries(d.value.lineas.map((l) => [l.pl_linea_id, { cantidad: '', danada: '', observacion: '' }])), filtroPl: '',
  }
}
const num = (v) => (v === '' || v === null || v === undefined ? 0 : Number(v))
const pls = computed(() => [...new Map((d.value?.lineas || []).map((l) => [l.pl_id, { valor: l.pl_id, texto: `${l.pl} · ${l.factura}`, sub: l.proveedor }])).values()])
const lineasPaso = computed(() => (d.value?.lineas || []).filter((l) => !registro.value?.filtroPl || l.pl_id === registro.value.filtroPl))
const ajuste = computed(() => registro.value?.tipo === 'AJUSTE')
function llenarPendiente() {
  for (const l of lineasPaso.value) if (l.pendiente > 0) registro.value.cantidades[l.pl_linea_id].cantidad = l.pendiente
}
function limpiar() {
  for (const l of lineasPaso.value) Object.assign(registro.value.cantidades[l.pl_linea_id], { cantidad: '', danada: '' })
}
// Lo que quedará en cada línea con este registro y su diferencia frente a lo enviado
const previa = computed(() => {
  if (!registro.value) return []
  return d.value.lineas.map((l) => {
    const c = registro.value.cantidades[l.pl_linea_id]
    const recibido = l.recibido + num(c.cantidad)
    const danado = l.danado + num(c.danada)
    return { ...l, ahora: num(c.cantidad), danadaAhora: num(c.danada), nota: c.observacion, recibidoFinal: recibido, danadoFinal: danado, diferenciaFinal: recibido - l.enviado }
  })
})
const tocadas = computed(() => previa.value.filter((l) => l.ahora || l.danadaAhora))
// Errores que el servidor también rechaza: se ven antes de enviar
const errores = computed(() => {
  const r = registro.value
  if (!r) return []
  const e = []
  if (!r.centro) e.push(t('Choose the warehouse that receives.'))
  if (!r.fecha) e.push(t('Enter the date it was received.'))
  if (ajuste.value && !r.observacion.trim()) e.push(t('An adjustment needs its reason.'))
  if (!tocadas.value.length) e.push(t('Enter at least one received quantity.'))
  for (const l of tocadas.value) {
    const ref = `${l.pl} · ${l.codigo}${l.variante || l.talla ? ` ${l.variante || l.talla}` : ''}`
    if (!ajuste.value && (l.ahora < 0 || l.danadaAhora < 0)) e.push(t('{0}: a count cannot be negative.', [ref]))
    if (!ajuste.value && l.danadaAhora > l.ahora) e.push(t('{0}: damaged cannot exceed what is counted now.', [ref]))
    if (l.danadoFinal > l.recibidoFinal) e.push(t('{0}: damaged cannot exceed received.', [ref]))
    if (l.recibidoFinal < 0) e.push(t('{0}: the adjustment leaves a negative quantity.', [ref]))
    if (!ajuste.value && l.diferenciaFinal > 0 && !l.nota.trim() && !r.observacion.trim()) e.push(t('{0}: explain the surplus.', [ref]))
  }
  return e
})
const resumenPrevia = computed(() => ({
  lineas: tocadas.value.length,
  cantidad: tocadas.value.reduce((a, l) => a + l.ahora, 0),
  danada: tocadas.value.reduce((a, l) => a + l.danadaAhora, 0),
  sobrantes: previa.value.filter((l) => l.diferenciaFinal > 0),
  faltantes: previa.value.filter((l) => l.diferenciaFinal < 0),
  completa: previa.value.every((l) => l.recibidoFinal >= l.enviado),
}))
const pasos = computed(() => [
  { clave: 'bodega', titulo: t('Warehouse and date'), completo: !!(registro.value?.centro && registro.value?.fecha && (!ajuste.value || registro.value.observacion.trim())) },
  { clave: 'conteo', titulo: ajuste.value ? t('Corrections') : t('Count'), completo: tocadas.value.length > 0 },
  { clave: 'revision', titulo: t('Review and save'), errores: registro.value?.paso === 2 ? errores.value.length : 0 },
])
async function guardar() {
  if (errores.value.length) return
  const r = registro.value
  ocupado.value = true
  try {
    d.value = await guardando(api.post(`/unidades/${props.id}/recepcion`, {
      tipo: r.tipo, centro: r.centro, fecha: r.fecha, observacion: r.observacion.trim() || null,
      lineas: tocadas.value.map((l) => ({ pl_linea_id: l.pl_linea_id, cantidad: l.ahora, danada: l.danadaAhora, observacion: l.nota.trim() || null })),
    }))
    avisar(d.value.unidad.recepcion_estado === 'RECIBIDA' ? t('Receipt saved: the load unit is fully received.') : t('Receipt saved.'))
    registro.value = null
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}

// ---- Acciones cortas -------------------------------------------------------
function abrirSinConteo() {
  modal.value = { tipo: 'sin_conteo', centro: u.value.centro || u.value.embarque.centro || bodegas.value[0]?.valor || '', fecha: hoy(), observacion: '' }
}
function abrirCierre() {
  modal.value = { tipo: 'cerrar', motivo: '' }
}
const faltantes = computed(() => (d.value?.diferencias || []).filter((x) => x.tipo === 'FALTANTE'))
async function confirmar() {
  const m = modal.value
  ocupado.value = true
  try {
    d.value = m.tipo === 'sin_conteo'
      ? await guardando(api.post(`/unidades/${props.id}/recepcion/sin-conteo`, { centro: m.centro, fecha: m.fecha, observacion: m.observacion || null }))
      : await guardando(api.post(`/unidades/${props.id}/recepcion/cerrar`, { motivo: m.motivo || null }))
    avisar(t('The load unit is received.'))
    modal.value = null
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}

// ---- Tablas ------------------------------------------------------------------
const columnas = [
  { clave: 'pl', texto: t('Packing list'), fija: true, prioridad: 1 },
  { clave: 'codigo', texto: t('Item'), prioridad: 1 },
  { clave: 'descripcion', texto: t('Description'), prioridad: 3 },
  { clave: 'proveedor', texto: t('Supplier'), prioridad: 3 },
  { clave: 'oc', texto: t('PO'), prioridad: 3 },
  { clave: 'enviado', texto: t('Shipped'), num: true, prioridad: 2 },
  { clave: 'recibido', texto: t('Received'), num: true, prioridad: 1 },
  { clave: 'danado', texto: t('Damaged'), num: true, prioridad: 2 },
  { clave: 'pendiente', texto: t('Pending'), num: true, prioridad: 2 },
  { clave: 'diferencia', texto: t('Difference'), num: true, prioridad: 2 },
]
const columnasConteo = [
  { clave: 'pl', texto: t('Packing list'), fija: true, prioridad: 1 },
  { clave: 'codigo', texto: t('Item'), prioridad: 1 },
  { clave: 'enviado', texto: t('Shipped'), num: true, prioridad: 2 },
  { clave: 'recibido', texto: t('Received before'), num: true, prioridad: 2 },
  { clave: 'pendiente', texto: t('Pending'), num: true, prioridad: 2 },
  { clave: 'ahora', texto: t('Received now'), prioridad: 1, ordenable: false, filtro: false },
  { clave: 'danada', texto: t('Damaged now'), prioridad: 1, ordenable: false, filtro: false },
  { clave: 'nota', texto: t('Remark'), prioridad: 3, ordenable: false, filtro: false },
]
const abiertos = reactive({})
</script>

<template>
  <template v-if="d">
    <router-link :to="`/transporte/embarques/${u.embarque.id}?unidad=${u.id}`" class="volver"><Icono nombre="atras" :tam="15" />{{ tx(u.embarque.codigo) }}</router-link>

    <Asistente v-if="registro" :documento="t('Receipt of {0}', [u.nombre])" :pasos="pasos" :actual="registro.paso" :ocupado="ocupado"
               :con-borrador="false" :texto-final="ajuste ? t('Save adjustment') : t('Save receipt')"
               @ir="(i) => (registro.paso = i)" @anterior="registro.paso--" @siguiente="registro.paso++" @finalizar="guardar" @cerrar="registro = null">
      <!-- 1. Bodega y fecha -->
      <div v-if="registro.paso === 0" class="rejilla-campos">
        <div class="campo"><span class="req">{{ t('Warehouse or bonded warehouse that receives') }}</span>
          <SelectBusqueda v-model="registro.centro" :opciones="bodegas" :etiqueta="t('Warehouse')" />
          <small class="ayuda">{{ t('Plants of the company that receives the shipment. The stock enters this warehouse.') }}</small>
        </div>
        <label class="campo"><span class="req">{{ t('Date received') }}</span>
          <CampoFecha v-model="registro.fecha" :max="hoy()" :min="u.embarque.arribo_real || undefined" />
          <small class="ayuda">{{ t('The day the goods were received, not today: it is what the lead times measure.') }}</small>
        </label>
        <label class="campo ancho-completo"><span :class="{ req: ajuste }">{{ ajuste ? t('Reason for the adjustment') : t('Remark (optional)') }}</span>
          <textarea v-model="registro.observacion" rows="2" maxlength="500"></textarea>
        </label>
        <p v-if="ajuste" class="nota aviso ancho-completo"><Icono nombre="info" />{{ t('An adjustment corrects earlier counts: enter positive quantities to add and negative ones to subtract.') }}</p>
      </div>

      <!-- 2. Conteo -->
      <div v-else-if="registro.paso === 1">
        <div class="fila-flex mb-chico">
          <SelectBusqueda v-model="registro.filtroPl" :opciones="pls" :vacio="t('All packing lists')" :etiqueta="t('Packing list')" />
          <span class="separar"></span>
          <button v-if="!ajuste" type="button" class="btn btn-chico" @click="llenarPendiente"><Icono nombre="check" :tam="14" />{{ t('Fill in what is pending') }}</button>
          <button type="button" class="btn btn-chico btn-fantasma" @click="limpiar">{{ t('Clear') }}</button>
        </div>
        <TablaDatos tabla="recepcion_conteo" :columnas="columnasConteo" :filas="lineasPaso" clave-fila="pl_linea_id" :vistas-guardadas="false" :por-pagina="100" :etiqueta="t('Count')">
          <template #celda-pl="{ fila: l }"><span class="codigo">{{ tx(l.pl) }}</span><span class="sub">{{ tx(l.factura) }}</span></template>
          <template #celda-codigo="{ fila: l }"><span class="codigo">{{ tx(l.codigo) }}</span><template v-if="l.variante || l.talla"> · {{ tx(l.variante || l.talla) }}</template><span class="sub">{{ tx(l.descripcion) }}</span></template>
          <template #celda-enviado="{ fila: l }">{{ fmtCant(l.enviado) }}</template>
          <template #celda-recibido="{ fila: l }">{{ fmtCant(l.recibido) }}</template>
          <template #celda-pendiente="{ fila: l }"><span :class="{ 'texto-aviso': l.pendiente > 0 }">{{ fmtCant(l.pendiente) }}</span></template>
          <template #celda-ahora="{ fila: l }"><input v-model="registro.cantidades[l.pl_linea_id].cantidad" class="celda num ancho-s con-borde" type="number" :min="ajuste ? undefined : 0" step="any" :aria-label="t('Received now {0}', [l.codigo])" /></template>
          <template #celda-danada="{ fila: l }"><input v-model="registro.cantidades[l.pl_linea_id].danada" class="celda num ancho-s con-borde" type="number" :min="ajuste ? undefined : 0" step="any" :aria-label="t('Damaged now {0}', [l.codigo])" /></template>
          <template #celda-nota="{ fila: l }"><input v-model="registro.cantidades[l.pl_linea_id].observacion" class="celda con-borde" maxlength="300" :aria-label="t('Remark {0}', [l.codigo])" /></template>
        </TablaDatos>
      </div>

      <!-- 3. Revisión -->
      <div v-else>
        <div class="empaque-resumen">
          <div class="cifra"><span>{{ t('Warehouse') }}</span><b>{{ tx(registro.centro) }} · {{ tx(nombreBodega(registro.centro)) }}</b></div>
          <div class="cifra"><span>{{ t('Date received') }}</span><b>{{ fmtFecha(registro.fecha) }}</b></div>
          <div class="cifra"><span>{{ t('Lines') }}</span><b>{{ fmtCant(resumenPrevia.lineas) }}</b></div>
          <div class="cifra"><span>{{ t('Quantity') }}</span><b>{{ fmtCant(resumenPrevia.cantidad) }}</b></div>
          <div class="cifra"><span>{{ t('Damaged') }}</span><b>{{ fmtCant(resumenPrevia.danada) }}</b></div>
        </div>
        <ul v-if="errores.length" class="diferencias mt">
          <li v-for="(e, i) in errores" :key="i" class="nota error"><Icono nombre="alerta" />{{ tx(e) }}</li>
        </ul>
        <template v-else>
          <p v-if="resumenPrevia.completa && !ajuste" class="nota ok mt"><Icono nombre="check" />{{ t('With this receipt everything shipped is counted: the load unit will be received.') }}</p>
          <p v-else-if="!ajuste" class="nota info mt"><Icono nombre="info" />{{ t('Lines still pending: {0}. You can record another count later or close the receipt with shortages.', [resumenPrevia.faltantes.length]) }}</p>
          <p v-if="resumenPrevia.sobrantes.length" class="nota aviso mt"><Icono nombre="alerta" />{{ t('Over: {0} lines receive more than shipped; they are reported to the supplier.', [resumenPrevia.sobrantes.length]) }}</p>
          <p v-if="resumenPrevia.danada" class="nota aviso mt"><Icono nombre="alerta" />{{ t('Damaged units are received but not available in stock.') }}</p>
        </template>
      </div>
    </Asistente>

    <template v-else>
      <section class="doc-cabeza">
        <div class="doc-fila">
          <Icono nombre="contenedor" :tam="26" />
          <h1 class="doc-numero">{{ t('Receipt of {0}', [u.nombre]) }}</h1>
          <EstadoBadge :estado="u.recepcion_estado" tipo="recepcion" />
          <span class="doc-sub">{{ tx(u.embarque.codigo) }} · {{ tx(u.tipo) }}</span>
          <div class="doc-acciones">
            <button v-if="acc.contar?.permitida" class="btn btn-primario" @click="iniciar('CONTEO')"><Icono nombre="lista" />{{ t('Record count') }}</button>
            <button v-if="acc.ajustar?.permitida" class="btn" @click="iniciar('AJUSTE')"><Icono nombre="editar" />{{ t('Record adjustment') }}</button>
            <button v-if="acc.sin_conteo?.permitida" class="btn" @click="abrirSinConteo"><Icono nombre="check" />{{ t('Confirm pending without counting') }}</button>
            <button v-if="acc.cerrar?.permitida" class="btn btn-fantasma" @click="abrirCierre"><Icono nombre="candado" />{{ t('Close receipt') }}</button>
          </div>
        </div>
        <p v-if="!acc.contar?.permitida && !acc.ajustar?.permitida && acc.contar?.motivo" class="ayuda bloqueo-motivo"><Icono nombre="info" :tam="14" />{{ tx(acc.contar.motivo) }}</p>
        <div class="doc-datos">
          <div class="dato"><span>{{ t('Warehouse') }}</span><b>{{ u.centro ? `${u.centro} · ${u.centro_nombre || ''}` : t('Not received yet') }}</b></div>
          <div class="dato"><span>{{ t('Actual arrival') }}</span><b>{{ fmtFecha(u.embarque.arribo_real) }}</b></div>
          <div class="dato"><span>{{ t('Customs release') }}</span><b>{{ fmtFecha(u.liberada_en) }}</b></div>
          <div class="dato"><span>{{ t('Delivered to the warehouse') }}</span><b>{{ fmtFecha(u.entregada_en) }}</b></div>
          <div class="dato"><span>{{ t('Received on') }}</span><b>{{ fmtFecha(u.recibida_en) }}</b></div>
        </div>
        <div class="empaque-resumen">
          <div class="cifra"><span>{{ t('Shipped') }}</span><b>{{ fmtCant(d.totales.enviado) }}</b></div>
          <div class="cifra"><span>{{ t('Received') }}</span><b>{{ fmtCant(d.totales.recibido) }}</b></div>
          <div class="cifra"><span>{{ t('Damaged') }}</span><b>{{ fmtCant(d.totales.danado) }}</b></div>
          <div class="cifra"><span>{{ t('Pending') }}</span><b>{{ fmtCant(d.totales.pendiente) }}</b></div>
          <div class="cifra"><span>{{ t('Progress') }}</span><Avance :porcentaje="avance" /></div>
        </div>
      </section>

      <section v-if="d.diferencias.length" class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Differences') }}</h2><p>{{ t('Short, over and damaged quantities against what was shipped. They open one alert per supplier.') }}</p></div></div>
        <ul class="diferencias">
          <li v-for="x in d.diferencias" :key="`${x.pl_linea_id}-${x.tipo}`">
            <span class="etiqueta" :class="x.tipo === 'FALTANTE' ? 'error' : 'aviso'">{{ tx(DIFERENCIA[x.tipo]) }}</span>
            <span class="codigo">{{ tx(x.fila) }}</span>
            <span class="ayuda">{{ t('expected {0} · received {1} · damaged {2}', [fmtCant(x.esperado), fmtCant(x.recibido), fmtCant(x.danado)]) }}</span>
          </li>
        </ul>
      </section>

      <section class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Contents') }}</h2><p>{{ t('What the load unit carries and what has been received of each line.') }}</p></div></div>
        <TablaDatos tabla="recepcion_lineas" :columnas="columnas" :filas="d.lineas" clave-fila="pl_linea_id" :vistas-guardadas="false" :etiqueta="t('Contents')">
          <template #celda-pl="{ fila: l }"><router-link :to="`/packing-lists/${l.pl_id}`" class="enlace codigo">{{ tx(l.pl) }}</router-link><span class="sub">{{ tx(l.factura) }}</span></template>
          <template #celda-codigo="{ fila: l }"><span class="codigo">{{ tx(l.codigo) }}</span><template v-if="l.variante || l.talla"> · {{ tx(l.variante || l.talla) }}</template></template>
          <template #celda-enviado="{ fila: l }">{{ fmtCant(l.enviado) }}</template>
          <template #celda-recibido="{ fila: l }">{{ fmtCant(l.recibido) }}</template>
          <template #celda-danado="{ fila: l }"><span :class="{ 'texto-aviso': l.danado > 0 }">{{ fmtCant(l.danado) }}</span></template>
          <template #celda-pendiente="{ fila: l }">{{ fmtCant(l.pendiente) }}</template>
          <template #celda-diferencia="{ fila: l }">
            <span v-if="l.diferencia < 0 && u.recepcion_estado !== 'RECIBIDA'" class="ayuda">{{ t('Pending') }}</span>
            <span v-else :class="{ 'texto-error': l.diferencia < 0, 'texto-aviso': l.diferencia > 0 }">{{ fmtCant(l.diferencia) }}</span>
          </template>
        </TablaDatos>
      </section>

      <section class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Receipt records') }}</h2><p>{{ t('Each count, adjustment or confirmation, with its warehouse, date and who recorded it.') }}</p></div></div>
        <ul class="linea-tiempo">
          <li v-for="g in d.registros" :key="g.id">
            <span class="ayuda">{{ fmtFecha(g.fecha) }}<br />{{ tx(g.usuario || '') }}</span>
            <span>
              <b>{{ tx(TIPOS[g.tipo] || g.tipo) }}</b> · {{ tx(g.centro) }} {{ tx(g.centro_nombre || '') }}
              <span class="sub">{{ t('{0} · quantity {1} · damaged {2}', [plural(g.lineas, t('line'), t('lines')), fmtCant(g.cantidad), fmtCant(g.danada)]) }}</span>
              <span v-if="g.observacion" class="sub">{{ tx(g.observacion) }}</span>
              <span class="sub">{{ t('Recorded {0}', [fmtFechaHora(g.creado_en)]) }}</span>
              <button type="button" class="btn-texto" @click="abiertos[g.id] = !abiertos[g.id]">{{ abiertos[g.id] ? t('Hide lines') : t('See lines') }}</button>
              <ul v-if="abiertos[g.id]" class="diferencias">
                <li v-for="m in g.movimientos" :key="m.pl_linea_id">
                  <span class="codigo">{{ tx(d.lineas.find((l) => l.pl_linea_id === m.pl_linea_id)?.codigo || '') }}</span>
                  {{ fmtCant(m.cantidad) }}<template v-if="m.danada"> · {{ t('damaged {0}', [fmtCant(m.danada)]) }}</template>
                  <span v-if="m.observacion" class="sub">{{ tx(m.observacion) }}</span>
                </li>
              </ul>
            </span>
          </li>
          <li v-if="!d.registros.length"><span></span><span class="ayuda">{{ t('Nothing received yet.') }}</span></li>
        </ul>
      </section>
    </template>
  </template>

  <Modal v-if="modal?.tipo === 'sin_conteo'" :titulo="t('Confirm pending without counting')" @cerrar="modal = null">
    <p>{{ t('Everything still pending in {0} is recorded as received complete and without damage, under your name. Use it only when the goods were checked another way.', [u.nombre]) }}</p>
    <div class="rejilla-campos">
      <div class="campo"><span class="req">{{ t('Warehouse') }}</span><SelectBusqueda v-model="modal.centro" :opciones="bodegas" :etiqueta="t('Warehouse')" /></div>
      <label class="campo"><span class="req">{{ t('Date received') }}</span><CampoFecha v-model="modal.fecha" :max="hoy()" :min="u.embarque.arribo_real || undefined" /></label>
      <label class="campo ancho-completo"><span>{{ t('Remark (optional)') }}</span><input v-model="modal.observacion" maxlength="500" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.centro || !modal.fecha" @click="confirmar">{{ t('Confirm') }}</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'cerrar'" :titulo="t('Close receipt')" @cerrar="modal = null">
    <p v-if="faltantes.length">{{ t('{0} are still short. Closing records them as final shortages and opens an alert to claim them from the supplier.', [plural(faltantes.length, t('line'), t('lines'))]) }}</p>
    <p v-else>{{ t('The receipt of {0} is closed. Later corrections go as adjustments with a reason.', [u.nombre]) }}</p>
    <label class="campo"><span :class="{ req: faltantes.length }">{{ t('Reason') }}</span><textarea v-model="modal.motivo" maxlength="500"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Back') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || (faltantes.length && !modal.motivo.trim())" @click="confirmar">{{ t('Close receipt') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.diferencias { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.diferencias li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }
</style>
