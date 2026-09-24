<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import CeldaEditable from '../components/CeldaEditable.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Modal from '../components/Modal.vue'
import { avisar, errorApi, guardando, textoDetalle } from '../stores/ui'
import { cantTxt, fmtNum, plural, porUnidadTxt, useSeleccion } from '../utils'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()

const pl = ref(null)
const plantillas = ref([])
const tab = ref(route.query.tab || 'contenido')
const selL = useSeleccion()
const selG = useSeleccion()
const filtro = reactive({ texto: '', empaque: '' })
const modal = ref(null)
const ocupado = ref(false)
const recepcion = reactive({})

const url = (s = '') => `/packing-lists/${props.id}${s}`
const editable = computed(() => !!pl.value?.puede.editar)

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
  } catch (e) {
    errorApi(e)
    if (e.status === 404) router.push('/facturas')
  }
}

async function cargarPlantillas() {
  try {
    plantillas.value = await api.get('/plantillas', { proveedor_id: pl.value.factura.proveedor_id })
  } catch (e) {
    errorApi(e)
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

// ---- Contenido -------------------------------------------------------------
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
    (!filtro.empaque || l.estado_empaque === filtro.empaque) &&
    (!q || [l.codigo_sap, l.estilo, l.color, l.talla, l.oc_numero, l.upc].some((v) => (v || '').toLowerCase().includes(q))))
})
const idsFiltrados = computed(() => lineasFiltradas.value.map((l) => l.id))
const selLineas = computed(() => (pl.value?.lineas || []).filter((l) => selL.tiene(l.id)))
const selConPendiente = computed(() => selLineas.value.filter((l) => l.sin_caja > 0))
const resumenSelLineas = computed(() => {
  const r = {}
  for (const l of selLineas.value) r[l.unidad] = (r[l.unidad] || 0) + l.sin_caja
  return `sin caja: ${porUnidadTxt(r, null)}`
})
const ref_ = (l) => `${l.codigo_sap}${l.talla ? ` talla ${l.talla}` : ''}`

// Aplicar plantilla con vista previa y decisión única sobre el sobrante
async function abrirPlantilla() {
  await cargarPlantillas()
  const primera = selConPendiente.value[0] || selLineas.value[0]
  const sugerida = plantillas.value.find((t) => t.id === primera?.plantilla_sugerida_id) ||
    plantillas.value.find((t) => t.unidad === primera?.unidad)
  modal.value = { tipo: 'plantilla', plantilla_id: sugerida?.id || '', reemplazar: false, previa: null, sobrante: 'caja_parcial' }
  if (sugerida) previsualizar()
}

async function previsualizar() {
  const m = modal.value
  if (!m?.plantilla_id) return
  try {
    m.previa = await api.post(url('/plantilla/previa'), { plantilla_id: m.plantilla_id, pl_linea_ids: selL.lista(), reemplazar: m.reemplazar })
  } catch (e) {
    errorApi(e)
  }
}

function aplicarPlantilla() {
  const m = modal.value
  accion(() => api.post(url('/plantilla/aplicar'), {
    version: pl.value.version, plantilla_id: m.plantilla_id, pl_linea_ids: selL.lista(),
    reemplazar: m.reemplazar, sobrante: m.sobrante,
  }), (r) => `Se crearon ${plural(r.resumen.cajas_completas, 'caja completa', 'cajas completas')}` +
    (r.resumen.sobrante_total ? (m.sobrante === 'caja_parcial' ? ` y ${plural(r.resumen.filas_con_sobrante, 'caja parcial', 'cajas parciales')}.` : `; quedan ${fmtNum(r.resumen.sobrante_total)} sin caja para revisar.`) : '.'))
}

async function abrirCaja() {
  await cargarPlantillas()
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
  }), m.items.length > 1 ? 'Caja mixta creada.' : `Se crearon ${m.num_cajas} cajas.`)
}

async function abrirSobrante() {
  await cargarPlantillas()
  modal.value = { tipo: 'sobrante', plantilla_id: '' }
}

function empacarSobrante() {
  accion(() => api.post(url('/cajas/sobrante'), {
    version: pl.value.version, pl_linea_ids: selConPendiente.value.map((l) => l.id), plantilla_id: modal.value.plantilla_id || null,
  }), (r) => `Se creó una caja parcial en ${plural(r.cajas, 'fila', 'filas')}. Revisa y confirma sus pesos.`)
}

function abrirDividir() {
  const l = selLineas.value[0]
  modal.value = { tipo: 'dividir', linea: l, partes: [Math.floor(l.sin_caja / 2) || 1] }
}
const sumaPartes = computed(() => (modal.value?.partes || []).reduce((a, b) => a + (Number(b) || 0), 0))
function dividir() {
  const m = modal.value
  accion(() => api.post(url('/dividir'), { version: pl.value.version, pl_linea_id: m.linea.id, partes: m.partes.map(Number) }),
    `Fila dividida en ${m.partes.length + 1} partes.`)
}

function filasMovibles() {
  return selConPendiente.value.map((l) => ({ pl_linea_id: l.id, ref: ref_(l), unidad: l.unidad, sin_caja: l.sin_caja, cantidad: l.sin_caja }))
}
function abrirMover() {
  modal.value = { tipo: 'mover', destino: pl.value.otros_pl[0]?.id || '', filas: filasMovibles() }
}
function abrirQuitar() {
  modal.value = { tipo: 'quitar', filas: filasMovibles() }
}
const movInvalido = computed(() => (modal.value?.filas || []).some((f) => !(f.cantidad >= 1) || f.cantidad > f.sin_caja))
function mover() {
  const m = modal.value
  accion(() => api.post(url('/mover'), {
    version: pl.value.version, destino_pl_id: m.destino || null,
    movimientos: m.filas.map((f) => ({ pl_linea_id: f.pl_linea_id, cantidad: Number(f.cantidad) })),
  }), (r) => `Cantidades movidas a ${r.destino_numero}.`)
}
function quitar() {
  accion(() => api.post(url('/quitar'), {
    version: pl.value.version,
    movimientos: modal.value.filas.map((f) => ({ pl_linea_id: f.pl_linea_id, cantidad: Number(f.cantidad) })),
  }), 'Cantidades devueltas a la factura; ya puedes asignarlas a otro packing list.')
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

function abrirEditarCajas() {
  modal.value = { tipo: 'editar_cajas', valores: { num_cajas: '', largo: '', ancho: '', alto: '', peso_neto_caja: '', peso_bruto_caja: '', observacion: '' } }
}
function editarCajas() {
  const valores = Object.fromEntries(Object.entries(modal.value.valores).filter(([, v]) => v !== '')
    .map(([k, v]) => [k, k === 'observacion' ? v : Number(v)]))
  if (!Object.keys(valores).length) return avisar('Escribe al menos un valor.', 'error')
  accion(() => api.patch(url('/cajas'), { version: pl.value.version, grupo_ids: selG.lista(), ...valores }),
    `Se actualizaron ${plural(selG.ids.size, 'grupo', 'grupos')} de cajas.`)
}
async function abrirPlantillaCajas() {
  await cargarPlantillas()
  modal.value = { tipo: 'cajas_plantilla', plantilla_id: plantillas.value[0]?.id || '' }
}
function valoresDePlantilla() {
  accion(() => api.patch(url('/cajas'), { version: pl.value.version, grupo_ids: selG.lista(), desde_plantilla_id: modal.value.plantilla_id }),
    'Medidas y pesos copiados de la plantilla. La plantilla no cambió.')
}
function confirmarPesos() {
  accion(() => api.patch(url('/cajas'), { version: pl.value.version, grupo_ids: selG.lista(), confirmar_pesos: true }), 'Pesos confirmados.')
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
    'Cajas desempacadas; su contenido quedó sin caja.')
}
function guardarPlantilla() {
  accion(() => api.post(url(`/cajas/${modal.value.grupo_id}/plantilla`), { nombre: modal.value.nombre }),
    (r) => `Plantilla “${r.nombre}” guardada.`)
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

onMounted(cargar)
</script>

<template>
  <template v-if="pl">
    <router-link :to="`/facturas/${pl.factura.id}?tab=pl`" class="volver">Factura {{ pl.factura.nombre }}</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ pl.numero }}</span>
        <EstadoBadge :estado="pl.estado" />
        <span class="ayuda">{{ pl.factura.proveedor }}</span>
        <div class="doc-acciones">
          <button v-if="editable && pl.saldo_factura > 0" class="btn" :disabled="ocupado" @click="agregarPendientes">
            Agregar pendientes de la factura ({{ fmtNum(pl.saldo_factura) }})
          </button>
          <button v-if="pl.puede.finalizar" class="btn btn-primario" :disabled="ocupado" @click="finalizar">Finalizar packing list</button>
          <button v-if="pl.puede.reabrir" class="btn" @click="modal = { tipo: 'estado', accion: 'reabrir', motivo: '' }">Reabrir para corregir</button>
          <button class="btn" @click="descargar">Descargar Excel</button>
          <button v-if="pl.puede.cancelar" class="btn btn-peligro" @click="modal = { tipo: 'estado', accion: 'cancelar', motivo: '' }">Cancelar</button>
        </div>
      </div>
      <div class="doc-meta">
        <span>Cajas <b>{{ fmtNum(pl.totales.cajas) }}</b></span>
        <span>Contenido <b>{{ porUnidadTxt(pl.totales.por_unidad, 'cantidad') }}</b></span>
        <span>Sin caja <b>{{ porUnidadTxt(pl.totales.por_unidad, 'sin_caja') }}</b></span>
        <span>Peso neto <b>{{ fmtNum(pl.totales.peso_neto, 2) }} kg</b></span>
        <span>Peso bruto <b>{{ fmtNum(pl.totales.peso_bruto, 2) }} kg</b></span>
        <span>Volumen <b>{{ fmtNum(pl.totales.cbm, 3) }} m³</b></span>
        <span>Unidad de carga
          <b v-if="pl.transporte">{{ pl.transporte.unidad }}, {{ pl.transporte.embarque }} ({{ pl.transporte.asignacion === 'CONFIRMADA' ? 'confirmada' : 'tentativa' }})</b>
          <b v-else>Sin asignar</b>
        </span>
      </div>
      <div v-if="pl.validaciones.length" class="nota aviso mt fila-flex">
        <span>{{ pl.validaciones.length }} pendientes para poder finalizar.</span>
        <button class="btn-texto" @click="modal = { tipo: 'pendientes', detalle: pl.validaciones }">Ver cuáles</button>
      </div>
    </section>

    <div class="pestanas" role="tablist">
      <button class="pestana" role="tab" :aria-selected="tab === 'contenido'" @click="tab = 'contenido'">Contenido<span class="cuenta">{{ pl.lineas.length }}</span></button>
      <button class="pestana" role="tab" :aria-selected="tab === 'cajas'" @click="tab = 'cajas'">Cajas<span class="cuenta">{{ pl.totales.cajas }}</span></button>
      <button v-if="pl.puede.recepcion" class="pestana" role="tab" :aria-selected="tab === 'recepcion'" @click="tab = 'recepcion'">Recepción</button>
    </div>

    <!-- Contenido -->
    <section v-if="tab === 'contenido'">
      <div class="filtros">
        <input v-model="filtro.texto" type="search" placeholder="Filtrar por código, estilo, color, talla u OC" aria-label="Filtrar contenido" />
        <select v-model="filtro.empaque" aria-label="Estado de empaque">
          <option value="">Todo el contenido</option>
          <option value="SIN_CAJA">Sin caja</option>
          <option value="PARCIAL">Parcialmente en cajas</option>
          <option value="COMPLETO">Completamente en cajas</option>
        </select>
        <span class="ayuda">{{ lineasFiltradas.length }} filas</span>
      </div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Seleccionar todas las filas filtradas" :checked="selL.todos(idsFiltrados)" @change="selL.alternarTodos(idsFiltrados)" /></th>
              <th>OC / pos.</th>
              <th>Código SAP</th>
              <th>Estilo</th>
              <th>Color</th>
              <th>Talla</th>
              <th class="num">Cantidad</th>
              <th class="num">En cajas</th>
              <th class="num">Sin caja</th>
              <th>Empaque</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in lineasFiltradas" :key="l.id" :class="{ seleccionada: selL.tiene(l.id) }">
              <td class="chk"><input type="checkbox" :aria-label="`Seleccionar ${ref_(l)}`" :checked="selL.tiene(l.id)" @change="selL.alternar(l.id)" /></td>
              <td class="codigo">{{ l.oc_numero }} / {{ l.posicion }}</td>
              <td class="codigo">{{ l.codigo_sap }}
                <span v-if="partes.cuenta[l.factura_linea_id] > 1" class="etiqueta">parte {{ partes.indice[l.id] }}</span>
              </td>
              <td>{{ l.estilo }}</td>
              <td>{{ l.color }}</td>
              <td><strong>{{ l.talla }}</strong></td>
              <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
              <td class="num">{{ fmtNum(l.en_cajas) }}</td>
              <td class="num"><strong v-if="l.sin_caja">{{ fmtNum(l.sin_caja) }}</strong><span v-else class="apagado">0</span></td>
              <td>
                <EstadoBadge :estado="l.estado_empaque" />
                <span v-if="l.en_parcial" class="etiqueta aviso">incluye caja parcial</span>
              </td>
            </tr>
            <tr v-if="!lineasFiltradas.length">
              <td colspan="10" class="vacio">{{ pl.lineas.length ? 'Ninguna fila coincide con el filtro.' : 'El packing list está vacío.' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <BarraSeleccion :cantidad="selL.ids.size" singular="fila seleccionada" plural="filas seleccionadas" @limpiar="selL.limpiar()">
        <template #resumen>{{ resumenSelLineas }}</template>
        <template v-if="editable">
          <button class="btn btn-primario" :disabled="!selLineas.length" @click="abrirPlantilla">Aplicar plantilla</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirCaja">{{ selConPendiente.length > 1 ? 'Crear caja mixta' : 'Crear cajas' }}</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirSobrante">Caja con lo que falta</button>
          <button class="btn" :disabled="selLineas.length !== 1 || selLineas[0].sin_caja < 2" @click="abrirDividir">Dividir</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirMover">Mover a otro PL</button>
          <button class="btn" :disabled="!selConPendiente.length" @click="abrirQuitar">Quitar del PL</button>
        </template>
      </BarraSeleccion>
    </section>

    <!-- Cajas -->
    <section v-if="tab === 'cajas'">
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Seleccionar todas las cajas" :checked="selG.todos(idsGrupos)" @change="selG.alternarTodos(idsGrupos)" /></th>
              <th>Cajas</th>
              <th>Contenido por caja</th>
              <th class="num">N.º cajas</th>
              <th class="num">Largo cm</th>
              <th class="num">Ancho cm</th>
              <th class="num">Alto cm</th>
              <th class="num">Neto/caja kg</th>
              <th class="num">Bruto/caja kg</th>
              <th class="num">CBM</th>
              <th class="num">Bruto total kg</th>
              <th>Notas</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in pl.grupos" :key="g.id" :class="{ seleccionada: selG.tiene(g.id) }">
              <td class="chk"><input type="checkbox" :aria-label="`Seleccionar cajas ${rango(g)}`" :checked="selG.tiene(g.id)" @change="selG.alternar(g.id)" /></td>
              <td class="cajas-rango">{{ rango(g) }}</td>
              <td class="envolver">
                <div v-for="it in g.items" :key="it.pl_linea_id">
                  <span class="codigo">{{ it.codigo_sap }}</span> {{ it.estilo }} <b>{{ it.talla }}</b>
                  × {{ cantTxt(it.cantidad_por_caja, it.unidad) }}
                </div>
              </td>
              <td class="num" style="width: 84px">
                <CeldaEditable v-if="editable" tipo="number" :min="1" paso="1" :valor="g.num_cajas" :guardar="celdaGrupo(g, 'num_cajas')" etiqueta="Número de cajas" />
                <template v-else>{{ g.num_cajas }}</template>
              </td>
              <td v-for="campo in ['largo', 'ancho', 'alto', 'peso_neto_caja', 'peso_bruto_caja']" :key="campo" class="num" style="width: 92px">
                <CeldaEditable v-if="editable" tipo="number" :min="0" :valor="g[campo]" :guardar="celdaGrupo(g, campo)" vacia-texto="Falta" :etiqueta="campo.replaceAll('_', ' ')" />
                <template v-else>{{ fmtNum(g[campo], campo.startsWith('peso') ? 2 : 0) }}</template>
              </td>
              <td class="num">{{ fmtNum(g.cbm_total, 3) }}</td>
              <td class="num">{{ fmtNum(g.peso_bruto_total, 2) }}</td>
              <td>
                <span v-if="g.mixta" class="etiqueta">Mixta</span>
                <span v-if="g.es_parcial" class="etiqueta aviso">Parcial</span>
                <span v-if="g.peso_estimado" class="etiqueta error">Peso estimado</span>
                <span v-if="g.plantilla_nombre" class="ayuda"> {{ g.plantilla_nombre }}</span>
                <div v-if="g.observacion" class="ayuda">{{ g.observacion }}</div>
              </td>
            </tr>
            <tr v-if="!pl.grupos.length">
              <td colspan="12" class="vacio">Todavía no hay cajas. En “Contenido” selecciona filas y aplica una plantilla o crea cajas.</td>
            </tr>
          </tbody>
          <tfoot v-if="pl.grupos.length">
            <tr>
              <td></td>
              <td colspan="2">Total</td>
              <td class="num">{{ fmtNum(pl.totales.cajas) }}</td>
              <td colspan="5"></td>
              <td class="num">{{ fmtNum(pl.totales.cbm, 3) }}</td>
              <td class="num">{{ fmtNum(pl.totales.peso_bruto, 2) }}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
      <BarraSeleccion :cantidad="selG.ids.size" singular="grupo seleccionado" plural="grupos seleccionados" @limpiar="selG.limpiar()">
        <template #resumen>{{ cajasSel }} cajas</template>
        <template v-if="editable">
          <button class="btn" @click="abrirEditarCajas">Cambiar medidas o pesos</button>
          <button class="btn" @click="abrirPlantillaCajas">Usar valores de plantilla</button>
          <button class="btn" :disabled="!selGrupos.some((g) => g.peso_estimado)" @click="confirmarPesos">Confirmar pesos</button>
          <button class="btn" @click="abrirMoverCajas">Mover cajas a otro PL</button>
          <button class="btn" :disabled="selGrupos.length !== 1 || selGrupos[0].mixta" @click="modal = { tipo: 'guardar_plantilla', grupo_id: selGrupos[0].id, nombre: '' }">Guardar como plantilla</button>
          <button class="btn btn-peligro" @click="modal = { tipo: 'desempacar' }">Desempacar</button>
        </template>
      </BarraSeleccion>
    </section>

    <!-- Recepción -->
    <section v-if="tab === 'recepcion'" class="panel">
      <div class="panel-cabeza">
        <h2>Recepción en bodega</h2>
        <button class="btn btn-primario" :disabled="ocupado" @click="guardarRecepcion">Guardar recepción</button>
      </div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr><th>Fila</th><th class="num">Según PL</th><th class="num">Recibida</th><th class="num">Dañada</th><th class="num">Diferencia</th><th>Observación</th></tr>
          </thead>
          <tbody>
            <tr v-for="l in pl.lineas" :key="l.id">
              <td><span class="codigo">{{ l.codigo_sap }}</span> {{ l.estilo }} <b>{{ l.talla }}</b></td>
              <td class="num">{{ cantTxt(l.cantidad, l.unidad) }}</td>
              <td class="num"><input v-model.number="recepcion[l.id].cantidad_recibida" class="celda num" type="number" min="0" style="width: 90px" :aria-label="`Recibida ${ref_(l)}`" /></td>
              <td class="num"><input v-model.number="recepcion[l.id].cantidad_danada" class="celda num" type="number" min="0" style="width: 80px" :aria-label="`Dañada ${ref_(l)}`" /></td>
              <td class="num">
                <span :class="{ 'etiqueta error': recepcion[l.id].cantidad_recibida !== l.cantidad }">{{ fmtNum(recepcion[l.id].cantidad_recibida - l.cantidad) }}</span>
              </td>
              <td><input v-model="recepcion[l.id].observacion" class="celda" :aria-label="`Observación ${ref_(l)}`" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>

  <!-- Modales -->
  <Modal v-if="modal?.tipo === 'plantilla'" titulo="Aplicar plantilla de caja" ancho="720px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span>Plantilla</span>
        <select v-model="modal.plantilla_id" @change="previsualizar">
          <option value="" disabled>Elige una plantilla</option>
          <option v-for="t in plantillas" :key="t.id" :value="t.id">{{ t.nombre }} ({{ cantTxt(t.cantidad_por_caja, t.unidad) }} por caja)</option>
        </select>
      </label>
      <label class="check" style="align-self: end">
        <input v-model="modal.reemplazar" type="checkbox" @change="previsualizar" /> Reemplazar las cajas que ya tienen estas filas
      </label>
    </div>
    <p v-if="!plantillas.length" class="nota aviso">Este proveedor no tiene plantillas activas. Créalas en “Plantillas de caja” o usa “Crear cajas”.</p>
    <p class="ayuda">La plantilla solo llena los datos de la caja; cada caja guarda sus propios valores y puedes editarlos después.</p>
    <template v-if="modal.previa">
      <div class="nota">
        Se crearán <b>{{ modal.previa.resumen.cajas_completas }} cajas completas</b> en {{ modal.previa.resumen.filas }} filas.
        <template v-if="modal.previa.resumen.omitidas"> {{ modal.previa.resumen.omitidas }} filas se omiten.</template>
      </div>
      <div v-if="modal.previa.resumen.sobrante_total" class="nota aviso">
        {{ modal.previa.resumen.filas_con_sobrante }} filas dejan un sobrante que no completa una caja ({{ fmtNum(modal.previa.resumen.sobrante_total) }} en total). ¿Qué hacemos con él?
        <label class="check mt"><input v-model="modal.sobrante" type="radio" value="caja_parcial" /> Crear una caja parcial por fila, con las medidas de la plantilla y el peso estimado para confirmar</label>
        <label class="check"><input v-model="modal.sobrante" type="radio" value="sin_caja" /> Dejarlo sin caja para revisarlo fila por fila</label>
      </div>
      <div class="tabla-marco" style="max-height: 280px; overflow-y: auto">
        <table class="tabla">
          <thead><tr><th>Fila</th><th class="num">Sin caja</th><th class="num">Cajas</th><th class="num">Sobrante</th></tr></thead>
          <tbody>
            <tr v-for="fp in modal.previa.filas" :key="fp.pl_linea_id">
              <td>{{ fp.ref }}</td>
              <td class="num">{{ fmtNum(fp.sin_caja) }}</td>
              <template v-if="fp.omitida"><td colspan="2" class="apagado">{{ fp.omitida }}</td></template>
              <template v-else>
                <td class="num">{{ fp.cajas }}</td>
                <td class="num"><span :class="{ 'etiqueta aviso': fp.sobrante }">{{ fp.sobrante }}</span></td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.previa || !modal.previa.resumen.filas" @click="aplicarPlantilla">Aplicar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'caja'" :titulo="modal.items.length > 1 ? 'Crear caja mixta' : 'Crear cajas'" ancho="680px" @cerrar="modal = null">
    <div class="rejilla-campos">
      <label class="campo"><span>Número de cajas</span><input v-model.number="modal.num_cajas" type="number" min="1" /></label>
      <label class="campo"><span>Tomar datos de plantilla (opcional)</span>
        <select v-model="modal.plantilla_id">
          <option value="">Sin plantilla</option>
          <option v-for="t in plantillas" :key="t.id" :value="t.id">{{ t.nombre }}</option>
        </select>
      </label>
    </div>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Fila</th><th class="num">Sin caja</th><th class="num">Por caja</th><th class="num">Total</th></tr></thead>
        <tbody>
          <tr v-for="i in modal.items" :key="i.pl_linea_id">
            <td>{{ i.ref }}</td>
            <td class="num">{{ cantTxt(i.sin_caja, i.unidad) }}</td>
            <td class="num"><input v-model.number="i.cantidad_por_caja" class="celda num" type="number" min="1" style="width: 90px" :aria-label="`Por caja ${i.ref}`" /></td>
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

  <Modal v-if="modal?.tipo === 'sobrante'" titulo="Caja con lo que falta" @cerrar="modal = null">
    <p>Se crea una caja por fila con todo lo que tiene sin caja ({{ selConPendiente.length }} filas).</p>
    <label class="campo"><span>Datos de la caja</span>
      <select v-model="modal.plantilla_id">
        <option value="">La última plantilla usada en cada fila</option>
        <option v-for="t in plantillas" :key="t.id" :value="t.id">{{ t.nombre }}</option>
      </select>
    </label>
    <p class="ayuda">Las medidas se copian de la plantilla y el peso se estima; confírmalo en la pestaña “Cajas”.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="empacarSobrante">Crear cajas</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'dividir'" titulo="Dividir fila" @cerrar="modal = null">
    <p><b>{{ ref_(modal.linea) }}</b>: {{ cantTxt(modal.linea.cantidad, modal.linea.unidad) }}, {{ fmtNum(modal.linea.sin_caja) }} sin caja.</p>
    <p class="ayuda">Solo se divide lo que no está en cajas. Cada parte queda como una fila nueva que puedes mover o empacar aparte.</p>
    <div v-for="(p, i) in modal.partes" :key="i" class="fila-flex">
      <label class="campo" style="flex: 1"><span>Parte nueva {{ i + 1 }}</span><input v-model.number="modal.partes[i]" type="number" min="1" /></label>
      <button v-if="modal.partes.length > 1" class="btn-icono" :aria-label="`Quitar parte ${i + 1}`" @click="modal.partes.splice(i, 1)">×</button>
    </div>
    <button class="btn-texto" style="align-self: flex-start" @click="modal.partes.push(1)">Agregar otra parte</button>
    <p :class="['nota', sumaPartes > modal.linea.sin_caja || sumaPartes >= modal.linea.cantidad ? 'error' : '']">
      La fila original queda con {{ fmtNum(modal.linea.cantidad - sumaPartes) }}.
      <template v-if="sumaPartes > modal.linea.sin_caja"> Las partes superan lo que está sin caja.</template>
    </p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || sumaPartes < 1 || sumaPartes > modal.linea.sin_caja || sumaPartes >= modal.linea.cantidad" @click="dividir">Dividir</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover' || modal?.tipo === 'quitar'" :titulo="modal.tipo === 'mover' ? 'Mover a otro packing list' : 'Quitar del packing list'" ancho="640px" @cerrar="modal = null">
    <label v-if="modal.tipo === 'mover'" class="campo"><span>Destino</span>
      <select v-model="modal.destino">
        <option v-for="o in pl.otros_pl" :key="o.id" :value="o.id">{{ o.numero }}</option>
        <option value="">Un packing list nuevo</option>
      </select>
    </label>
    <p v-else class="ayuda">La cantidad vuelve a la factura como pendiente de asignar.</p>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Fila</th><th class="num">Sin caja</th><th class="num">Cantidad</th></tr></thead>
        <tbody>
          <tr v-for="fm in modal.filas" :key="fm.pl_linea_id">
            <td>{{ fm.ref }}</td>
            <td class="num">{{ cantTxt(fm.sin_caja, fm.unidad) }}</td>
            <td class="num"><input v-model.number="fm.cantidad" class="celda num" type="number" min="1" :max="fm.sin_caja" style="width: 90px" :aria-label="`Cantidad ${fm.ref}`" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="ayuda">Solo se mueve lo que está sin caja. Para llevar lo empacado usa “Mover cajas” en la pestaña Cajas.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || movInvalido" @click="modal.tipo === 'mover' ? mover() : quitar()">
        {{ modal.tipo === 'mover' ? 'Mover' : 'Quitar del PL' }}
      </button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'editar_cajas'" :titulo="`Cambiar datos de ${cajasSel} cajas`" @cerrar="modal = null">
    <p class="ayuda">Deja en blanco lo que no quieras cambiar. Los cambios de peso quitan la marca de estimado.</p>
    <div class="rejilla-campos">
      <label class="campo"><span>Número de cajas por grupo</span><input v-model="modal.valores.num_cajas" type="number" min="1" /></label>
      <label class="campo"><span>Largo cm</span><input v-model="modal.valores.largo" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Ancho cm</span><input v-model="modal.valores.ancho" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Alto cm</span><input v-model="modal.valores.alto" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso neto por caja kg</span><input v-model="modal.valores.peso_neto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Peso bruto por caja kg</span><input v-model="modal.valores.peso_bruto_caja" type="number" min="0" step="any" /></label>
      <label class="campo"><span>Observación</span><input v-model="modal.valores.observacion" /></label>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="editarCajas">Aplicar a {{ selG.ids.size }} grupos</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'cajas_plantilla'" titulo="Usar valores de una plantilla" @cerrar="modal = null">
    <label class="campo"><span>Plantilla</span>
      <select v-model="modal.plantilla_id">
        <option v-for="t in plantillas" :key="t.id" :value="t.id">{{ t.nombre }}</option>
      </select>
    </label>
    <p class="ayuda">Copia medidas y pesos a las cajas seleccionadas. En cajas parciales el peso se estima en proporción. La plantilla no se modifica.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.plantilla_id" @click="valoresDePlantilla">Copiar valores</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover_cajas'" titulo="Mover cajas a otro packing list" ancho="600px" @cerrar="modal = null">
    <label class="campo"><span>Destino</span>
      <select v-model="modal.destino">
        <option v-for="o in pl.otros_pl" :key="o.id" :value="o.id">{{ o.numero }}</option>
        <option value="">Un packing list nuevo</option>
      </select>
    </label>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Cajas</th><th class="num">Hay</th><th class="num">Mover</th></tr></thead>
        <tbody>
          <tr v-for="gm in modal.grupos" :key="gm.grupo_id">
            <td class="cajas-rango">{{ gm.rango }}</td>
            <td class="num">{{ gm.max }}</td>
            <td class="num"><input v-model.number="gm.num_cajas" class="celda num" type="number" min="1" :max="gm.max" style="width: 80px" :aria-label="`Cajas a mover de ${gm.rango}`" /></td>
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
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.nombre.trim()" @click="guardarPlantilla">Guardar plantilla</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'desempacar'" titulo="Desempacar cajas" @cerrar="modal = null">
    <p>Se eliminan {{ cajasSel }} cajas y su contenido queda sin caja en el packing list.</p>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="desempacar">Desempacar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'pendientes'" titulo="Pendientes para finalizar" ancho="620px" @cerrar="modal = null">
    <ul class="lista-mensajes"><li v-for="(d, i) in modal.detalle" :key="i">{{ textoDetalle(d) }}</li></ul>
    <template #pie><button class="btn btn-primario" @click="modal = null">Entendido</button></template>
  </Modal>

  <Modal v-if="modal?.tipo === 'estado'" :titulo="modal.accion === 'reabrir' ? 'Reabrir packing list' : 'Cancelar packing list'" @cerrar="modal = null">
    <p v-if="modal.accion === 'reabrir'">Vuelve a ser editable. Si estaba confirmado en una unidad de carga, la asignación pasa a tentativa.</p>
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
