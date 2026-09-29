<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Anillo from '../components/Anillo.vue'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import CeldaEditable from '../components/CeldaEditable.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import Pasos from '../components/Pasos.vue'
import { avisar, errorApi, guardando, textoDetalle } from '../stores/ui'
import { cantTxt, fmtNum, pct, plural, porUnidadTxt, useSeleccion } from '../utils'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()

const pl = ref(null)
const tab = ref(route.query.tab || '')
const selL = useSeleccion()
const selG = useSeleccion()
const filtro = reactive({ texto: '', solo_pendiente: true })
const modal = ref(null)
const ocupado = ref(false)
const recepcion = reactive({})

const url = (s = '') => `/packing-lists/${props.id}${s}`
const editable = computed(() => !!pl.value?.puede.editar)
const plantillas = computed(() => pl.value?.plantillas || [])
const ref_ = (l) => `${l.estilo || l.codigo_sap}${l.color ? ` ${l.color}` : ''}${l.talla ? ` · talla ${l.talla}` : ''}`

async function cargar() {
  try {
    pl.value = await api.get(url())
    selL.podar(pl.value.lineas.map((l) => l.id))
    selG.podar(pl.value.grupos.map((g) => g.id))
    for (const l of pl.value.lineas) {
      recepcion[l.id] = {
        cantidad_recibida: l.recepcion?.cantidad_recibida ?? l.cantidad,
        cantidad_danada: l.recepcion?.cantidad_danada ?? 0,
        observacion: l.recepcion?.observacion ?? '',
      }
    }
    if (!tab.value || (!editable.value && ['empacar', 'revision'].includes(tab.value))) {
      tab.value = editable.value && pendientes.value.length ? 'empacar' : editable.value ? 'revision' : 'cajas'
    }
  } catch (e) {
    errorApi(e)
    if (e.status === 404) router.push('/facturas')
  }
}

// Ejecuta una acción, recarga y deja el PL al día. Todo o nada en el servidor.
async function accion(fn, exito) {
  ocupado.value = true
  try {
    const r = await guardando(fn())
    if (exito) avisar(typeof exito === 'function' ? exito(r) : exito)
    modal.value = null
    await cargar()
    return r
  } catch (e) {
    if (e.codigo === 'pendientes') modal.value = { tipo: 'pendientes', detalle: e.detalle }
    else {
      errorApi(e)
      if (e.codigo === 'conflicto_version') await cargar()
    }
    return null
  } finally {
    ocupado.value = false
  }
}

watch(tab, (t) => router.replace({ query: { ...route.query, tab: t } }))

// ---- Resumen y avance ------------------------------------------------------
const total = (campo) => Object.values(pl.value?.totales.por_unidad || {}).reduce((a, u) => a + u[campo], 0)
const avanceEmpaque = computed(() => pct(total('en_cajas'), total('cantidad')))
const pendientes = computed(() => (pl.value?.lineas || []).filter((l) => l.sin_caja > 0))
const estimadas = computed(() => (pl.value?.grupos || []).filter((g) => g.peso_estimado))

// Pendientes para finalizar, agrupados en lo que el proveedor tiene que hacer
const revision = computed(() => {
  const v = pl.value?.validaciones || []
  const grupo = (fn) => v.filter(fn)
  const sinCaja = grupo((e) => e.codigo === 'sin_caja')
  const estimado = grupo((e) => e.codigo === 'peso_estimado')
  const medidas = grupo((e) => e.grupo_id && /medidas/.test(e.mensaje))
  const pesos = grupo((e) => e.grupo_id && !e.codigo && !/medidas/.test(e.mensaje))
  const otros = grupo((e) => !e.grupo_id && e.codigo !== 'sin_caja')
  return [
    { clave: 'contenido', titulo: 'Todo el contenido está en cajas', faltan: [...otros, ...sinCaja], accion: 'empacar' },
    { clave: 'medidas', titulo: 'Cada caja tiene medidas', faltan: medidas, accion: 'cajas' },
    { clave: 'pesos', titulo: 'Cada caja tiene peso neto y bruto', faltan: pesos, accion: 'cajas' },
    { clave: 'estimados', titulo: 'Los pesos estimados están confirmados', faltan: estimado, accion: 'confirmar' },
  ]
})
const listoParaFinalizar = computed(() => editable.value && !(pl.value?.validaciones || []).length)

const pasos = computed(() => {
  if (!pl.value) return []
  const fin = pl.value.estado === 'FINALIZADO'
  const empacado = !pendientes.value.length && pl.value.lineas.length > 0
  const datosOk = revision.value.slice(1).every((r) => !r.faltan.length)
  return [
    { titulo: 'Contenido', estado: pl.value.lineas.length ? 'hecho' : 'actual', detalle: `${plural(pl.value.lineas.length, 'fila', 'filas')} · ${porUnidadTxt(pl.value.totales.por_unidad, 'cantidad')}` },
    { titulo: 'Empacar', estado: empacado || fin ? 'hecho' : 'actual', detalle: empacado ? plural(pl.value.totales.cajas, 'caja', 'cajas') : `${porUnidadTxt(pl.value.totales.por_unidad, 'sin_caja')} sin caja` },
    { titulo: 'Medidas y pesos', estado: (empacado && datosOk) || fin ? 'hecho' : estimadas.value.length ? 'alerta' : empacado ? 'actual' : 'pendiente',
      detalle: estimadas.value.length ? `${plural(estimadas.value.length, 'grupo', 'grupos')} con peso estimado` : !pl.value.grupos.length ? 'Después de empacar' : datosOk ? 'Completos' : 'Por completar' },
    { titulo: 'Finalizar', estado: fin ? 'hecho' : listoParaFinalizar.value ? 'actual' : 'pendiente', detalle: fin ? 'Listo para embarcar' : pl.value.estado === 'EN_CORRECCION' ? 'En corrección' : 'Pendiente' },
  ]
})

// ---- Por empacar -----------------------------------------------------------
const partes = computed(() => {
  const cuenta = {}
  const indice = {}
  for (const l of pl.value?.lineas || []) {
    cuenta[l.factura_linea_id] = (cuenta[l.factura_linea_id] || 0) + 1
    indice[l.id] = cuenta[l.factura_linea_id]
  }
  return { cuenta, indice }
})
const lineasFiltradas = computed(() => {
  const q = filtro.texto.trim().toLowerCase()
  return (pl.value?.lineas || []).filter((l) =>
    (!filtro.solo_pendiente || l.sin_caja > 0) &&
    (!q || [l.codigo_sap, l.estilo, l.color, l.talla, l.oc_numero, l.upc].some((v) => (v || '').toLowerCase().includes(q))))
})
const idsFiltrados = computed(() => lineasFiltradas.value.map((l) => l.id))
const selLineas = computed(() => (pl.value?.lineas || []).filter((l) => selL.tiene(l.id)))
const selConPendiente = computed(() => selLineas.value.filter((l) => l.sin_caja > 0))
const resumenSelLineas = computed(() => {
  const r = {}
  for (const l of selLineas.value) r[l.unidad] = (r[l.unidad] || 0) + l.sin_caja
  return `${porUnidadTxt(r, null)} sin caja`
})
const nombrePlantilla = (id) => plantillas.value.find((t) => t.id === id)?.nombre

// La mejor plantilla para una fila: la sugerida por el historial o, si no
// hay, la primera activa con la misma unidad.
function sugerida(l) {
  const s = plantillas.value.find((t) => t.id === l.plantilla_sugerida_id && t.unidad === l.unidad)
  return (s || plantillas.value.find((t) => t.unidad === l.unidad))?.id || ''
}

// ---- Empaque automático: cada fila con su plantilla ------------------------
function abrirAuto(soloSeleccion = false) {
  const filas = (soloSeleccion ? selConPendiente.value : pendientes.value).map((l) => ({
    pl_linea_id: l.id, ref: ref_(l), unidad: l.unidad, sin_caja: l.sin_caja, plantilla_id: sugerida(l),
  }))
  modal.value = { tipo: 'auto', filas, sobrante: 'caja_parcial' }
}
const calculoAuto = computed(() => {
  const m = modal.value
  if (m?.tipo !== 'auto') return null
  let completas = 0
  let parciales = 0
  let sobrante = 0
  let validas = 0
  const filas = m.filas.map((f) => {
    const t = plantillas.value.find((x) => x.id === f.plantilla_id)
    if (!t) return { ...f, cajas: null, sobrante: null }
    validas++
    const cajas = Math.floor(f.sin_caja / t.cantidad_por_caja)
    const resto = f.sin_caja % t.cantidad_por_caja
    completas += cajas
    if (resto) {
      parciales++
      sobrante += resto
    }
    return { ...f, cajas, sobrante: resto }
  })
  return { filas, completas, parciales, sobrante, validas }
})
const plantillasDe = (unidad) => plantillas.value.filter((t) => t.unidad === unidad)
const unidadesAuto = computed(() => [...new Set((modal.value?.filas || []).map((f) => f.unidad))])
function aplicarATodas(unidad, id) {
  if (!id) return
  for (const f of modal.value.filas) if (f.unidad === unidad) f.plantilla_id = Number(id)
}
function empacarAuto() {
  const m = modal.value
  const filas = m.filas.filter((f) => f.plantilla_id).map((f) => ({ pl_linea_id: f.pl_linea_id, plantilla_id: f.plantilla_id }))
  accion(() => api.post(url('/empaque/aplicar'), { version: pl.value.version, filas, sobrante: m.sobrante }), (r) => {
    selL.limpiar()
    const partesTxt = [plural(r.resumen.cajas_completas, 'caja completa', 'cajas completas')]
    if (r.resumen.sobrante_total && m.sobrante === 'caja_parcial') partesTxt.push(plural(r.resumen.filas_con_sobrante, 'caja parcial (confirma su peso)', 'cajas parciales (confirma sus pesos)'))
    if (r.resumen.sobrante_total && m.sobrante === 'sin_caja') partesTxt.push(`${fmtNum(r.resumen.sobrante_total)} quedan sin caja`)
    return `Listo: ${partesTxt.join(' y ')}.`
  }).then((r) => {
    if (r && !pendientes.value.length) tab.value = 'revision'
  })
}

// ---- Caja manual o mixta ---------------------------------------------------
function abrirCaja() {
  modal.value = {
    tipo: 'caja',
    num_cajas: 1,
    plantilla_id: '',
    valores: { largo: '', ancho: '', alto: '', peso_neto_caja: '', peso_bruto_caja: '', observacion: '' },
    items: selConPendiente.value.map((l) => ({
      pl_linea_id: l.id, ref: ref_(l), unidad: l.unidad, sin_caja: l.sin_caja,
      cantidad_por_caja: selConPendiente.value.length === 1 ? l.sin_caja : '',
    })),
  }
}
const plantillaModal = computed(() => plantillas.value.find((t) => t.id === modal.value?.plantilla_id))
const cajaInvalida = computed(() => {
  const m = modal.value
  if (m?.tipo !== 'caja') return true
  return !(m.num_cajas >= 1) || m.items.some((i) => !(i.cantidad_por_caja >= 1) || i.cantidad_por_caja * m.num_cajas > i.sin_caja)
})
function crearCaja() {
  const m = modal.value
  const valores = Object.fromEntries(Object.entries(m.valores).filter(([, v]) => v !== '' && v !== null)
    .map(([k, v]) => [k, k === 'observacion' ? v : Number(v)]))
  accion(() => api.post(url('/cajas'), {
    version: pl.value.version,
    num_cajas: Number(m.num_cajas),
    plantilla_id: m.plantilla_id || null,
    items: m.items.map((i) => ({ pl_linea_id: i.pl_linea_id, cantidad_por_caja: Number(i.cantidad_por_caja) })),
    ...valores,
  }), m.items.length > 1 ? 'Caja mixta creada.' : `Se ${m.num_cajas === 1 ? 'creó 1 caja' : `crearon ${m.num_cajas} cajas`}.`)
  selL.limpiar()
}

// ---- Mover o quitar lo que no está en cajas -------------------------------
function filasMovibles() {
  const base = selConPendiente.value.length ? selConPendiente.value : pendientes.value
  return base.map((l) => ({ pl_linea_id: l.id, ref: ref_(l), unidad: l.unidad, sin_caja: l.sin_caja, cantidad: l.sin_caja }))
}
function abrirMover() {
  modal.value = { tipo: 'mover', destino: pl.value.otros_pl[0]?.id || '', filas: filasMovibles() }
}
function abrirQuitar() {
  modal.value = { tipo: 'quitar', filas: filasMovibles() }
}
const movInvalido = computed(() => (modal.value?.filas || []).some((f) => f.cantidad !== 0 && (!(f.cantidad >= 1) || f.cantidad > f.sin_caja)) ||
  !(modal.value?.filas || []).some((f) => f.cantidad > 0))
const movimientos = () => modal.value.filas.filter((f) => f.cantidad > 0).map((f) => ({ pl_linea_id: f.pl_linea_id, cantidad: Number(f.cantidad) }))
function mover() {
  const m = modal.value
  accion(() => api.post(url('/mover'), { version: pl.value.version, destino_pl_id: m.destino || null, movimientos: movimientos() }),
    (r) => `Cantidades movidas a ${r.destino_numero}.`)
  selL.limpiar()
}
function quitar() {
  accion(() => api.post(url('/quitar'), { version: pl.value.version, movimientos: movimientos() }),
    'Cantidades devueltas a la factura; quedan pendientes de asignar a un packing list.')
  selL.limpiar()
}

// ---- Cajas -----------------------------------------------------------------
const selGrupos = computed(() => (pl.value?.grupos || []).filter((g) => selG.tiene(g.id)))
const idsGrupos = computed(() => (pl.value?.grupos || []).map((g) => g.id))
const cajasSel = computed(() => selGrupos.value.reduce((a, g) => a + g.num_cajas, 0))
const rango = (g) => (g.desde === g.hasta ? `${g.desde}` : `${g.desde}–${g.hasta}`)

const celdaGrupo = (g, campo) => async (valor) => {
  try {
    await guardando(api.patch(url('/cajas'), { version: pl.value.version, grupo_ids: [g.id], [campo]: valor }))
    await cargar()
  } catch (e) {
    errorApi(e)
    if (e.codigo === 'conflicto_version') cargar()
    throw e
  }
}

// Una sola ventana para medidas, pesos, número de cajas y valores de plantilla
function abrirEditarCajas(grupos = selGrupos.value) {
  modal.value = {
    tipo: 'editar_cajas', grupo_ids: grupos.map((g) => g.id), cajas: grupos.reduce((a, g) => a + g.num_cajas, 0), plantilla_id: '',
    valores: { num_cajas: '', largo: '', ancho: '', alto: '', peso_neto_caja: '', peso_bruto_caja: '', observacion: '' },
  }
}
function editarCajas() {
  const m = modal.value
  const valores = Object.fromEntries(Object.entries(m.valores).filter(([, v]) => v !== '')
    .map(([k, v]) => [k, k === 'observacion' ? v : Number(v)]))
  if (!Object.keys(valores).length && !m.plantilla_id) return avisar('Elige una plantilla o escribe al menos un valor.', 'error')
  accion(() => api.patch(url('/cajas'), {
    version: pl.value.version, grupo_ids: m.grupo_ids, ...valores, ...(m.plantilla_id ? { desde_plantilla_id: m.plantilla_id } : {}),
  }), `Se actualizaron ${plural(m.cajas, 'caja', 'cajas')}.`)
}
function confirmarPesos(grupos) {
  accion(() => api.patch(url('/cajas'), { version: pl.value.version, grupo_ids: grupos.map((g) => g.id), confirmar_pesos: true }),
    `Pesos confirmados en ${plural(grupos.length, 'grupo', 'grupos')} de cajas.`)
}
function abrirMoverCajas() {
  modal.value = {
    tipo: 'mover_cajas',
    destino: pl.value.otros_pl[0]?.id || '',
    grupos: selGrupos.value.map((g) => ({ grupo_id: g.id, rango: rango(g), max: g.num_cajas, num_cajas: g.num_cajas })),
  }
}
function moverCajas() {
  const m = modal.value
  accion(() => api.post(url('/mover-cajas'), {
    version: pl.value.version, destino_pl_id: m.destino || null,
    grupos: m.grupos.map((g) => ({ grupo_id: g.grupo_id, num_cajas: Number(g.num_cajas) })),
  }), (r) => `Cajas movidas a ${r.destino_numero} con su contenido.`)
}
function desempacar() {
  accion(() => api.post(url('/cajas/eliminar'), { version: pl.value.version, grupo_ids: selG.lista() }),
    'Cajas desempacadas; su contenido volvió a “Por empacar”.')
}
function guardarPlantilla() {
  accion(() => api.post(url(`/cajas/${modal.value.grupo_id}/plantilla`), { nombre: modal.value.nombre }),
    (r) => `Plantilla “${r.nombre}” guardada; ya la puedes usar al empacar.`)
}

// ---- Estados, recepción y exportación -------------------------------------
const finalizar = () => accion(() => api.post(url('/finalizar'), { version: pl.value.version }), 'Packing list finalizado.')
const agregarPendientes = () => accion(() => api.post(url('/agregar'), { version: pl.value.version }),
  (r) => `Se agregaron ${fmtNum(r.agregado)} desde la factura.`)
function cambiarEstado() {
  const { accion: a, motivo } = modal.value
  accion(() => api.post(url(`/${a}`), { motivo }), (r) => (a === 'reabrir'
    ? `Packing list reabierto.${r.nota ? ` ${r.nota}` : ''}` : 'Packing list cancelado; sus cantidades volvieron a la factura.'))
}
function guardarRecepcion() {
  accion(() => api.post(url('/recepcion'), {
    lineas: pl.value.lineas.map((l) => ({ pl_linea_id: l.id, ...recepcion[l.id], cantidad_recibida: Number(recepcion[l.id].cantidad_recibida), cantidad_danada: Number(recepcion[l.id].cantidad_danada) })),
  }), (r) => (r.diferencias.length ? `Recepción guardada con ${plural(r.diferencias.length, 'diferencia', 'diferencias')}.` : 'Recepción guardada sin diferencias.'))
}
const descargar = () => api.descargar(url('/exportar'), 'packing_list.xlsx').catch(errorApi)

function irA(accionRevision) {
  if (accionRevision === 'confirmar') confirmarPesos(estimadas.value)
  else tab.value = accionRevision
}

onMounted(cargar)
</script>

<template>
  <template v-if="pl">
    <router-link :to="`/facturas/${pl.factura.id}?tab=pl`" class="volver"><Icono nombre="atras" :tam="15" />Factura {{ pl.factura.nombre }}</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ pl.numero }}</span>
        <EstadoBadge :estado="pl.estado" />
        <span class="doc-sub">{{ pl.factura.nombre }} · {{ pl.factura.proveedor }}</span>
        <div class="doc-acciones">
          <button class="btn btn-fantasma" title="Descargar Excel" @click="descargar"><Icono nombre="descargar" />Excel</button>
          <button v-if="pl.puede.reabrir" class="btn" @click="modal = { tipo: 'estado', accion: 'reabrir', motivo: '' }">Reabrir para corregir</button>
          <button v-if="pl.puede.cancelar" class="btn btn-peligro" @click="modal = { tipo: 'estado', accion: 'cancelar', motivo: '' }">Cancelar</button>
          <button v-if="pl.puede.finalizar" class="btn" :class="{ 'btn-primario': listoParaFinalizar }" :disabled="ocupado" @click="listoParaFinalizar ? finalizar() : (tab = 'revision')">
            <Icono nombre="check" />{{ listoParaFinalizar ? 'Finalizar packing list' : `Finalizar (${pl.validaciones.length} pendientes)` }}
          </button>
        </div>
      </div>
      <div class="empaque-resumen">
        <Anillo :porcentaje="avanceEmpaque" titulo="Empacado" :detalle="pendientes.length ? `Faltan ${porUnidadTxt(pl.totales.por_unidad, 'sin_caja')}` : `${porUnidadTxt(pl.totales.por_unidad, 'cantidad')} en cajas`" />
        <div class="cifra"><span>Cajas</span><b>{{ fmtNum(pl.totales.cajas) }}</b></div>
        <div class="cifra"><span>Peso neto</span><b>{{ fmtNum(pl.totales.peso_neto, 1) }} kg</b></div>
        <div class="cifra"><span>Peso bruto</span><b>{{ fmtNum(pl.totales.peso_bruto, 1) }} kg</b></div>
        <div class="cifra"><span>Volumen</span><b>{{ fmtNum(pl.totales.cbm, 2) }} m³</b></div>
        <div class="cifra"><span>Contenedor</span>
          <b v-if="pl.transporte" style="font-size: 0.95rem">{{ pl.transporte.unidad }} · {{ pl.transporte.embarque }} <EstadoBadge :estado="pl.transporte.asignacion" /></b>
          <b v-else class="apagado" style="font-size: 0.95rem">Sin asignar</b>
        </div>
      </div>
      <Pasos :pasos="pasos" />
    </section>

    <p v-if="editable && pl.saldo_factura > 0" class="nota aviso" style="align-items: center">
      <Icono nombre="info" />
      <span>La factura tiene {{ fmtNum(pl.saldo_factura) }} que no están en ningún packing list.</span>
      <button class="btn btn-chico separar" :disabled="ocupado" @click="agregarPendientes"><Icono nombre="mas" :tam="14" />Agregar a {{ pl.numero }}</button>
    </p>

    <div class="pestanas" role="tablist">
      <button v-if="editable" class="pestana" role="tab" :aria-selected="tab === 'empacar'" @click="tab = 'empacar'">
        <Icono nombre="caja" :tam="16" />Por empacar<span class="cuenta" :class="{ alerta: pendientes.length }">{{ pendientes.length }}</span>
      </button>
      <button class="pestana" role="tab" :aria-selected="tab === 'cajas'" @click="tab = 'cajas'">
        <Icono nombre="lista" :tam="16" />Cajas<span class="cuenta">{{ pl.totales.cajas }}</span>
      </button>
      <button v-if="editable" class="pestana" role="tab" :aria-selected="tab === 'revision'" @click="tab = 'revision'">
        <Icono nombre="check" :tam="16" />Revisión<span class="cuenta" :class="{ alerta: pl.validaciones.length }">{{ pl.validaciones.length || '✓' }}</span>
      </button>
      <button v-if="!editable" class="pestana" role="tab" :aria-selected="tab === 'contenido'" @click="tab = 'contenido'">
        <Icono nombre="lista" :tam="16" />Contenido<span class="cuenta">{{ pl.lineas.length }}</span>
      </button>
      <button v-if="pl.puede.recepcion" class="pestana" role="tab" :aria-selected="tab === 'recepcion'" @click="tab = 'recepcion'"><Icono nombre="importar" :tam="16" />Recepción</button>
    </div>

    <!-- Por empacar -->
    <section v-if="tab === 'empacar' && editable">
      <div v-if="!pendientes.length && pl.lineas.length" class="panel vacio">
        <div class="todo-listo" style="justify-content: center">
          <span class="icono-ok"><Icono nombre="check" :tam="22" /></span>
          <div style="text-align: left"><b>Todo está en cajas</b><p class="ayuda">Revisa medidas y pesos y finaliza el packing list.</p></div>
          <button class="btn btn-primario" @click="tab = 'revision'">Ir a revisión<Icono nombre="flecha" :tam="16" /></button>
        </div>
      </div>
      <template v-else>
        <div class="opciones-empaque">
          <button class="opcion recomendada" :disabled="!pendientes.length || !plantillas.length" @click="abrirAuto(selConPendiente.length > 0)">
            <span class="opcion-icono"><Icono nombre="varita" /></span>
            <b>Empacar con plantillas <span class="etiqueta kraft">Recomendado</span></b>
            <span>{{ selConPendiente.length ? `Las ${selConPendiente.length} filas seleccionadas` : `Todas las filas (${pendientes.length})` }} en un paso. Cada producto usa su plantilla de caja; tú decides qué hacer con el sobrante.</span>
            <span v-if="!plantillas.length" class="etiqueta aviso">Crea una plantilla primero</span>
          </button>
          <button class="opcion" :disabled="!selConPendiente.length" @click="abrirCaja">
            <span class="opcion-icono"><Icono nombre="caja" /></span>
            <b>Caja manual o mixta</b>
            <span>{{ selConPendiente.length ? `Con las ${selConPendiente.length} filas seleccionadas.` : 'Selecciona filas abajo.' }} Defines cuántas van por caja; con varias filas es una caja surtida.</span>
          </button>
          <button class="opcion" :disabled="!pendientes.length" @click="abrirMover">
            <span class="opcion-icono"><Icono nombre="mover" /></span>
            <b>Dividir en otro packing list</b>
            <span>Pasa cantidades sin caja a otro PL de la factura (o a uno nuevo), por ejemplo para otro contenedor.</span>
          </button>
        </div>

        <div class="filtros mt">
          <label class="buscador">
            <Icono nombre="buscar" :tam="16" />
            <input v-model="filtro.texto" type="search" placeholder="Filtrar por código, estilo, color, talla u OC" aria-label="Filtrar contenido" />
          </label>
          <div class="segmentos" role="group" aria-label="Mostrar">
            <button class="segmento" :aria-pressed="filtro.solo_pendiente" @click="filtro.solo_pendiente = true">Sin empacar<span class="cuenta">{{ pendientes.length }}</span></button>
            <button class="segmento" :aria-pressed="!filtro.solo_pendiente" @click="filtro.solo_pendiente = false">Todo<span class="cuenta">{{ pl.lineas.length }}</span></button>
          </div>
        </div>
        <div class="tabla-marco">
          <table class="tabla">
            <thead>
              <tr>
                <th class="chk"><input type="checkbox" aria-label="Seleccionar todas las filas filtradas" :checked="selL.todos(idsFiltrados)" @change="selL.alternarTodos(idsFiltrados)" /></th>
                <th>Producto</th>
                <th>Talla</th>
                <th>OC / pos.</th>
                <th class="num">Cantidad</th>
                <th class="num">En cajas</th>
                <th class="num">Sin caja</th>
                <th>Plantilla sugerida</th>
                <th>Empaque</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="l in lineasFiltradas" :key="l.id" :class="{ seleccionada: selL.tiene(l.id) }">
                <td class="chk"><input type="checkbox" :aria-label="`Seleccionar ${ref_(l)}`" :checked="selL.tiene(l.id)" @change="selL.alternar(l.id)" /></td>
                <td>{{ l.estilo }} · {{ l.color }}
                  <span v-if="partes.cuenta[l.factura_linea_id] > 1" class="etiqueta">parte {{ partes.indice[l.id] }}</span>
                  <span class="sub codigo">{{ l.codigo_sap }}</span>
                </td>
                <td><strong>{{ l.talla }}</strong></td>
                <td class="codigo">{{ l.oc_numero }} / {{ l.posicion }}</td>
                <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
                <td class="num">{{ fmtNum(l.en_cajas) }}</td>
                <td class="num"><strong v-if="l.sin_caja">{{ fmtNum(l.sin_caja) }}</strong><span v-else class="apagado">0</span></td>
                <td>
                  <span v-if="sugerida(l)">{{ nombrePlantilla(sugerida(l)) }}<span v-if="l.plantilla_sugerida_id === sugerida(l)" class="etiqueta info" title="Es la que usaste la última vez con este producto">usada antes</span></span>
                  <span v-else class="apagado">Sin plantilla para {{ l.unidad === 'PAR' ? 'pares' : 'unidades' }}</span>
                </td>
                <td>
                  <EstadoBadge :estado="l.estado_empaque" />
                  <span v-if="l.en_parcial" class="etiqueta aviso">caja parcial</span>
                </td>
              </tr>
              <tr v-if="!lineasFiltradas.length">
                <td colspan="9" class="vacio">{{ pl.lineas.length ? 'Ninguna fila coincide con el filtro.' : 'El packing list está vacío.' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <BarraSeleccion :cantidad="selL.ids.size" singular="fila seleccionada" plural="filas seleccionadas" @limpiar="selL.limpiar()">
          <template #resumen>{{ resumenSelLineas }}</template>
          <button class="btn btn-primario" :disabled="!selConPendiente.length || !plantillas.length" @click="abrirAuto(true)"><Icono nombre="varita" :tam="15" />Empacar con plantillas</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirCaja"><Icono nombre="caja" :tam="15" />{{ selConPendiente.length > 1 ? 'Caja mixta' : 'Caja manual' }}</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirMover"><Icono nombre="mover" :tam="15" />Mover a otro PL</button>
          <button class="btn btn-peligro" :disabled="!selConPendiente.length" @click="abrirQuitar">Quitar del PL</button>
        </BarraSeleccion>
      </template>
    </section>

    <!-- Cajas -->
    <section v-if="tab === 'cajas'">
      <p v-if="editable && estimadas.length" class="nota aviso" style="align-items: center; margin-bottom: 12px">
        <Icono nombre="escala" />
        <span>{{ plural(estimadas.length, 'grupo de cajas tiene', 'grupos de cajas tienen') }} peso estimado (cajas parciales). Pésalas y corrige, o confirma el estimado.</span>
        <button class="btn btn-chico separar" :disabled="ocupado" @click="confirmarPesos(estimadas)">Confirmar todos los estimados</button>
      </p>
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Seleccionar todas las cajas" :checked="selG.todos(idsGrupos)" @change="selG.alternarTodos(idsGrupos)" /></th>
              <th>Cajas</th>
              <th>Contenido por caja</th>
              <th class="num">N.º</th>
              <th class="num">Largo</th>
              <th class="num">Ancho</th>
              <th class="num">Alto cm</th>
              <th class="num">Neto/caja</th>
              <th class="num">Bruto/caja kg</th>
              <th class="num">m³</th>
              <th class="num">Bruto total</th>
              <th>Notas</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in pl.grupos" :key="g.id" :class="{ seleccionada: selG.tiene(g.id) }">
              <td class="chk"><input type="checkbox" :aria-label="`Seleccionar cajas ${rango(g)}`" :checked="selG.tiene(g.id)" @change="selG.alternar(g.id)" /></td>
              <td class="cajas-rango">{{ rango(g) }}</td>
              <td class="envolver">
                <div class="caja-items">
                  <div v-for="it in g.items" :key="it.pl_linea_id">
                    {{ it.estilo }} <b>{{ it.talla }}</b> × {{ cantTxt(it.cantidad_por_caja, it.unidad) }}
                  </div>
                </div>
              </td>
              <td class="num" style="width: 70px">
                <CeldaEditable v-if="editable" tipo="number" :min="1" paso="1" :valor="g.num_cajas" :guardar="celdaGrupo(g, 'num_cajas')" etiqueta="Número de cajas" />
                <template v-else>{{ g.num_cajas }}</template>
              </td>
              <td v-for="campo in ['largo', 'ancho', 'alto', 'peso_neto_caja', 'peso_bruto_caja']" :key="campo" class="num" style="width: 82px">
                <CeldaEditable v-if="editable" tipo="number" :min="0" :valor="g[campo]" :guardar="celdaGrupo(g, campo)" vacia-texto="Falta" :etiqueta="campo.replaceAll('_', ' ')" />
                <template v-else>{{ fmtNum(g[campo], campo.startsWith('peso') ? 2 : 0) }}</template>
              </td>
              <td class="num">{{ fmtNum(g.cbm_total, 3) }}</td>
              <td class="num">{{ fmtNum(g.peso_bruto_total, 1) }}</td>
              <td>
                <span v-if="g.mixta" class="etiqueta">Mixta</span>
                <span v-if="g.es_parcial" class="etiqueta aviso">Parcial</span>
                <span v-if="g.peso_estimado" class="etiqueta error">Peso estimado</span>
                <span v-if="g.plantilla_nombre" class="sub">{{ g.plantilla_nombre }}</span>
                <span v-if="g.observacion" class="sub">{{ g.observacion }}</span>
              </td>
            </tr>
            <tr v-if="!pl.grupos.length">
              <td colspan="12" class="vacio">
                <Icono nombre="caja" :tam="28" />
                <p>Todavía no hay cajas.</p>
                <button v-if="editable" class="btn btn-primario" @click="tab = 'empacar'">Empezar a empacar</button>
              </td>
            </tr>
          </tbody>
          <tfoot v-if="pl.grupos.length">
            <tr>
              <td></td>
              <td colspan="2">Total</td>
              <td class="num">{{ fmtNum(pl.totales.cajas) }}</td>
              <td colspan="5"></td>
              <td class="num">{{ fmtNum(pl.totales.cbm, 3) }}</td>
              <td class="num">{{ fmtNum(pl.totales.peso_bruto, 1) }}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <BarraSeleccion :cantidad="selG.ids.size" singular="grupo seleccionado" plural="grupos seleccionados" @limpiar="selG.limpiar()">
        <template #resumen>{{ plural(cajasSel, 'caja', 'cajas') }}</template>
        <template v-if="editable">
          <button class="btn btn-primario" @click="abrirEditarCajas()"><Icono nombre="editar" :tam="15" />Medidas y pesos</button>
          <button v-if="selGrupos.some((g) => g.peso_estimado)" class="btn" :disabled="ocupado" @click="confirmarPesos(selGrupos.filter((g) => g.peso_estimado))">Confirmar pesos</button>
          <button class="btn" @click="abrirMoverCajas"><Icono nombre="mover" :tam="15" />Mover a otro PL</button>
          <button class="btn" :disabled="selGrupos.length !== 1 || selGrupos[0].mixta" title="Solo cajas de un solo producto" @click="modal = { tipo: 'guardar_plantilla', grupo_id: selGrupos[0].id, nombre: '' }"><Icono nombre="capas" :tam="15" />Guardar como plantilla</button>
          <button class="btn btn-peligro" @click="modal = { tipo: 'desempacar' }">Desempacar</button>
        </template>
      </BarraSeleccion>
    </section>

    <!-- Revisión -->
    <section v-if="tab === 'revision' && editable" class="dos-columnas">
      <div class="panel">
        <div class="panel-cabeza"><div><h2>Antes de finalizar</h2><p>Todo debe estar en verde. Cada punto te lleva a resolverlo.</p></div></div>
        <ul class="checklist">
          <li v-for="r in revision" :key="r.clave" :class="r.faltan.length ? 'falta' : 'ok'">
            <span class="marca"><Icono :nombre="r.faltan.length ? 'alerta' : 'check'" :tam="14" /></span>
            <span>
              {{ r.titulo }}
              <span v-if="r.faltan.length" class="sub ayuda">{{ r.faltan.slice(0, 3).map((e) => e.mensaje).join(' ') }}<template v-if="r.faltan.length > 3"> Y {{ r.faltan.length - 3 }} más.</template></span>
            </span>
            <button v-if="r.faltan.length" class="btn btn-chico" :disabled="ocupado" @click="irA(r.accion)">
              {{ { empacar: 'Empacar', cajas: 'Ir a cajas', confirmar: 'Confirmar estimados' }[r.accion] }}
            </button>
          </li>
        </ul>
        <div class="fila-flex mt">
          <button v-if="pl.puede.finalizar" class="btn btn-primario btn-grande" :disabled="ocupado || !listoParaFinalizar" @click="finalizar"><Icono nombre="check" />Finalizar packing list</button>
          <span v-if="!listoParaFinalizar" class="ayuda">{{ plural(pl.validaciones.length, 'pendiente', 'pendientes') }}</span>
        </div>
      </div>
      <div class="panel">
        <div class="panel-cabeza"><div><h2>Resumen del packing list</h2><p>Así saldrá en el Excel.</p></div></div>
        <div class="doc-datos" style="margin-top: 0; padding-top: 0; border-top: 0">
          <div class="dato"><span>Contenido</span><b>{{ porUnidadTxt(pl.totales.por_unidad, 'cantidad') }}</b></div>
          <div class="dato"><span>Cajas</span><b>{{ fmtNum(pl.totales.cajas) }}</b></div>
          <div class="dato"><span>Peso neto</span><b>{{ fmtNum(pl.totales.peso_neto, 2) }} kg</b></div>
          <div class="dato"><span>Peso bruto</span><b>{{ fmtNum(pl.totales.peso_bruto, 2) }} kg</b></div>
          <div class="dato"><span>Volumen</span><b>{{ fmtNum(pl.totales.cbm, 3) }} m³</b></div>
          <div class="dato"><span>Filas</span><b>{{ pl.lineas.length }}</b></div>
        </div>
      </div>
    </section>

    <!-- Contenido (solo lectura) -->
    <section v-if="tab === 'contenido'">
      <div class="tabla-marco">
        <table class="tabla">
          <thead><tr><th>Producto</th><th>Talla</th><th>OC / pos.</th><th class="num">Cantidad</th><th class="num">En cajas</th><th>Empaque</th></tr></thead>
          <tbody>
            <tr v-for="l in pl.lineas" :key="l.id">
              <td>{{ l.estilo }} · {{ l.color }}<span class="sub codigo">{{ l.codigo_sap }}</span></td>
              <td><strong>{{ l.talla }}</strong></td>
              <td class="codigo">{{ l.oc_numero }} / {{ l.posicion }}</td>
              <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
              <td class="num">{{ fmtNum(l.en_cajas) }}</td>
              <td><EstadoBadge :estado="l.estado_empaque" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Recepción -->
    <section v-if="tab === 'recepcion'" class="panel">
      <div class="panel-cabeza">
        <div><h2>Recepción en bodega</h2><p>Registra lo recibido y lo dañado por fila; las diferencias quedan en el historial.</p></div>
        <button class="btn btn-primario" :disabled="ocupado" @click="guardarRecepcion">Guardar recepción</button>
      </div>
      <div class="tabla-marco" style="box-shadow: none">
        <table class="tabla">
          <thead>
            <tr><th>Fila</th><th class="num">Según PL</th><th class="num">Recibida</th><th class="num">Dañada</th><th class="num">Diferencia</th><th>Observación</th></tr>
          </thead>
          <tbody>
            <tr v-for="l in pl.lineas" :key="l.id">
              <td>{{ l.estilo }} <b>{{ l.talla }}</b><span class="sub codigo">{{ l.codigo_sap }}</span></td>
              <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
              <td class="num"><input v-model.number="recepcion[l.id].cantidad_recibida" class="celda num" type="number" min="0" style="width: 90px; border-color: var(--linea)" :aria-label="`Recibida ${ref_(l)}`" /></td>
              <td class="num"><input v-model.number="recepcion[l.id].cantidad_danada" class="celda num" type="number" min="0" style="width: 80px; border-color: var(--linea)" :aria-label="`Dañada ${ref_(l)}`" /></td>
              <td class="num">
                <span :class="{ 'etiqueta error': recepcion[l.id].cantidad_recibida !== l.cantidad }">{{ fmtNum(recepcion[l.id].cantidad_recibida - l.cantidad) }}</span>
              </td>
              <td><input v-model="recepcion[l.id].observacion" class="celda" style="border-color: var(--linea)" :aria-label="`Observación ${ref_(l)}`" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>

  <!-- Modales -->
  <Modal v-if="modal?.tipo === 'auto'" titulo="Empacar con plantillas" ancho="820px" @cerrar="modal = null">
    <p class="ayuda">Cada fila se empaca en cajas completas con la plantilla que elijas. Ya viene sugerida la que usaste antes con cada producto.</p>
    <div class="fila-flex">
      <label v-for="u in unidadesAuto" :key="u" class="campo" style="min-width: 240px">
        <span>Usar para todas las filas en {{ u === 'PAR' ? 'pares' : 'unidades' }}</span>
        <select @change="aplicarATodas(u, $event.target.value); $event.target.value = ''">
          <option value="">Elegir plantilla…</option>
          <option v-for="t in plantillasDe(u)" :key="t.id" :value="t.id">{{ t.nombre }} ({{ t.cantidad_por_caja }} por caja)</option>
        </select>
      </label>
    </div>
    <div class="tabla-marco" style="max-height: 320px; overflow-y: auto; box-shadow: none">
      <table class="tabla">
        <thead><tr><th>Fila</th><th class="num">Sin caja</th><th>Plantilla</th><th class="num">Cajas</th><th class="num">Sobrante</th></tr></thead>
        <tbody>
          <tr v-for="(f, i) in calculoAuto.filas" :key="f.pl_linea_id">
            <td>{{ f.ref }}</td>
            <td class="num">{{ cantTxt(f.sin_caja, f.unidad) }}</td>
            <td>
              <select v-model="modal.filas[i].plantilla_id" class="entrada" style="max-width: 240px" :aria-label="`Plantilla para ${f.ref}`">
                <option value="">No empacar esta fila</option>
                <option v-for="t in plantillasDe(f.unidad)" :key="t.id" :value="t.id">{{ t.nombre }} ({{ t.cantidad_por_caja }})</option>
              </select>
            </td>
            <template v-if="f.cajas !== null">
              <td class="num">{{ f.cajas }}</td>
              <td class="num"><span :class="{ 'etiqueta aviso': f.sobrante }">{{ f.sobrante }}</span></td>
            </template>
            <td v-else colspan="2" class="apagado">Se omite</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="nota bloque">
      Se crearán <b>{{ plural(calculoAuto.completas, 'caja completa', 'cajas completas') }}</b> en {{ plural(calculoAuto.validas, 'fila', 'filas') }}.
    </div>
    <div v-if="calculoAuto.sobrante" class="nota aviso bloque">
      {{ plural(calculoAuto.parciales, 'fila deja', 'filas dejan') }} un sobrante que no llena una caja ({{ fmtNum(calculoAuto.sobrante) }} en total). ¿Qué hacemos con él?
      <label class="check mt-chico"><input v-model="modal.sobrante" type="radio" value="caja_parcial" /> Una caja parcial por fila, con las medidas de la plantilla y el peso estimado (lo confirmas después)</label>
      <label class="check mt-chico"><input v-model="modal.sobrante" type="radio" value="sin_caja" /> Dejarlo sin caja para armar cajas mixtas a mano</label>
    </div>
    <template #pie>
      <router-link class="btn btn-fantasma" to="/plantillas" style="margin-right: auto">Administrar plantillas</router-link>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || !calculoAuto.validas" @click="empacarAuto"><Icono nombre="varita" :tam="15" />Empacar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'caja'" :titulo="modal.items.length > 1 ? 'Caja mixta' : 'Caja manual'" ancho="700px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span>Número de cajas iguales</span><input v-model.number="modal.num_cajas" type="number" min="1" /></label>
      <label class="campo"><span>Medidas y pesos de una plantilla (opcional)</span>
        <select v-model="modal.plantilla_id">
          <option value="">Sin plantilla</option>
          <option v-for="t in plantillas" :key="t.id" :value="t.id">{{ t.nombre }}</option>
        </select>
      </label>
    </div>
    <div class="tabla-marco" style="box-shadow: none">
      <table class="tabla">
        <thead><tr><th>Fila</th><th class="num">Sin caja</th><th class="num">Por caja</th><th class="num">Total</th></tr></thead>
        <tbody>
          <tr v-for="i in modal.items" :key="i.pl_linea_id">
            <td>{{ i.ref }}</td>
            <td class="num">{{ cantTxt(i.sin_caja, i.unidad) }}</td>
            <td class="num"><input v-model.number="i.cantidad_por_caja" class="celda num" type="number" min="1" style="width: 90px; border-color: var(--linea)" :aria-label="`Por caja ${i.ref}`" /></td>
            <td class="num"><span :class="{ 'etiqueta error': i.cantidad_por_caja * modal.num_cajas > i.sin_caja }">{{ fmtNum((i.cantidad_por_caja || 0) * modal.num_cajas) }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">Deja en blanco lo que quieras tomar de la plantilla{{ plantillaModal ? ` (${plantillaModal.largo}×${plantillaModal.ancho}×${plantillaModal.alto} cm, ${plantillaModal.peso_bruto} kg bruto)` : '' }}.</p>
    <div class="rejilla-campos">
      <label class="campo"><span>Largo cm</span><input v-model="modal.valores.largo" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Ancho cm</span><input v-model="modal.valores.ancho" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Alto cm</span><input v-model="modal.valores.alto" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso neto por caja kg</span><input v-model="modal.valores.peso_neto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso bruto por caja kg</span><input v-model="modal.valores.peso_bruto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Observación</span><input v-model="modal.valores.observacion" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || cajaInvalida" @click="crearCaja">Crear</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover' || modal?.tipo === 'quitar'" :titulo="modal.tipo === 'mover' ? 'Dividir en otro packing list' : 'Quitar del packing list'" ancho="660px" @cerrar="modal = null">
    <label v-if="modal.tipo === 'mover'" class="campo"><span>Destino</span>
      <select v-model="modal.destino">
        <option v-for="o in pl.otros_pl" :key="o.id" :value="o.id">{{ o.numero }}</option>
        <option value="">Un packing list nuevo</option>
      </select>
    </label>
    <p v-else class="ayuda">La cantidad vuelve a la factura como pendiente de asignar a un packing list.</p>
    <div class="tabla-marco" style="max-height: 300px; overflow-y: auto; box-shadow: none">
      <table class="tabla">
        <thead><tr><th>Fila</th><th class="num">Sin caja</th><th class="num">{{ modal.tipo === 'mover' ? 'Mover' : 'Quitar' }}</th></tr></thead>
        <tbody>
          <tr v-for="fm in modal.filas" :key="fm.pl_linea_id">
            <td>{{ fm.ref }}</td>
            <td class="num">{{ cantTxt(fm.sin_caja, fm.unidad) }}</td>
            <td class="num"><input v-model.number="fm.cantidad" class="celda num" type="number" min="0" :max="fm.sin_caja" style="width: 90px; border-color: var(--linea)" :aria-label="`Cantidad ${fm.ref}`" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">Pon 0 en las filas que no quieras tocar. Solo se mueve lo que está sin caja; para llevar cajas completas usa “Mover a otro PL” en la pestaña Cajas.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || movInvalido" @click="modal.tipo === 'mover' ? mover() : quitar()">
        {{ modal.tipo === 'mover' ? 'Mover' : 'Quitar del PL' }}
      </button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'editar_cajas'" :titulo="`Medidas y pesos de ${plural(modal.cajas, 'caja', 'cajas')}`" ancho="640px" @cerrar="modal = null">
    <label class="campo"><span>Copiar de una plantilla (opcional)</span>
      <select v-model="modal.plantilla_id">
        <option value="">No copiar</option>
        <option v-for="t in plantillas" :key="t.id" :value="t.id">{{ t.nombre }} · {{ t.largo }}×{{ t.ancho }}×{{ t.alto }} cm, {{ t.peso_bruto }} kg</option>
      </select>
    </label>
    <p class="ayuda">Deja en blanco lo que no quieras cambiar. Lo que escribas aquí manda sobre la plantilla. Capturar un peso quita la marca de estimado.</p>
    <div class="rejilla-campos">
      <label class="campo"><span>Largo cm</span><input v-model="modal.valores.largo" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Ancho cm</span><input v-model="modal.valores.ancho" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Alto cm</span><input v-model="modal.valores.alto" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso neto por caja kg</span><input v-model="modal.valores.peso_neto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso bruto por caja kg</span><input v-model="modal.valores.peso_bruto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Cajas por grupo</span><input v-model="modal.valores.num_cajas" type="number" min="1" /></label>
      <label class="campo" style="grid-column: 1 / -1"><span>Observación</span><input v-model="modal.valores.observacion" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="editarCajas">Aplicar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover_cajas'" titulo="Mover cajas a otro packing list" ancho="600px" @cerrar="modal = null">
    <label class="campo"><span>Destino</span>
      <select v-model="modal.destino">
        <option v-for="o in pl.otros_pl" :key="o.id" :value="o.id">{{ o.numero }}</option>
        <option value="">Un packing list nuevo</option>
      </select>
    </label>
    <div class="tabla-marco" style="box-shadow: none">
      <table class="tabla">
        <thead><tr><th>Cajas</th><th class="num">Hay</th><th class="num">Mover</th></tr></thead>
        <tbody>
          <tr v-for="gm in modal.grupos" :key="gm.grupo_id">
            <td class="cajas-rango">{{ gm.rango }}</td>
            <td class="num">{{ gm.max }}</td>
            <td class="num"><input v-model.number="gm.num_cajas" class="celda num" type="number" min="1" :max="gm.max" style="width: 80px; border-color: var(--linea)" :aria-label="`Cajas a mover de ${gm.rango}`" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">El contenido viaja con sus cajas. La numeración se recalcula en ambos packing lists.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || modal.grupos.some((g) => !(g.num_cajas >= 1) || g.num_cajas > g.max)" @click="moverCajas">Mover cajas</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'guardar_plantilla'" titulo="Guardar como plantilla" @cerrar="modal = null">
    <label class="campo"><span>Nombre de la plantilla</span><input v-model="modal.nombre" placeholder="Por ejemplo: Caja 12 pares talla grande" /></label>
    <p class="ayuda">Guarda la cantidad por caja, medidas y pesos para usarla en el empaque automático.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.nombre.trim()" @click="guardarPlantilla">Guardar plantilla</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'desempacar'" titulo="Desempacar cajas" @cerrar="modal = null">
    <p>Se eliminan {{ plural(cajasSel, 'caja', 'cajas') }} y su contenido vuelve a “Por empacar”.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="desempacar">Desempacar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pendientes'" titulo="Pendientes para finalizar" ancho="620px" @cerrar="modal = null">
    <ul class="lista-mensajes"><li v-for="(d, i) in modal.detalle" :key="i">{{ textoDetalle(d) }}</li></ul>
    <template #pie><button class="btn btn-primario" @click="modal = null; tab = 'revision'">Ver en revisión</button></template>
  </Modal>

  <Modal v-if="modal?.tipo === 'estado'" :titulo="modal.accion === 'reabrir' ? 'Reabrir packing list' : 'Cancelar packing list'" @cerrar="modal = null">
    <p v-if="modal.accion === 'reabrir'">Vuelve a ser editable. Si estaba confirmado en un contenedor, la asignación pasa a tentativa.</p>
    <p v-else>Sus cantidades vuelven a la factura como pendientes de asignar.</p>
    <label class="campo"><span>Motivo{{ modal.accion === 'cancelar' && pl?.estado === 'BORRADOR' ? ' (opcional)' : '' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn" :class="modal.accion === 'cancelar' ? 'btn-peligro' : 'btn-primario'" :disabled="ocupado" @click="cambiarEstado">
        {{ modal.accion === 'reabrir' ? 'Reabrir' : 'Cancelar packing list' }}
      </button>
    </template>
  </Modal>
</template>
