<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import { fmtFechaHora, fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { PROPIEDADES, textoCambios } from '@/modulos/etiquetado/etiquetas.js'
import { usarEditor } from './estado.js'

// Versiones del diseño: cuál se usa al generar (vigente), cuál está en curso,
// quién la creó, envió y aprobó, con el comentario del revisor. Cada acción
// sigue las reglas del servidor; aquí solo se ofrecen las que aplican.
// Dos versiones se comparan lado a lado con lo que cambió entre ellas.
const props = defineProps({ plantilla: { type: Object, required: true }, actual: { type: Number, default: null }, sucio: Boolean })
const emit = defineEmits(['abrir', 'cambio'])
const versiones = computed(() => props.plantilla.versiones || [])
const abierta = computed(() => versiones.value.find((v) => ['BORRADOR', 'PENDIENTE', 'RECHAZADA'].includes(v.estado)))
const activa = computed(() => props.plantilla.estado === 'ACTIVA')

function acciones(v) {
  const r = []
  if (!activa.value) return r
  if (v.estado === 'PENDIENTE' && puede('etiquetas.aprobar')) r.push(['aprobar', t('Approve'), 'btn-primario'], ['rechazar', t('Reject'), 'btn-peligro'])
  if (v.estado === 'PENDIENTE' && puede('etiquetas.disenar')) r.push(['retirar', t('Withdraw'), ''])
  if (v.estado === 'BORRADOR' && puede('etiquetas.disenar')) r.push(['enviar', t('Send for approval'), 'btn-primario'])
  if (['APROBADA', 'ARCHIVADA'].includes(v.estado) && v.aprobada_en && !v.vigente && puede('etiquetas.aprobar')) r.push(['usar', t('Use this version'), ''])
  if (['APROBADA', 'ARCHIVADA'].includes(v.estado) && !abierta.value && puede('etiquetas.disenar')) r.push(['nueva', t('New version from this one'), ''])
  if (v.estado !== 'ARCHIVADA' && !v.vigente && (puede('etiquetas.aprobar') || (v.estado !== 'APROBADA' && puede('etiquetas.disenar')))) r.push(['archivar', t('Archive'), 'btn-texto'])
  return r
}

// Acciones con comentario: rechazar (obligatorio), aprobar, usar y archivar (opcional)
const pedir = ref(null)
const TEXTOS = computed(() => ({
  aprobar: [t('Approve version {0}', [pedir.value?.v.numero]), t('From now on, new labels use this version. Previous labels are not changed.'), t('Comment (optional)')],
  rechazar: [t('Reject version {0}', [pedir.value?.v.numero]), t('The designer sees your comment and can fix the version.'), t('What has to change?')],
  usar: [t('Use version {0} again', [pedir.value?.v.numero]), t('New labels will use this version; the other versions are kept.'), t('Reason (optional)')],
  archivar: [t('Archive version {0}', [pedir.value?.v.numero]), t('It is kept in the history and labels already generated with it can still be downloaded.'), t('Reason (optional)')],
}))
async function ejecutar(accion, v) {
  if (accion === 'nueva') return nuevaDesde(v)
  if (['aprobar', 'rechazar', 'usar', 'archivar'].includes(accion)) {
    pedir.value = { accion, v, comentario: '' }
    return
  }
  if (accion === 'enviar' && props.sucio) {
    avisar(t('Save the changes before sending the version for approval.'), 'error')
    return
  }
  await llamar(accion, v, {})
}
async function llamar(accion, v, cuerpo) {
  try {
    await api.post(`/etiquetas/versiones/${v.id}/${accion}`, cuerpo)
    avisar({ enviar: t('Version {0} sent for approval.', [v.numero]), retirar: t('Version {0} is a draft again.', [v.numero]),
      aprobar: t('Version {0} approved: it is the one in use.', [v.numero]), rechazar: t('Version {0} rejected.', [v.numero]),
      usar: t('Version {0} is in use again.', [v.numero]), archivar: t('Version {0} archived.', [v.numero]) }[accion])
    pedir.value = null
    emit('cambio')
  } catch (e) {
    errorApi(e)
  }
}
const confirmarPedido = () => llamar(pedir.value.accion, pedir.value.v, { comentario: pedir.value.comentario || null })
async function nuevaDesde(v) {
  try {
    const n = await api.post(`/etiquetas/plantillas/${props.plantilla.id}/versiones`, { desde_id: v.id })
    avisar(t('Version {0} created from version {1}.', [n.numero, v.numero]))
    emit('cambio', n.id)
  } catch (e) {
    errorApi(e)
  }
}

// ---- Comparar dos versiones ----------------------------------------------------------------
const comparar = ref([])
function alternarComparar(id) {
  comparar.value = comparar.value.includes(id) ? comparar.value.filter((x) => x !== id) : [...comparar.value.slice(-1), id]
}
const comparacion = ref(null)
async function abrirComparacion() {
  try {
    const [a, b] = await Promise.all(comparar.value.map((id) => api.get(`/etiquetas/versiones/${id}`)))
    const [vieja, nueva] = a.numero < b.numero ? [a, b] : [b, a]
    comparacion.value = { vieja, nueva, cambios: diferencias(vieja.diseno, nueva.diseno) }
  } catch (e) {
    errorApi(e)
  }
}
const ed = usarEditor()
const etiquetaCampo = (c) => tx(ed?.estado.campos.find((x) => x.clave === c)?.etiqueta || c)
const nombreEl = (e) => e.nombre || (e.campo ? etiquetaCampo(e.campo) : e.tipo === 'texto' ? (e.contenido || '').slice(0, 24) : (e.simbologia || e.tipo).toUpperCase())
function diferencias(a, b) {
  const r = []
  if (a.ancho !== b.ancho || a.alto !== b.alto) r.push([t('Dimensions'), `${fmtNum(a.ancho, 1)} × ${fmtNum(a.alto, 1)} → ${fmtNum(b.ancho, 1)} × ${fmtNum(b.alto, 1)} mm`])
  for (const k of ['margen', 'fondo', 'dpi']) if (a[k] !== b[k]) r.push([{ margen: t('Safe margin'), fondo: t('Background'), dpi: t('PNG resolution') }[k], `${a[k]} → ${b[k]}`])
  if (JSON.stringify(a.borde) !== JSON.stringify(b.borde)) r.push([t('Border'), t('changed')])
  if (JSON.stringify(a.hoja) !== JSON.stringify(b.hoja)) r.push([t('How it prints'), t('changed')])
  const ia = Object.fromEntries(a.elementos.map((e) => [e.id, e]))
  const ib = Object.fromEntries(b.elementos.map((e) => [e.id, e]))
  for (const e of b.elementos) if (!ia[e.id]) r.push([t('Added'), nombreEl(e)])
  for (const e of a.elementos) if (!ib[e.id]) r.push([t('Removed'), nombreEl(e)])
  for (const e of b.elementos) {
    const o = ia[e.id]
    if (!o) continue
    const props_ = [...new Set([...Object.keys(o), ...Object.keys(e)])].filter((k) => JSON.stringify(o[k]) !== JSON.stringify(e[k]))
    if (props_.length) r.push([t('Changed'), `${nombreEl(e)}: ${props_.map((k) => PROPIEDADES()[k] || k).join(', ')}`])
  }
  const orden = (x, y) => x.elementos.map((e) => e.id).filter((id) => y.elementos.some((f) => f.id === id)).join()
  if (orden(a, b) !== orden(b, a)) r.push([t('Layers'), t('order changed')])
  return r
}

// ---- Bitácora ------------------------------------------------------------------------------
const bitacora = ref(null)
const verBitacora = ref(false)
watch(verBitacora, async (v) => {
  if (!v) return
  try {
    bitacora.value = await api.get(`/etiquetas/plantillas/${props.plantilla.id}/bitacora`)
  } catch (e) {
    errorApi(e)
  }
})
watch(() => props.plantilla, () => {
  if (verBitacora.value) api.get(`/etiquetas/plantillas/${props.plantilla.id}/bitacora`).then((r) => (bitacora.value = r)).catch(() => {})
})
const ACCIONES = computed(() => ({
  crear: t('Created the design'), editar: t('Edited the design data'), duplicar: t('Created as a copy'), archivar: t('Archived the design'),
  reactivar: t('Reactivated the design'), nueva_version: t('New version'), guardar_diseno: t('Saved changes'), enviar_aprobacion: t('Sent for approval'),
  retirar_aprobacion: t('Withdrew from approval'), aprobar: t('Approved'), rechazar: t('Rejected'), archivar_version: t('Archived a version'),
  usar_version: t('Put a version back in use'),
}))
const miniatura = (v) => `/api/etiquetas/versiones/${v.id}/miniatura.svg?e=${encodeURIComponent(v.actualizada_en || v.creada_en || '')}`
</script>

<template>
  <div class="versiones">
    <div class="ver-barra">
      <button type="button" class="btn btn-chico" :disabled="comparar.length !== 2" @click="abrirComparacion">{{ t('Compare the 2 checked') }}</button>
      <button type="button" class="btn btn-chico btn-texto" :aria-expanded="verBitacora" @click="verBitacora = !verBitacora"><Icono nombre="historial" :tam="15" />{{ t('Activity log') }}</button>
    </div>

    <ol v-if="!verBitacora" class="ver-lista">
      <li v-for="v in versiones" :key="v.id" class="ver" :class="{ actual: v.id === props.actual }">
        <div class="ver-cabeza">
          <input type="checkbox" :checked="comparar.includes(v.id)" :aria-label="t('Compare version {0}', [v.numero])" @change="alternarComparar(v.id)" />
          <button type="button" class="ver-numero" @click="emit('abrir', v.id)">{{ t('Version {0}', [v.numero]) }}</button>
          <EstadoBadge :estado="v.estado" tipo="etiqueta" />
          <span v-if="v.vigente" class="etiqueta ok ms-0">{{ t('In use') }}</span>
        </div>
        <p class="ver-dato">{{ t('Created by {0} · {1}', [v.creada_por || '—', fmtFechaHora(v.creada_en)]) }}</p>
        <p v-if="v.enviada_en" class="ver-dato">{{ t('Sent by {0} · {1}', [v.enviada_por || '—', fmtFechaHora(v.enviada_en)]) }}</p>
        <p v-if="v.aprobada_en" class="ver-dato">{{ t('Approved by {0} · {1}', [v.aprobada_por || '—', fmtFechaHora(v.aprobada_en)]) }}</p>
        <p v-else-if="v.revisada_en" class="ver-dato">{{ t('Reviewed by {0} · {1}', [v.revisada_por || '—', fmtFechaHora(v.revisada_en)]) }}</p>
        <p v-if="v.cambios && v.numero > 1" class="ver-cambios">{{ textoCambios(v.cambios) }}</p>
        <p v-if="v.comentario" class="ver-comentario" :class="{ rechazo: v.estado === 'RECHAZADA' }">«{{ v.comentario }}»</p>
        <div v-if="acciones(v).length || v.id !== props.actual" class="ver-acciones">
          <button v-if="v.id !== props.actual" type="button" class="btn btn-chico" @click="emit('abrir', v.id)">{{ t('Open') }}</button>
          <button v-for="[a, txt, cls] in acciones(v)" :key="a" type="button" class="btn btn-chico" :class="cls" @click="ejecutar(a, v)">{{ txt }}</button>
        </div>
      </li>
    </ol>

    <ol v-else class="bitacora">
      <li v-for="b in bitacora || []" :key="b.id">
        <span class="bit-fecha">{{ fmtFechaHora(b.fecha) }}</span>
        <span><strong>{{ b.usuario || t('System') }}</strong> · {{ ACCIONES[b.accion] || b.accion }}<template v-if="b.detalle?.version"> ({{ t('version {0}', [b.detalle.version]) }})</template></span>
        <span v-if="b.detalle?.cambios" class="bit-detalle">{{ textoCambios(b.detalle.cambios) }}</span>
        <span v-if="b.motivo" class="bit-detalle">«{{ b.motivo }}»</span>
      </li>
      <li v-if="bitacora && !bitacora.length" class="ayuda">{{ t('No activity yet.') }}</li>
    </ol>

    <Modal v-if="pedir" :titulo="TEXTOS[pedir.accion][0]" @cerrar="pedir = null">
      <p class="mt-0">{{ TEXTOS[pedir.accion][1] }}</p>
      <label class="campo"><span>{{ TEXTOS[pedir.accion][2] }}</span>
        <textarea v-model="pedir.comentario" rows="3" maxlength="1000" /></label>
      <template #pie>
        <button type="button" class="btn" @click="pedir = null">{{ t('Cancel') }}</button>
        <button type="button" class="btn" :class="pedir.accion === 'rechazar' ? 'btn-peligro' : 'btn-primario'"
                :disabled="pedir.accion === 'rechazar' && !pedir.comentario.trim()" @click="confirmarPedido">{{ TEXTOS[pedir.accion][0] }}</button>
      </template>
    </Modal>

    <Modal v-if="comparacion" :titulo="t('Version {0} and version {1}', [comparacion.vieja.numero, comparacion.nueva.numero])" ancho="920px" @cerrar="comparacion = null">
      <div class="comparar">
        <figure v-for="v in [comparacion.vieja, comparacion.nueva]" :key="v.id">
          <figcaption>{{ t('Version {0}', [v.numero]) }} <EstadoBadge :estado="v.estado" tipo="etiqueta" /></figcaption>
          <img :src="miniatura(v)" :alt="t('Version {0}', [v.numero])" />
          <span class="ayuda">{{ fmtNum(v.ancho_mm, 1) }} × {{ fmtNum(v.alto_mm, 1) }} mm</span>
        </figure>
      </div>
      <h4 class="mt">{{ t('What changed') }}</h4>
      <table v-if="comparacion.cambios.length" class="tabla">
        <tbody><tr v-for="(c, i) in comparacion.cambios" :key="i"><td class="nowrap">{{ tx(c[0]) }}</td><td>{{ c[1] }}</td></tr></tbody>
      </table>
      <p v-else class="ayuda">{{ t('The two versions have the same design.') }}</p>
    </Modal>
  </div>
</template>

<style scoped>
.ver-barra { display: flex; justify-content: space-between; gap: 6px; margin-bottom: 8px; }
.ver-lista, .bitacora { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.ver { border: 1px solid var(--linea); border-radius: 10px; padding: 9px 10px; background: var(--superficie); }
.ver.actual { border-color: var(--acento-medio); box-shadow: 0 0 0 2px var(--acento-claro); }
.ver-cabeza { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ver-numero { border: 0; background: none; padding: 0; font-weight: 600; color: var(--tinta); cursor: pointer; }
.ver-numero:hover { color: var(--acento-texto); text-decoration: underline; }
.ver-dato { margin: 3px 0 0; font-size: 0.75rem; color: var(--tinta-3); }
.ver-cambios { margin: 5px 0 0; font-size: 0.75rem; color: var(--tinta-2); background: var(--superficie-2); border-radius: 6px; padding: 4px 6px; }
.ver-comentario { margin: 5px 0 0; font-size: 0.78rem; color: var(--tinta-2); font-style: italic; }
.ver-comentario.rechazo { color: var(--error); }
.ver-acciones { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.bitacora li { display: flex; flex-direction: column; gap: 1px; font-size: 0.78rem; border-left: 2px solid var(--linea); padding-left: 8px; }
.bit-fecha { color: var(--tinta-3); font-size: 0.72rem; }
.bit-detalle { color: var(--tinta-2); font-size: 0.74rem; }
.comparar { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.comparar figure { margin: 0; display: flex; flex-direction: column; gap: 6px; align-items: center; padding: 12px; border: 1px solid var(--linea); border-radius: 10px;
  background: repeating-conic-gradient(#eef1f5 0 25%, #fff 0 50%) 0 0 / 14px 14px; }
.comparar figcaption { display: flex; gap: 6px; align-items: center; font-weight: 600; }
.comparar img { max-width: 100%; max-height: 300px; box-shadow: 0 1px 3px rgba(16, 24, 40, 0.25); background: #fff; }
@media (max-width: 700px) { .comparar { grid-template-columns: 1fr; } }
</style>
