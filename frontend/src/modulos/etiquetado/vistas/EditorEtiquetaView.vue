<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { fmtNum } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { UNIDADES, UNIDADES_DE, cargarFuentes, textoModalidad } from '@/modulos/etiquetado/etiquetas.js'
import { crearEditor } from '@/modulos/etiquetado/editor/estado.js'
import LienzoEtiqueta from '@/modulos/etiquetado/editor/LienzoEtiqueta.vue'
import BibliotecaCampos from '@/modulos/etiquetado/editor/BibliotecaCampos.vue'
import CapasEtiqueta from '@/modulos/etiquetado/editor/CapasEtiqueta.vue'
import PanelElemento from '@/modulos/etiquetado/editor/PanelElemento.vue'
import PanelEtiqueta from '@/modulos/etiquetado/editor/PanelEtiqueta.vue'
import VistaPrevia from '@/modulos/etiquetado/editor/VistaPrevia.vue'
import VersionesEtiqueta from '@/modulos/etiquetado/editor/VersionesEtiqueta.vue'

// Editor de una versión de etiqueta. Se edita un borrador (o una versión
// rechazada); una versión aprobada, pendiente o archivada se ve sin cambios y
// el aviso de arriba dice qué hacer. El lienzo dibuja al instante; la vista
// previa del servidor (la que se imprime) se actualiza al dejar de editar y
// marca los problemas en el lienzo.
const route = useRoute()
const router = useRouter()
const ed = crearEditor()
const est = ed.estado
const plantilla = ref(null)
const version = ref(null)
const grupos = ref({})
const familia = ref(null)
const cargando = ref(true)
const guardando = ref(false)
const fuentes = ref(0)
const lienzo = ref(null)
const panelIzq = ref('biblioteca')
const panelDer = ref('propiedades')

const disenador = computed(() => puede('etiquetas.disenar'))
const editable = computed(() => disenador.value && plantilla.value?.estado === 'ACTIVA' && ['BORRADOR', 'RECHAZADA'].includes(version.value?.estado))
watch(editable, (v) => (est.editable = v), { immediate: true })
watch(disenador, (v) => (est.disenador = v), { immediate: true })
const abierta = computed(() => plantilla.value?.versiones?.find((v) => ['BORRADOR', 'PENDIENTE', 'RECHAZADA'].includes(v.estado)))

// ---- Carga --------------------------------------------------------------------------------
async function cargarPlantilla() {
  plantilla.value = await api.get(`/etiquetas/plantillas/${route.params.id}`)
}
async function abrirVersion(id) {
  const v = await api.get(`/etiquetas/versiones/${id}`)
  version.value = v
  est.modalidad = plantilla.value.modalidad
  ed.cargar(v.diseno)
  est.previa = null
  pedirPrevia()
}
function versionInicial() {
  const vs = plantilla.value.versiones
  const pedida = Number(route.query.version)
  return (vs.find((v) => v.id === pedida) || abierta.value || vs.find((v) => v.vigente) || vs[0])?.id
}
async function cargar() {
  cargando.value = true
  try {
    await cargarPlantilla()
    const [campos, familias] = await Promise.all([
      api.get('/etiquetas/campos', { modalidad: plantilla.value.modalidad }),
      plantilla.value.familia_id ? api.get('/etiquetas/familias') : Promise.resolve([]),
    ])
    grupos.value = campos.grupos
    est.campos = campos.campos
    est.colecciones = campos.colecciones || []
    est.tipos = Object.fromEntries(campos.campos.map((c) => [c.clave, c.tipo]))
    est.ejemplos = { ...Object.fromEntries(campos.campos.filter((c) => c.ejemplo != null).map((c) => [c.clave, c.ejemplo])),
      'etiqueta.numero': 1, 'etiqueta.total': 1, 'etiqueta.numero_lote': 1, 'etiqueta.total_lote': 1 }
    familia.value = familias.find((f) => f.id === plantilla.value.familia_id) || null
    await abrirVersion(versionInicial())
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
async function cambiarVersion(id) {
  if (id === version.value?.id) return
  if (est.sucio && editable.value && !(await confirmar(t('There are unsaved changes. Open the other version anyway?'), { boton: t('Discard changes'), peligro: true }))) return
  router.replace({ query: { ...route.query, version: id } })
  try {
    await abrirVersion(id)
  } catch (e) {
    errorApi(e)
  }
}
async function alCambiarVersiones(nuevaId) {
  try {
    await cargarPlantilla()
    await abrirVersion(nuevaId || version.value.id)
    if (nuevaId) router.replace({ query: { ...route.query, version: nuevaId } })
  } catch (e) {
    errorApi(e)
  }
}

// ---- Vista previa del servidor ------------------------------------------------------------
const previaCargando = ref(false)
let esperaPrevia
let pedidoPrevia = 0
function pedirPrevia() {
  clearTimeout(esperaPrevia)
  esperaPrevia = setTimeout(previa, 450)
}
async function previa() {
  if (!est.diseno || !version.value) return
  const f = est.fuenteDatos
  const cuerpo = disenador.value ? { modalidad: plantilla.value.modalidad, diseno: est.diseno } : { version_id: version.value.id }
  if (f.real) {
    if (est.modalidad === 'ARTICULO' && f.articulo_id) cuerpo.articulo_id = f.articulo_id
    if (est.modalidad !== 'ARTICULO' && f.oc_id) {
      cuerpo.oc_id = f.oc_id
      if (f.posicion_id) cuerpo.posicion_id = f.posicion_id
      if (f.bulto) cuerpo.bulto = Number(f.bulto)
    }
  }
  const n = ++pedidoPrevia
  previaCargando.value = true
  try {
    const r = await api.post('/etiquetas/vista-previa', cuerpo)
    if (n === pedidoPrevia) est.previa = r
  } catch (e) {
    if (n !== pedidoPrevia) return
    if (e.status !== 422) errorApi(e)
    else if (e.detalle?.length) est.previa = { ...(est.previa || {}), problemas: e.detalle.map((d) => ({ nivel: 'error', nombre: d.campo, mensaje: d.mensaje })) }
    else est.previa = { ...(est.previa || {}), problemas: [{ nivel: 'error', mensaje: e.message }] }
  } finally {
    if (n === pedidoPrevia) previaCargando.value = false
  }
}
watch(() => est.diseno, pedirPrevia, { deep: true })
watch(() => ({ ...est.fuenteDatos }), pedirPrevia, { deep: true })
const errores = computed(() => (est.previa?.problemas || []).filter((p) => p.nivel === 'error').length)
const avisos = computed(() => (est.previa?.problemas || []).filter((p) => p.nivel !== 'error').length)

// ---- Guardar ------------------------------------------------------------------------------
async function guardar() {
  if (!editable.value || guardando.value || !est.sucio) return
  ed.fotografiar()
  guardando.value = true
  try {
    const r = await api.put(`/etiquetas/versiones/${version.value.id}/diseno`, { diseno: est.diseno, version: version.value.version })
    version.value = { ...version.value, ...r }
    ed.guardado(r.diseno)
    avisar(t('Version {0} saved.', [r.numero]))
    cargarPlantilla().catch(() => {})
  } catch (e) {
    if (e.status === 409 && e.codigo === 'conflicto_version') {
      avisar(t('Someone else saved this version in the meantime. Reload it to see their changes (yours will be lost).'), 'error')
    } else errorApi(e)
  } finally {
    guardando.value = false
  }
}
async function recargarVersion() {
  if (est.sucio && !(await confirmar(t('Discard your changes and load the saved version?'), { boton: t('Discard changes'), peligro: true }))) return
  await alCambiarVersiones()
}
async function enviar() {
  if (est.sucio) await guardar()
  if (est.sucio) return
  try {
    await api.post(`/etiquetas/versiones/${version.value.id}/enviar`, {})
    avisar(t('Version {0} sent for approval.', [version.value.numero]))
    await alCambiarVersiones()
  } catch (e) {
    errorApi(e)
  }
}
async function nuevaVersion() {
  try {
    const v = await api.post(`/etiquetas/plantillas/${plantilla.value.id}/versiones`, {})
    await alCambiarVersiones(v.id)
  } catch (e) {
    errorApi(e)
  }
}

// ---- Datos del diseño (nombre, familia, unidad de generación) ----------------------------------
const datos = ref(null)
const familias = ref([])
async function abrirDatos() {
  const p = plantilla.value
  datos.value = { nombre: p.nombre, descripcion: p.descripcion || '', familia_id: p.familia_id || '', unidad: p.unidad }
  familias.value = await api.get('/etiquetas/familias', { activas: true }).catch(() => [])
}
async function guardarDatos() {
  try {
    plantilla.value = await api.patch(`/etiquetas/plantillas/${plantilla.value.id}`, { ...datos.value, familia_id: datos.value.familia_id || null })
    const fs = familias.value.length ? familias.value : await api.get('/etiquetas/familias')
    familia.value = fs.find((f) => f.id === plantilla.value.familia_id) || null
    datos.value = null
    avisar(t('Design data saved.'))
  } catch (e) {
    errorApi(e)
  }
}

// ---- Aviso de solo lectura -------------------------------------------------------------------
const aviso = computed(() => {
  const v = version.value
  const p = plantilla.value
  if (!v || !p) return null
  if (p.estado !== 'ACTIVA') return { texto: t('This design is archived: it is kept for the history and is not used for new labels.') }
  if (!disenador.value) return { texto: t('You can see this design; only label designers can change it.') }
  if (v.estado === 'APROBADA') {
    return abierta.value
      ? { texto: t('Version {0} is approved and never changes. Version {1} is in progress.', [v.numero, abierta.value.numero]), accion: [t('Open version {0}', [abierta.value.numero]), () => cambiarVersion(abierta.value.id)] }
      : { texto: t('Version {0} is approved and never changes: changes go in a new version, which replaces it once approved.', [v.numero]), accion: [t('Create new version'), nuevaVersion] }
  }
  if (v.estado === 'PENDIENTE') return { texto: t('Version {0} is waiting for approval. Withdraw it from approval to keep editing.', [v.numero]), accion: [t('See versions'), () => (panelDer.value = 'versiones')] }
  if (v.estado === 'ARCHIVADA') return { texto: t('Version {0} is archived: it is kept for the history.', [v.numero]) }
  return null
})

// ---- Zoom y atajos ---------------------------------------------------------------------------
const zoom = (z) => (est.zoom = Math.max(0.1, Math.min(z, 8)))
const PASOS_ZOOM = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8]
const acercar = () => zoom(PASOS_ZOOM.find((z) => z > est.zoom + 0.01) || 8)
const alejar = () => zoom([...PASOS_ZOOM].reverse().find((z) => z < est.zoom - 0.01) || 0.1)
function teclas(ev) {
  const mod = ev.ctrlKey || ev.metaKey
  const k = ev.key.toLowerCase()
  if (mod && k === 's') {
    ev.preventDefault()
    guardar()
    return
  }
  const escribiendo = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable
  if (escribiendo || document.querySelector('.modal-fondo')) return
  const hecho = () => ev.preventDefault()
  if (mod && k === 'z' && !ev.shiftKey) return hecho(), ed.deshacer()
  if ((mod && k === 'y') || (mod && k === 'z' && ev.shiftKey)) return hecho(), ed.rehacer()
  if (mod && k === 'd') return hecho(), ed.duplicar()
  if (mod && k === 'c') return ed.copiar()
  if (mod && k === 'v') return hecho(), ed.pegar()
  if (mod && k === 'a') return hecho(), ed.seleccionarTodo()
  if (mod && k === 'g') return hecho(), ev.shiftKey ? ed.desagrupar() : ed.agrupar()
  if (mod && k === '0') return hecho(), lienzo.value?.ajustarZoom()
  if (k === 'delete' || k === 'backspace') return hecho(), ed.eliminar()
  if (k === 'escape') return ed.seleccionar(null)
  if (k === '+' || k === '=') return acercar()
  if (k === '-') return alejar()
  if (k === ']') return ed.ordenar(mod ? 'frente' : 'subir')
  if (k === '[') return ed.ordenar(mod ? 'fondo' : 'bajar')
  const flechas = { arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, -1], arrowdown: [0, 1] }
  if (flechas[k] && est.seleccion.length) {
    hecho()
    const paso = (est.diseno.cuadricula?.paso || 1) * (ev.shiftKey ? 10 : 1)
    ed.mover(flechas[k][0] * paso, flechas[k][1] * paso)
  }
}
const ayudaTeclas = ref(false)
const ATAJOS = computed(() => [
  ['Ctrl + S', t('Save')], ['Ctrl + Z / Ctrl + Y', t('Undo / redo')], ['Ctrl + C / Ctrl + V', t('Copy / paste')], ['Ctrl + D', t('Duplicate')],
  ['Ctrl + A', t('Select all')], ['Ctrl + G / Ctrl + Shift + G', t('Group / ungroup')], ['Del', t('Delete')],
  [t('Arrows (Shift: ×10)'), t('Move one grid step')], ['[ / ]', t('Send backward / bring forward')], ['+ / − / Ctrl + 0', t('Zoom in / out / fit')],
  [t('Space + drag'), t('Move around the canvas')], [t('Shift while dragging'), t('Straight line, keep proportions, rotate in steps of 15°')],
  [t('Alt while dragging'), t('No guides and no grid')], [t('Double click a text'), t('Edit it on the label')],
])

function antesDeSalir(e) {
  if (est.sucio && editable.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onBeforeRouteLeave(async () => !(est.sucio && editable.value)
  || confirmar(t('The label design has unsaved changes. Leave anyway?'), { boton: t('Leave without saving'), peligro: true }))
onMounted(() => {
  cargar()
  cargarFuentes().then(() => fuentes.value++)
  window.addEventListener('keydown', teclas)
  window.addEventListener('beforeunload', antesDeSalir)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', teclas)
  window.removeEventListener('beforeunload', antesDeSalir)
  clearTimeout(esperaPrevia)
})
const medida = computed(() => (est.diseno ? `${fmtNum(est.diseno.ancho, 1)} × ${fmtNum(est.diseno.alto, 1)} mm` : ''))
</script>

<template>
  <div v-if="cargando && !plantilla" class="editor-etq cargando-ed"><p class="ayuda">{{ t('Loading…') }}</p></div>
  <div v-else-if="plantilla && version && est.diseno" class="editor-etq">
    <!-- Cabecera: diseño, versión y acciones -->
    <header class="ed-cabeza">
      <router-link to="/etiquetas" class="btn btn-icono" :aria-label="t('Back to labels')" :title="t('Back to labels')"><Icono nombre="atras" /></router-link>
      <div class="ed-titulo">
        <h1>{{ tx(plantilla.nombre) }}</h1>
        <p class="ed-meta">
          <span>{{ tx(textoModalidad(plantilla.modalidad)) }}</span> ·
          <span>{{ tx(UNIDADES()[plantilla.unidad] || plantilla.unidad) }}</span> ·
          <span>{{ familia ? tx(familia.nombre) : t('No family') }}</span> ·
          <span>{{ medida }}</span>
          <button v-if="disenador && plantilla.estado === 'ACTIVA'" type="button" class="btn btn-texto btn-chico" @click="abrirDatos">{{ t('Edit data') }}</button>
        </p>
      </div>
      <div class="ed-version">
        <Seleccion :model-value="version.id" :aria-label="t('Version')" @change="cambiarVersion">
          <option v-for="v in plantilla.versiones" :key="v.id" :value="v.id">{{ t('Version {0}', [v.numero]) }}{{ v.vigente ? ` · ${t('in use')}` : '' }}</option>
        </Seleccion>
        <EstadoBadge :estado="version.estado" tipo="etiqueta" />
      </div>
      <div class="ed-acciones">
        <span v-if="editable" class="indicador-guardado" :class="{ sucio: est.sucio }">{{ guardando ? t('Saving…') : est.sucio ? t('Unsaved changes') : t('Saved') }}</span>
        <button v-if="editable && est.sucio" type="button" class="btn btn-texto btn-chico" @click="recargarVersion">{{ t('Discard') }}</button>
        <button v-if="editable" type="button" class="btn" :disabled="!est.sucio || guardando" @click="guardar"><Icono nombre="check" :tam="16" />{{ t('Save') }}</button>
        <button v-if="editable && version.estado === 'BORRADOR'" type="button" class="btn btn-primario" :disabled="errores > 0 || guardando"
                :title="errores ? t('Fix the errors first') : ''" @click="enviar"><Icono nombre="enviar" :tam="16" />{{ t('Send for approval') }}</button>
      </div>
    </header>

    <div v-if="aviso" class="nota ed-aviso"><Icono nombre="candado" :tam="16" /><span>{{ aviso.texto }}</span>
      <button v-if="aviso.accion" type="button" class="btn btn-chico" @click="aviso.accion[1]">{{ aviso.accion[0] }}</button></div>
    <div v-else-if="version.estado === 'RECHAZADA' && version.comentario" class="nota ed-aviso rechazo"><Icono nombre="alerta" :tam="16" />
      <span>{{ t('Rejected by {0}: «{1}». Fix it and send it again.', [version.revisada_por || '—', version.comentario]) }}</span></div>

    <!-- Barra de herramientas -->
    <div class="ed-barra" role="toolbar" :aria-label="t('Editor tools')">
      <button type="button" class="btn btn-icono btn-chico" :disabled="!editable || !est.historia.length" :title="t('Undo (Ctrl+Z)')" :aria-label="t('Undo')" @click="ed.deshacer()"><Icono nombre="deshacer" :tam="16" /></button>
      <button type="button" class="btn btn-icono btn-chico" :disabled="!editable || !est.futuro.length" :title="t('Redo (Ctrl+Y)')" :aria-label="t('Redo')" @click="ed.rehacer()"><Icono nombre="rehacer" :tam="16" /></button>
      <span class="sep" />
      <button type="button" class="btn btn-icono btn-chico" :title="t('Zoom out')" :aria-label="t('Zoom out')" @click="alejar"><Icono nombre="zoom-menos" :tam="16" /></button>
      <button type="button" class="btn btn-chico zoom-txt" :title="t('Actual scale (100 %)')" @click="zoom(1)">{{ Math.round(est.zoom * 100) }} %</button>
      <button type="button" class="btn btn-icono btn-chico" :title="t('Zoom in')" :aria-label="t('Zoom in')" @click="acercar"><Icono nombre="zoom-mas" :tam="16" /></button>
      <button type="button" class="btn btn-icono btn-chico" :title="t('Fit to screen (Ctrl+0)')" :aria-label="t('Fit to screen')" @click="lienzo?.ajustarZoom()"><Icono nombre="ajustar" :tam="16" /></button>
      <span class="sep" />
      <button type="button" class="btn btn-icono btn-chico" :class="{ activo: est.diseno.cuadricula.visible }" :aria-pressed="est.diseno.cuadricula.visible" :title="t('Show grid')" :aria-label="t('Show grid')"
              @click="est.diseno.cuadricula.visible = !est.diseno.cuadricula.visible"><Icono nombre="cuadricula" :tam="16" /></button>
      <button type="button" class="btn btn-chico" :class="{ activo: est.diseno.cuadricula.ajustar }" :aria-pressed="est.diseno.cuadricula.ajustar" @click="est.diseno.cuadricula.ajustar = !est.diseno.cuadricula.ajustar">{{ t('Snap') }}</button>
      <template v-if="est.seleccion.length && editable">
        <span class="sep" />
        <button v-for="[m, i, txt] in [['izq', 'alin-izq', t('Left')], ['centro', 'alin-centro', t('Center')], ['der', 'alin-der', t('Right')], ['arriba', 'alin-arriba', t('Top')], ['medio', 'alin-medio', t('Middle')], ['abajo', 'alin-abajo', t('Bottom')]]"
                :key="m" type="button" class="btn btn-icono btn-chico" :title="txt" :aria-label="txt" @click="ed.alinear(m)"><Icono :nombre="i" :tam="16" /></button>
        <span class="sep" />
        <button type="button" class="btn btn-icono btn-chico" :title="t('Duplicate (Ctrl+D)')" :aria-label="t('Duplicate')" @click="ed.duplicar()"><Icono nombre="copiar" :tam="16" /></button>
        <button type="button" class="btn btn-icono btn-chico" :title="t('Delete (Del)')" :aria-label="t('Delete')" @click="ed.eliminar()"><Icono nombre="basura" :tam="16" /></button>
      </template>
      <span class="crece" />
      <button type="button" class="btn btn-chico ed-estado-previa" :class="{ error: errores, aviso: !errores && avisos }" @click="panelDer = 'previa'">
        <Icono :nombre="errores ? 'alerta' : avisos ? 'info' : 'check'" :tam="15" />
        {{ errores ? (errores === 1 ? t('1 error') : t('{0} errors', [errores])) : avisos ? (avisos === 1 ? t('1 warning') : t('{0} warnings', [avisos])) : t('Ready to print') }}
      </button>
      <button type="button" class="btn btn-icono btn-chico" :title="t('Keyboard shortcuts')" :aria-label="t('Keyboard shortcuts')" @click="ayudaTeclas = true">?</button>
    </div>

    <div class="ed-cuerpo">
      <aside class="ed-lado ed-izq">
        <nav class="pestanas-pildora ed-pestanas" role="tablist">
          <button type="button" role="tab" class="pildora" :aria-selected="panelIzq === 'biblioteca'" @click="panelIzq = 'biblioteca'">{{ t('Add') }}</button>
          <button type="button" role="tab" class="pildora" :aria-selected="panelIzq === 'capas'" @click="panelIzq = 'capas'">{{ t('Layers') }} ({{ ed.elementos.value.length }})</button>
        </nav>
        <div class="ed-scroll">
          <BibliotecaCampos v-if="panelIzq === 'biblioteca'" :grupos="grupos" :familia="familia" />
          <CapasEtiqueta v-else />
        </div>
      </aside>
      <main class="ed-centro">
        <LienzoEtiqueta ref="lienzo" :fuentes="fuentes" @zoom="zoom" />
      </main>
      <aside class="ed-lado ed-der">
        <nav class="pestanas-pildora ed-pestanas" role="tablist">
          <button type="button" role="tab" class="pildora" :aria-selected="panelDer === 'propiedades'" @click="panelDer = 'propiedades'">{{ est.seleccion.length ? t('Element') : t('Label') }}</button>
          <button type="button" role="tab" class="pildora" :aria-selected="panelDer === 'previa'" @click="panelDer = 'previa'">{{ t('Preview') }}</button>
          <button type="button" role="tab" class="pildora" :aria-selected="panelDer === 'versiones'" @click="panelDer = 'versiones'">{{ t('Versions') }} ({{ plantilla.versiones.length }})</button>
        </nav>
        <div class="ed-scroll">
          <template v-if="panelDer === 'propiedades'">
            <PanelElemento v-if="est.seleccion.length" :grupos="grupos" />
            <PanelEtiqueta v-else />
          </template>
          <VistaPrevia v-else-if="panelDer === 'previa'" :cargando="previaCargando" />
          <VersionesEtiqueta v-else :plantilla="plantilla" :actual="version.id" :sucio="est.sucio && editable" @abrir="cambiarVersion" @cambio="alCambiarVersiones" />
        </div>
      </aside>
    </div>

    <Modal v-if="datos" :titulo="t('Design data')" @cerrar="datos = null">
      <label class="campo"><span>{{ t('Name') }}</span><input v-model="datos.nombre" maxlength="120" /></label>
      <label class="campo"><span>{{ t('Description') }}</span><textarea v-model="datos.descripcion" rows="2" maxlength="500" /></label>
      <label class="campo"><span>{{ t('Labeling family') }}</span>
        <Seleccion v-model="datos.familia_id" :aria-label="t('Labeling family')">
          <option value="">{{ t('No family (any item)') }}</option>
          <option v-for="f in familias" :key="f.id" :value="f.id">{{ tx(f.nombre) }}</option>
        </Seleccion>
      </label>
      <label class="campo"><span>{{ t('One label for each…') }}</span>
        <Seleccion v-model="datos.unidad" :aria-label="t('One label for each…')">
          <option v-for="u in UNIDADES_DE[plantilla.modalidad]" :key="u" :value="u">{{ UNIDADES()[u] }}</option>
        </Seleccion>
      </label>
      <p class="ayuda">{{ t('The data mode ({0}) does not change: duplicate the design to use other data.', [tx(textoModalidad(plantilla.modalidad))]) }}</p>
      <template #pie>
        <button type="button" class="btn" @click="datos = null">{{ t('Cancel') }}</button>
        <button type="button" class="btn btn-primario" :disabled="!datos.nombre.trim()" @click="guardarDatos">{{ t('Save') }}</button>
      </template>
    </Modal>

    <Modal v-if="ayudaTeclas" :titulo="t('Keyboard shortcuts')" @cerrar="ayudaTeclas = false">
      <table class="tabla"><tbody><tr v-for="[k, d] in ATAJOS" :key="k"><td class="nowrap"><kbd>{{ k }}</kbd></td><td>{{ d }}</td></tr></tbody></table>
    </Modal>
  </div>
</template>

<style scoped>
.editor-etq { display: flex; flex-direction: column; height: calc(100vh - 108px); min-height: 560px; gap: 10px; }
.cargando-ed { align-items: center; justify-content: center; }
.ed-cabeza { display: flex; align-items: center; gap: 12px; }
@media (max-width: 1100px) {
  .ed-cabeza { flex-wrap: wrap; }
  .ed-cabeza .ed-titulo { flex: 1 1 calc(100% - 60px); }
  .ed-cabeza .ed-meta { flex-wrap: wrap; white-space: normal; }
  .ed-cabeza .ed-titulo h1 { white-space: normal; }
}
.ed-titulo { flex: 1; min-width: 0; }
.ed-titulo h1 { margin: 0; font-size: 1.3rem; line-height: 1.25; }
.ed-meta { margin: 2px 0 0; font-size: 0.8rem; color: var(--tinta-3); display: flex; gap: 4px; align-items: center; white-space: nowrap; overflow: hidden; }
.ed-meta > span { overflow: hidden; text-overflow: ellipsis; }
.ed-titulo h1 { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ed-version { display: flex; align-items: center; gap: 8px; }
.ed-version :deep(.sb) { min-width: 170px; }
.ed-acciones { display: flex; align-items: center; gap: 8px; }
.indicador-guardado { font-size: 0.78rem; color: var(--ok); }
.indicador-guardado.sucio { color: var(--aviso); }
.ed-aviso { display: flex; align-items: center; gap: 10px; margin: 0; }
.ed-aviso span { flex: 1; }
.ed-aviso.rechazo { background: var(--error-fondo); color: var(--error); border-color: transparent; }
.ed-barra { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; padding: 5px 8px; background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; }
.ed-barra .sep { width: 1px; height: 22px; background: var(--linea); margin: 0 4px; }
.ed-barra .activo { background: var(--acento-claro); border-color: var(--acento-medio); color: var(--acento-texto); }
.zoom-txt { min-width: 58px; font-variant-numeric: tabular-nums; }
.ed-estado-previa { color: var(--ok); }
.ed-estado-previa.aviso { color: var(--aviso); }
.ed-estado-previa.error { color: var(--error); }
.ed-cuerpo { flex: 1; min-height: 0; display: grid; grid-template-columns: 250px minmax(0, 1fr) 330px; gap: 10px; }
.ed-lado { display: flex; flex-direction: column; min-height: 0; background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; overflow: hidden; }
.ed-pestanas { padding: 8px 8px 0; flex-wrap: wrap; }
.ed-scroll { flex: 1; overflow: auto; padding: 10px 12px 16px; }
.ed-centro { min-height: 0; border: 1px solid var(--linea); border-radius: 10px; overflow: hidden; }
kbd { font-family: ui-monospace, monospace; font-size: 0.78rem; background: var(--superficie-2); border: 1px solid var(--linea); border-bottom-width: 2px; border-radius: 4px; padding: 1px 5px; }
@media (max-width: 1100px) {
  .ed-cuerpo { grid-template-columns: 220px minmax(0, 1fr) 290px; }
}
@media (max-width: 900px) {
  .editor-etq { height: auto; }
  .ed-cuerpo { grid-template-columns: 1fr; }
  .ed-centro { height: 60vh; order: -1; }
  .ed-lado { max-height: 70vh; }
}
</style>
