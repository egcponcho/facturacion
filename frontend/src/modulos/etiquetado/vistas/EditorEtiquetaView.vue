<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import MenuAcciones from '@/componentes/MenuAcciones.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { fmtNum } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { CANTIDADES, SUJETOS, alCargarFuente, cargarFuentes, ponerRegional } from '@/modulos/etiquetado/etiquetas.js'
import { crearEditor } from '@/modulos/etiquetado/editor/estado.js'
import LienzoEtiqueta from '@/modulos/etiquetado/editor/LienzoEtiqueta.vue'
import BarraEditor from '@/modulos/etiquetado/editor/BarraEditor.vue'
import MenuContexto from '@/modulos/etiquetado/editor/MenuContexto.vue'
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
const cargando = ref(true)
const guardando = ref(false)
const fuentes = ref(0)
let quitarAviso = null
const lienzo = ref(null)
// Paneles: a la izquierda uno a la vez (campos, capas, vista previa o versiones; plegable) y a la derecha
// las propiedades (plegable). Se recuerdan por navegador.
const leerPaneles = () => { try { return JSON.parse(localStorage.getItem('editor-etiqueta-paneles') || '{}') } catch { return {} } }
const panelesGuardados = leerPaneles()
const panelIzq = ref(panelesGuardados.izq === undefined ? 'campos' : panelesGuardados.izq)
const panelDer = ref(panelesGuardados.der !== false)
watch([panelIzq, panelDer], ([izq, der]) => { try { localStorage.setItem('editor-etiqueta-paneles', JSON.stringify({ izq, der })) } catch { /* sin almacenamiento */ } })
const abrirPanel = (p) => (panelIzq.value = panelIzq.value === p ? null : p)
const menuContexto = ref(null)

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
  est.sujeto = plantilla.value.sujeto
  est.tipo_etiqueta_id = plantilla.value.tipo_etiqueta_id
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
    const campos = await api.get('/etiquetas/campos', { sujeto: plantilla.value.sujeto })
    grupos.value = campos.grupos
    est.campos = campos.campos
    est.colecciones = campos.colecciones || []
    est.tipos = Object.fromEntries(campos.campos.map((c) => [c.clave, c.tipo]))
    est.ejemplos = { ...Object.fromEntries(campos.campos.filter((c) => c.ejemplo != null).map((c) => [c.clave, c.ejemplo])),
      'etiqueta.numero': 1, 'etiqueta.total': 1, 'etiqueta.numero_lote': 1, 'etiqueta.total_lote': 1 }
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
  const cuerpo = disenador.value ? { tipo_etiqueta_id: plantilla.value.tipo_etiqueta_id, diseno: est.diseno } : { version_id: version.value.id }
  if (f.real) {
    // Un artículo (con o sin su línea de OC), un bulto de una OC o el documento de una OC
    if (est.sujeto === 'ARTICULO' && f.articulo_id) cuerpo.articulo_id = f.articulo_id
    if (f.oc_id) {
      cuerpo.oc_id = f.oc_id
      if (est.sujeto === 'ARTICULO' && f.posicion_id) cuerpo.posicion_id = f.posicion_id
      if (est.sujeto === 'BULTO' && f.bulto) cuerpo.bulto = Number(f.bulto)
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
// Idioma y separadores del diseño: el lienzo formatea igual que el servidor
watch(() => [est.diseno?.idioma, est.diseno?.separador_miles, est.diseno?.separador_decimal], () => ponerRegional(est.diseno), { immediate: true })
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

// ---- Datos del diseño (nombre, descripción y tipo de etiqueta) ----------------------------------
const datos = ref(null)
const tipos = ref([])
async function abrirDatos() {
  const p = plantilla.value
  datos.value = { nombre: p.nombre, descripcion: p.descripcion || '', tipo_etiqueta_id: p.tipo_etiqueta_id }
  tipos.value = (await api.get('/etiquetas/tipos').catch(() => [])).filter((x) => x.sujeto === p.sujeto)
}
async function guardarDatos() {
  try {
    plantilla.value = await api.patch(`/etiquetas/plantillas/${plantilla.value.id}`, { ...datos.value, tipo_etiqueta_id: Number(datos.value.tipo_etiqueta_id) })
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
  if (v.estado === 'PENDIENTE') return { texto: t('Version {0} is waiting for approval. Withdraw it from approval to keep editing.', [v.numero]), accion: [t('See versions'), () => (panelIzq.value = 'versiones')] }
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
  if (k === 'escape' && menuContexto.value) return (menuContexto.value = null)
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
  [t('Right click'), t('Actions on what is selected')],
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
  quitarAviso = alCargarFuente(() => fuentes.value++)
  window.addEventListener('keydown', teclas)
  window.addEventListener('beforeunload', antesDeSalir)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', teclas)
  window.removeEventListener('beforeunload', antesDeSalir)
  clearTimeout(esperaPrevia)
  quitarAviso?.()
})
const medida = computed(() => (est.diseno ? `${fmtNum(est.diseno.ancho, 1)} × ${fmtNum(est.diseno.alto, 1)} mm` : ''))
</script>

<template>
  <div v-if="cargando && !plantilla" class="editor-etq cargando-ed"><p class="ayuda">{{ t('Loading…') }}</p></div>
  <div v-else-if="plantilla && version && est.diseno" class="editor-etq">
    <!-- Cabecera: el diseño, su versión, el estado para imprimir y guardar -->
    <header class="ed-cabeza">
      <router-link to="/etiquetas/disenos" class="btn btn-icono" :aria-label="t('Back to designs')" :title="t('Back to designs')"><Icono nombre="atras" /></router-link>
      <div class="ed-titulo">
        <h1 :title="tx(plantilla.nombre)">{{ tx(plantilla.nombre) }}</h1>
        <p class="ed-meta"><span>{{ tx(plantilla.tipo) }}</span><span>{{ SUJETOS()[plantilla.sujeto] }}</span><span>{{ medida }}</span></p>
      </div>
      <div class="ed-version">
        <Seleccion :model-value="version.id" :aria-label="t('Version')" @change="cambiarVersion">
          <option v-for="v in plantilla.versiones" :key="v.id" :value="v.id">{{ t('Version {0}', [v.numero]) }}{{ v.vigente ? ` · ${t('in use')}` : '' }}</option>
        </Seleccion>
        <EstadoBadge :estado="version.estado" tipo="etiqueta" />
      </div>
      <button type="button" class="btn btn-chico ed-estado-previa" :class="{ error: errores, aviso: !errores && avisos }" :title="t('See the preview and its problems')"
              @click="panelIzq = 'previa'">
        <Icono :nombre="errores ? 'alerta' : avisos ? 'info' : 'check'" :tam="15" />
        <span>{{ errores ? (errores === 1 ? t('1 error') : t('{0} errors', [errores])) : avisos ? (avisos === 1 ? t('1 warning') : t('{0} warnings', [avisos])) : t('Ready to print') }}</span>
      </button>
      <div class="ed-acciones">
        <span v-if="editable" class="indicador-guardado" :class="{ sucio: est.sucio }">{{ guardando ? t('Saving…') : est.sucio ? t('Unsaved changes') : t('Saved') }}</span>
        <button v-if="editable && est.sucio" type="button" class="btn btn-texto btn-chico" @click="recargarVersion">{{ t('Discard') }}</button>
        <button v-if="editable" type="button" class="btn" :disabled="!est.sucio || guardando" @click="guardar"><Icono nombre="check" :tam="16" />{{ t('Save') }}</button>
        <button v-if="editable && version.estado === 'BORRADOR'" type="button" class="btn btn-primario" :disabled="errores > 0 || guardando"
                :title="errores ? t('Fix the errors first') : ''" @click="enviar"><Icono nombre="enviar" :tam="16" /><span class="ed-txt-largo">{{ t('Send for approval') }}</span></button>
        <MenuAcciones :etiqueta="t('More options of the design')">
          <button v-if="disenador && plantilla.estado === 'ACTIVA'" type="button" role="menuitem" @click="abrirDatos">{{ t('Design data (name, type)') }}</button>
          <button type="button" role="menuitem" @click="panelIzq = 'versiones'">{{ t('Versions and approval') }}</button>
          <button type="button" role="menuitem" @click="ayudaTeclas = true">{{ t('Keyboard shortcuts') }}</button>
        </MenuAcciones>
      </div>
    </header>

    <div v-if="aviso" class="nota ed-aviso"><Icono nombre="candado" :tam="16" /><span>{{ aviso.texto }}</span>
      <button v-if="aviso.accion" type="button" class="btn btn-chico" @click="aviso.accion[1]">{{ aviso.accion[0] }}</button></div>
    <div v-else-if="version.estado === 'RECHAZADA' && version.comentario" class="nota ed-aviso rechazo"><Icono nombre="alerta" :tam="16" />
      <span>{{ t('Rejected by {0}: «{1}». Fix it and send it again.', [version.revisada_por || '—', version.comentario]) }}</span></div>

    <BarraEditor @acercar="acercar" @alejar="alejar" @zoom100="zoom(1)" @ajustar="lienzo?.ajustarZoom()" @campos="panelIzq = 'campos'" />

    <div class="ed-cuerpo" :class="{ 'sin-izq': !panelIzq, 'sin-der': !panelDer }">
      <!-- Riel: qué panel se ve a la izquierda (otro clic lo pliega) -->
      <nav class="ed-riel" :aria-label="t('Panels')">
        <button v-for="[clave, icono, texto, cuenta, marca] in [
                  ['campos', 'campo', t('Fields'), null, null],
                  ['capas', 'capas', t('Layers'), ed.elementos.value.length, null],
                  ['previa', 'ojo', t('Preview'), null, errores ? 'error' : avisos ? 'aviso' : null],
                  ['versiones', 'historial', t('Versions'), plantilla.versiones.length, null]]"
                :key="clave" type="button" class="riel-btn" :class="{ activo: panelIzq === clave }" :aria-pressed="panelIzq === clave"
                :title="panelIzq === clave ? t('Hide the panel') : texto" @click="abrirPanel(clave)">
          <span class="riel-icono"><Icono :nombre="icono" :tam="18" /><span v-if="marca" class="riel-marca" :class="marca" /></span>
          <span class="riel-texto">{{ texto }}<template v-if="cuenta"> · {{ cuenta }}</template></span>
        </button>
      </nav>
      <aside v-if="panelIzq" class="ed-lado ed-izq" :aria-label="{ campos: t('Fields'), capas: t('Layers'), previa: t('Preview'), versiones: t('Versions') }[panelIzq]">
        <header class="ed-lado-cabeza">
          <h2>{{ { campos: t('Data fields'), capas: t('Layers'), previa: t('Preview with real data'), versiones: t('Versions and approval') }[panelIzq] }}</h2>
          <button type="button" class="btn btn-icono btn-chico" :title="t('Hide the panel')" :aria-label="t('Hide the panel')" @click="panelIzq = null"><Icono nombre="panel-izq" :tam="16" /></button>
        </header>
        <div class="ed-scroll">
          <BibliotecaCampos v-if="panelIzq === 'campos'" :grupos="grupos" />
          <CapasEtiqueta v-else-if="panelIzq === 'capas'" />
          <VistaPrevia v-else-if="panelIzq === 'previa'" :cargando="previaCargando" />
          <VersionesEtiqueta v-else :plantilla="plantilla" :actual="version.id" :sucio="est.sucio && editable" @abrir="cambiarVersion" @cambio="alCambiarVersiones" />
        </div>
      </aside>
      <main class="ed-centro">
        <LienzoEtiqueta ref="lienzo" :fuentes="fuentes" @zoom="zoom" @menu="(p) => (menuContexto = p)" />
        <button v-if="!panelDer" type="button" class="btn btn-chico ed-abrir-der" @click="panelDer = true"><Icono nombre="panel-der" :tam="16" />{{ t('Properties') }}</button>
      </main>
      <aside v-if="panelDer" class="ed-lado ed-der" :aria-label="t('Properties')">
        <header class="ed-lado-cabeza">
          <h2>{{ ed.seleccionados.value.length > 1 ? t('{0} elements selected', [ed.seleccionados.value.length]) : est.seleccion.length ? t('Element') : t('Label') }}</h2>
          <button type="button" class="btn btn-icono btn-chico" :title="t('Hide the panel')" :aria-label="t('Hide the panel')" @click="panelDer = false"><Icono nombre="panel-der" :tam="16" /></button>
        </header>
        <div class="ed-scroll">
          <PanelElemento v-if="est.seleccion.length" :grupos="grupos" />
          <PanelEtiqueta v-else />
        </div>
      </aside>
    </div>

    <MenuContexto v-if="menuContexto" :x="menuContexto.x" :y="menuContexto.y" @cerrar="menuContexto = null" />

    <Modal v-if="datos" :titulo="t('Design data')" @cerrar="datos = null">
      <label class="campo"><span>{{ t('Name') }}</span><input v-model="datos.nombre" maxlength="120" /></label>
      <label class="campo"><span>{{ t('Description') }}</span><textarea v-model="datos.descripcion" rows="2" maxlength="500" /></label>
      <label class="campo"><span>{{ t('Label type') }}</span>
        <Seleccion v-model="datos.tipo_etiqueta_id" :aria-label="t('Label type')">
          <option v-for="x in tipos" :key="x.id" :value="x.id">{{ tx(x.nombre) }} · {{ CANTIDADES()[x.cantidad] }}</option>
        </Seleccion>
      </label>
      <p class="ayuda">{{ t('Only types that label the same thing ({0}); the type cannot change while the design is in use.', [SUJETOS()[plantilla.sujeto]]) }}</p>
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
.editor-etq { display: flex; flex-direction: column; height: calc(100vh - 100px); min-height: 560px; gap: 8px; }
.cargando-ed { align-items: center; justify-content: center; }
/* Cabecera en una línea; en pantallas angostas pasa a dos */
.ed-cabeza { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; row-gap: 6px; }
.ed-titulo { flex: 1 1 220px; min-width: 0; }
.ed-titulo h1 { margin: 0; font-size: 1.15rem; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ed-meta { margin: 1px 0 0; font-size: 0.78rem; color: var(--tinta-3); display: flex; gap: 6px; white-space: nowrap; overflow: hidden; }
.ed-meta span { overflow: hidden; text-overflow: ellipsis; }
.ed-meta span + span::before { content: '·'; margin-inline-end: 6px; }
.ed-version { display: flex; align-items: center; gap: 8px; flex: none; }
.ed-version :deep(.sb) { min-width: 160px; }
.ed-acciones { display: flex; align-items: center; gap: 6px; flex: none; }
.indicador-guardado { font-size: 0.76rem; color: var(--ok); white-space: nowrap; }
.indicador-guardado.sucio { color: var(--aviso); }
.ed-estado-previa { color: var(--ok); flex: none; }
.ed-estado-previa.aviso { color: var(--aviso); }
.ed-estado-previa.error { color: var(--error); }
.ed-aviso { display: flex; align-items: center; gap: 10px; margin: 0; padding: 8px 12px; }
.ed-aviso span { flex: 1; }
.ed-aviso.rechazo { background: var(--error-fondo); color: var(--error); border-color: transparent; }
/* Cuerpo: riel | panel izquierdo | lienzo | propiedades */
.ed-cuerpo { position: relative; flex: 1; min-height: 0; display: grid; grid-template-columns: 64px 272px minmax(0, 1fr) 316px; gap: 8px; }
.ed-cuerpo.sin-izq { grid-template-columns: 64px minmax(0, 1fr) 316px; }
.ed-cuerpo.sin-der { grid-template-columns: 64px 272px minmax(0, 1fr); }
.ed-cuerpo.sin-izq.sin-der { grid-template-columns: 64px minmax(0, 1fr); }
.ed-riel { display: flex; flex-direction: column; gap: 4px; padding: 6px 4px; background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; }
.riel-btn { display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 8px 2px 6px; border: 0; border-radius: 8px; background: none;
  color: var(--tinta-3); font: inherit; font-size: 0.68rem; line-height: 1.15; cursor: pointer; text-align: center; }
.riel-btn:hover { background: var(--superficie-2); color: var(--tinta); }
.riel-btn.activo { background: var(--acento-claro); color: var(--acento-texto); }
.riel-icono { position: relative; display: inline-flex; }
.riel-marca { position: absolute; top: -2px; inset-inline-end: -4px; width: 8px; height: 8px; border-radius: 50%; border: 2px solid var(--superficie); }
.riel-marca.error { background: var(--error); }
.riel-marca.aviso { background: var(--aviso); }
.riel-texto { overflow-wrap: anywhere; }
.ed-lado { display: flex; flex-direction: column; min-height: 0; min-width: 0; background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; overflow: hidden; }
.ed-lado-cabeza { display: flex; align-items: center; gap: 8px; padding: 8px 8px 8px 14px; border-bottom: 1px solid var(--linea); }
.ed-lado-cabeza h2 { flex: 1; min-width: 0; margin: 0; font-size: 0.9rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ed-scroll { flex: 1; overflow: auto; padding: 10px 12px 16px; min-width: 0; }
/* Dentro de los paneles nada se sale por el borde: las columnas y los selectores se encogen */
.ed-scroll :deep(.rejilla-2) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.ed-scroll :deep(.sb) { min-width: 0; width: 100%; }
.ed-scroll :deep(input), .ed-scroll :deep(select), .ed-scroll :deep(textarea) { max-width: 100%; min-width: 0; box-sizing: border-box; }
.ed-centro { position: relative; min-height: 0; min-width: 0; border: 1px solid var(--linea); border-radius: 10px; overflow: hidden; }
.ed-abrir-der { position: absolute; top: 8px; inset-inline-end: 8px; z-index: 2; box-shadow: var(--sombra-flotante); }
kbd { font-family: ui-monospace, monospace; font-size: 0.78rem; background: var(--superficie-2); border: 1px solid var(--linea); border-bottom-width: 2px; border-radius: 4px; padding: 1px 5px; }
@media (max-width: 1400px) {
  .ed-cuerpo { grid-template-columns: 64px 248px minmax(0, 1fr) 296px; }
  .ed-cuerpo.sin-izq { grid-template-columns: 64px minmax(0, 1fr) 296px; }
  .ed-cuerpo.sin-der { grid-template-columns: 64px 248px minmax(0, 1fr); }
}
/* Pantallas medianas: el panel izquierdo flota sobre el lienzo en vez de quitarle espacio */
@media (max-width: 1180px) {
  .ed-cuerpo, .ed-cuerpo.sin-izq { grid-template-columns: 64px minmax(0, 1fr) 284px; }
  .ed-cuerpo.sin-der, .ed-cuerpo.sin-izq.sin-der { grid-template-columns: 64px minmax(0, 1fr); }
  .ed-izq { position: absolute; z-index: 5; top: 0; bottom: 0; inset-inline-start: 72px; width: 280px; box-shadow: var(--sombra-flotante); }
  .ed-txt-largo { display: none; }
}
@media (max-width: 900px) {
  .editor-etq { height: auto; }
  .ed-cuerpo, .ed-cuerpo.sin-izq, .ed-cuerpo.sin-der, .ed-cuerpo.sin-izq.sin-der { grid-template-columns: 1fr; }
  .ed-riel { flex-direction: row; overflow-x: auto; }
  .riel-btn { flex: 1; }
  .ed-izq { position: static; width: auto; box-shadow: none; max-height: 60vh; }
  .ed-centro { height: 60vh; order: -1; }
  .ed-der { max-height: 70vh; }
}
</style>
