<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { fmtFecha, fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { MODALIDADES, TAMANOS, UNIDADES, UNIDADES_DE, textoModalidad } from '@/modulos/etiquetado/etiquetas.js'

// Diseños de etiqueta: miniatura, modalidad de datos, familia, tamaño, versión
// en uso y la última versión (si hay una en curso o esperando aprobación)
const router = useRouter()
const filtros = reactive({ q: '', modalidad: '', familia_id: '', estado: 'ACTIVA', estado_version: '' })
const datos = ref({ items: [], total: 0 })
const familias = ref([])
const cargando = ref(false)

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/etiquetas/plantillas', { ...filtros, size: 200 })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
let espera
watch(() => filtros.q, () => {
  clearTimeout(espera)
  espera = setTimeout(cargar, 300)
})
watch(() => [filtros.modalidad, filtros.familia_id, filtros.estado, filtros.estado_version], cargar)
onMounted(() => {
  cargar()
  api.get('/etiquetas/familias').then((r) => (familias.value = r)).catch(() => {})
})

const MODOS = computed(() => [['', t('All')], ...MODALIDADES().map(([v, txt]) => [v, txt])])
const medida = (v) => (v ? `${fmtNum(v.ancho_mm, 1)} × ${fmtNum(v.alto_mm, 1)} mm` : '')
const miniatura = (p) => (p.vigente || p.ultima ? `/api/etiquetas/versiones/${(p.vigente || p.ultima).id}/miniatura.svg?v=${encodeURIComponent(p.actualizada_en || '')}` : null)
const abierta = (p) => p.ultima && p.ultima.estado !== 'APROBADA' && p.ultima.estado !== 'ARCHIVADA' && (!p.vigente || p.ultima.id !== p.vigente.id)

// Diseño nuevo
const nuevo = ref(null)
function abrirNuevo() {
  nuevo.value = { nombre: '', descripcion: '', modalidad: 'OC_ARTICULO', unidad: 'LINEA', familia_id: '', tamano: 0, ancho: 100, alto: 50 }
}
watch(() => nuevo.value?.modalidad, (m) => {
  if (nuevo.value && !UNIDADES_DE[m].includes(nuevo.value.unidad)) nuevo.value.unidad = UNIDADES_DE[m][0]
})
function elegirTamano(i) {
  nuevo.value.tamano = i
  if (i >= 0) [, nuevo.value.ancho, nuevo.value.alto] = TAMANOS[i]
}
async function crear() {
  const n = nuevo.value
  try {
    const p = await api.post('/etiquetas/plantillas', { nombre: n.nombre, descripcion: n.descripcion, modalidad: n.modalidad, unidad: n.unidad,
      familia_id: n.familia_id || null, diseno: { ancho: Number(n.ancho), alto: Number(n.alto) } })
    avisar(t('Design “{0}” created as draft version 1.', [p.nombre]))
    router.push(`/etiquetas/plantillas/${p.id}`)
  } catch (e) {
    errorApi(e)
  }
}

// Duplicar: otro diseño independiente; el original no cambia
const copia = ref(null)
async function duplicar() {
  try {
    const p = await api.post(`/etiquetas/plantillas/${copia.value.id}/duplicar`, { nombre: copia.value.nombre })
    avisar(t('Copy “{0}” created; the original did not change.', [p.nombre]))
    copia.value = null
    router.push(`/etiquetas/plantillas/${p.id}`)
  } catch (e) {
    errorApi(e)
  }
}
async function archivar(p) {
  try {
    await api.post(`/etiquetas/plantillas/${p.id}/${p.estado === 'ACTIVA' ? 'archivar' : 'reactivar'}`, {})
    avisar(p.estado === 'ACTIVA' ? t('Design archived: it is no longer chosen for new labels; generated labels did not change.') : t('Design back in use.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <div class="barra-filtros">
    <label class="buscador"><Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" :placeholder="t('Search design')" :aria-label="t('Search design')" /></label>
    <Segmentos v-model="filtros.modalidad" :opciones="MODOS" :etiqueta="t('Data')" />
    <Seleccion v-model="filtros.familia_id" :aria-label="t('Labeling family')">
      <option value="">{{ t('Any family') }}</option>
      <option v-for="f in familias" :key="f.id" :value="f.id">{{ tx(f.nombre) }}</option>
    </Seleccion>
    <Seleccion v-model="filtros.estado_version" :aria-label="t('Version')">
      <option value="">{{ t('Any version') }}</option>
      <option value="PENDIENTE">{{ t('With a version pending approval') }}</option>
      <option value="BORRADOR">{{ t('With a draft') }}</option>
    </Seleccion>
    <label class="check"><input type="checkbox" :checked="filtros.estado === 'ARCHIVADA'" @change="filtros.estado = $event.target.checked ? 'ARCHIVADA' : 'ACTIVA'" /> {{ t('Archived') }}</label>
    <button v-if="puede('etiquetas.disenar')" type="button" class="btn btn-primario separar" @click="abrirNuevo"><Icono nombre="mas" />{{ t('New design') }}</button>
  </div>

  <div v-if="cargando && !datos.items.length" class="vacio">{{ t('Loading…') }}</div>
  <EstadoVacio v-else-if="!datos.items.length" icono="etiqueta" :titulo="filtros.q || filtros.modalidad || filtros.familia_id ? t('No designs match these filters.') : t('There are no label designs yet.')"
               :texto="t('Create a design, place fields of the item, the PO or the package on it and send it to approval.')">
    <button v-if="puede('etiquetas.disenar')" type="button" class="btn btn-primario" @click="abrirNuevo"><Icono nombre="mas" />{{ t('New design') }}</button>
  </EstadoVacio>
  <ul v-else class="tarjetas-etq">
    <li v-for="p in datos.items" :key="p.id" class="tarjeta-etq" :class="{ apagada: p.estado === 'ARCHIVADA' }">
      <router-link :to="`/etiquetas/plantillas/${p.id}`" class="miniatura-etq" :aria-label="t('Open {0}', [p.nombre])">
        <img v-if="miniatura(p)" :src="miniatura(p)" :alt="t('Preview of {0}', [p.nombre])" loading="lazy" />
      </router-link>
      <div class="cuerpo-etq">
        <router-link :to="`/etiquetas/plantillas/${p.id}`" class="nombre-etq">{{ tx(p.nombre) }}</router-link>
        <p class="sub">{{ tx(textoModalidad(p.modalidad)) }} · {{ tx(UNIDADES()[p.unidad] || p.unidad) }}</p>
        <div class="chips-etq">
          <span v-if="p.familia" class="etiqueta ms-0">{{ tx(p.familia) }}</span>
          <span class="etiqueta ms-0">{{ medida(p.vigente || p.ultima) }}</span>
          <span v-if="p.vigente" class="etiqueta ok ms-0">{{ t('In use: version {0}', [p.vigente.numero]) }}</span>
          <span v-else class="etiqueta aviso ms-0">{{ t('Not approved yet') }}</span>
          <span v-if="abierta(p)" class="ms-0"><EstadoBadge :estado="p.ultima.estado" tipo="etiqueta" /> v{{ p.ultima.numero }}</span>
        </div>
        <p class="ayuda">{{ p.asignaciones ? t('Applies in {0} places', [p.asignaciones]) : t('Not assigned yet') }} · {{ t('Updated {0}', [fmtFecha(p.actualizada_en)]) }}</p>
      </div>
      <div class="acciones-etq">
        <router-link :to="`/etiquetas/plantillas/${p.id}`" class="btn btn-chico">{{ puede('etiquetas.disenar') && p.estado === 'ACTIVA' ? t('Edit') : t('Open') }}</router-link>
        <button v-if="puede('etiquetas.disenar')" type="button" class="btn btn-chico" @click="copia = { id: p.id, nombre: t('{0} (copy)', [p.nombre]) }">{{ t('Duplicate') }}</button>
        <button v-if="puede('etiquetas.disenar') || puede('etiquetas.aprobar')" type="button" class="btn btn-chico" @click="archivar(p)">{{ p.estado === 'ACTIVA' ? t('Archive') : t('Reactivate') }}</button>
      </div>
    </li>
  </ul>

  <Modal v-if="nuevo" :titulo="t('New label design')" ancho="720px" @cerrar="nuevo = null">
    <form id="form-etq" class="formulario-etq" @submit.prevent="crear">
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="nuevo.nombre" required maxlength="120" :placeholder="t('E.g. Apparel label by size and color')" /></label>
      <fieldset class="campo">
        <legend class="req">{{ t('Where does the data come from?') }}</legend>
        <div class="opciones-modo">
          <label v-for="[v, txt, ayuda] in MODALIDADES()" :key="v" class="opcion-modo" :class="{ activa: nuevo.modalidad === v }">
            <input v-model="nuevo.modalidad" type="radio" :value="v" />
            <strong>{{ tx(txt) }}</strong><span class="ayuda">{{ tx(ayuda) }}</span>
          </label>
        </div>
      </fieldset>
      <div class="rejilla-campos">
        <label class="campo"><span>{{ t('Each label represents') }}</span>
          <Seleccion v-model="nuevo.unidad"><option v-for="u in UNIDADES_DE[nuevo.modalidad]" :key="u" :value="u">{{ tx(UNIDADES()[u]) }}</option></Seleccion>
        </label>
        <label class="campo"><span>{{ t('Designed for the family') }}</span>
          <Seleccion v-model="nuevo.familia_id"><option value="">{{ t('Any family') }}</option>
            <option v-for="f in familias.filter((x) => x.activa)" :key="f.id" :value="f.id">{{ tx(f.nombre) }}</option></Seleccion>
        </label>
        <label class="campo"><span>{{ t('Dimensions') }}</span>
          <Seleccion :model-value="nuevo.tamano" @update:model-value="(v) => elegirTamano(Number(v))">
            <option v-for="([txt], i) in TAMANOS" :key="txt" :value="i">{{ txt }}</option>
            <option :value="-1">{{ t('Custom dimensions') }}</option>
          </Seleccion>
        </label>
        <template v-if="nuevo.tamano === -1">
          <label class="campo"><span>{{ t('Width (mm)') }}</span><input v-model="nuevo.ancho" type="number" min="5" max="1000" step="0.1" required /></label>
          <label class="campo"><span>{{ t('Height (mm)') }}</span><input v-model="nuevo.alto" type="number" min="5" max="1000" step="0.1" required /></label>
        </template>
      </div>
      <label class="campo"><span>{{ t('Description') }}</span><textarea v-model="nuevo.descripcion" maxlength="500" rows="2"></textarea></label>
    </form>
    <template #pie>
      <button class="btn" type="button" @click="nuevo = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-etq">{{ t('Create and open the editor') }}</button>
    </template>
  </Modal>

  <Modal v-if="copia" :titulo="t('Duplicate design')" @cerrar="copia = null">
    <form id="form-copia" @submit.prevent="duplicar">
      <label class="campo"><span class="req">{{ t('Name of the copy') }}</span><input v-model="copia.nombre" required maxlength="120" /></label>
      <p class="ayuda mt">{{ t('The copy starts as a draft with the design in use; the original and its versions do not change.') }}</p>
    </form>
    <template #pie>
      <button class="btn" type="button" @click="copia = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-copia">{{ t('Duplicate') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.barra-filtros { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 16px; }
.tarjetas-etq { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.tarjeta-etq { background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio-panel); display: flex; flex-direction: column; overflow: hidden; box-shadow: var(--sombra); }
.tarjeta-etq.apagada { opacity: 0.65; }
.miniatura-etq { display: grid; place-items: center; height: 160px; background: repeating-conic-gradient(var(--linea-suave) 0% 25%, var(--superficie-2) 0% 50%) 0 0 / 16px 16px; border-bottom: 1px solid var(--linea); padding: 12px; }
.miniatura-etq img { max-width: 100%; max-height: 100%; box-shadow: 0 1px 4px rgb(0 0 0 / 18%); background: #fff; }
.cuerpo-etq { padding: 12px 14px 4px; display: flex; flex-direction: column; gap: 6px; flex: 1; }
.nombre-etq { font-weight: 650; color: var(--tinta); text-decoration: none; }
.nombre-etq:hover { color: var(--acento-texto); }
.chips-etq { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.acciones-etq { display: flex; gap: 6px; padding: 10px 14px 14px; flex-wrap: wrap; }
.formulario-etq { display: flex; flex-direction: column; gap: 14px; }
.opciones-modo { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 8px; margin-top: 6px; }
.opcion-modo { border: 1px solid var(--linea); border-radius: var(--radio); padding: 10px 12px; display: flex; flex-direction: column; gap: 4px; cursor: pointer; }
.opcion-modo input { position: absolute; opacity: 0; pointer-events: none; }
.opcion-modo.activa { border-color: var(--acento); background: var(--acento-claro); }
.opcion-modo:focus-within { box-shadow: 0 0 0 3px var(--foco); }
fieldset.campo { border: 0; padding: 0; margin: 0; }
</style>
