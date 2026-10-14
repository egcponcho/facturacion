<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { fmtFecha, fmtNum } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import CabezaEtiquetado from '@/modulos/etiquetado/componentes/CabezaEtiquetado.vue'
import { CANTIDADES, SUJETOS, catalogos, textoDonde } from '@/modulos/etiquetado/etiquetas.js'

// Diseños de etiqueta agrupados por tipo de etiqueta: miniatura, versión en
// uso, la que está en curso y dónde se usa (enlace a la matriz).
const router = useRouter()
const filtros = reactive({ q: '', estado: 'ACTIVA', estado_version: '' })
const datos = ref({ items: [], total: 0 })
const tipos = ref([])
const cargando = ref(false)

async function cargar() {
  cargando.value = true
  try {
    ;[datos.value, tipos.value] = await Promise.all([api.get('/etiquetas/plantillas', { ...filtros, size: 200 }), api.get('/etiquetas/tipos', { todos: true })])
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
watch(() => [filtros.estado, filtros.estado_version], cargar)
onMounted(cargar)
alCambiar(() => cargar(), ['/etiquetas/plantillas', '/etiquetas/usos', '/etiquetas/tipos'])

// Una sección por tipo, en el orden de la empresa
const grupos = computed(() => tipos.value.map((tp) => ({ tipo: tp, disenos: datos.value.items.filter((p) => p.tipo_etiqueta_id === tp.id) }))
  .filter((g) => g.disenos.length || (!filtros.q && filtros.estado === 'ACTIVA' && g.tipo.activo)))
const medida = (v) => (v ? `${fmtNum(v.ancho_mm, 1)} × ${fmtNum(v.alto_mm, 1)} mm` : '')
const miniatura = (p) => (p.vigente || p.ultima ? `/api/etiquetas/versiones/${(p.vigente || p.ultima).id}/miniatura.svg?v=${encodeURIComponent(p.actualizada_en || '')}` : null)
const abierta = (p) => p.ultima && !['APROBADA', 'ARCHIVADA'].includes(p.ultima.estado) && (!p.vigente || p.ultima.id !== p.vigente.id)
// «Se usa en: Calzado, Ropa · 2 excepciones»
function seUsaEn(p) {
  const lugares = (p.se_usa_en || []).filter((u) => !u.excepcion).map((u) => textoDonde(u.nivel, u.destino))
  const excepciones = (p.se_usa_en || []).filter((u) => u.excepcion).length
  return [lugares.join(', '), excepciones ? t('{0} exceptions', [excepciones]) : ''].filter(Boolean).join(' · ')
}

// Diseño nuevo: tipo, nombre, tamaño (de la empresa o a mano) y desde dónde empezar
const tamanos = ref([])
onMounted(() => catalogos().then((c) => (tamanos.value = c.tamanos)).catch(() => {}))
const nuevo = ref(null)
function abrirNuevo(tipoId = '') {
  nuevo.value = { nombre: '', descripcion: '', tipo_etiqueta_id: tipoId || tipos.value.find((x) => x.activo)?.id || '', tamano: 0, ancho: 100, alto: 50,
    desde: 'blanco', copia_id: '' }
}
const copiables = computed(() => datos.value.items.filter((p) => p.tipo_etiqueta_id === Number(nuevo.value?.tipo_etiqueta_id) && (p.vigente || p.ultima)))
async function crear() {
  const n = nuevo.value
  try {
    let p
    if (n.desde === 'copia' && n.copia_id) {
      p = await api.post(`/etiquetas/plantillas/${n.copia_id}/duplicar`, { nombre: n.nombre })
    } else {
      const tam = n.tamano >= 0 ? tamanos.value[n.tamano] : { ancho: Number(n.ancho), alto: Number(n.alto) }
      p = await api.post('/etiquetas/plantillas', { nombre: n.nombre, descripcion: n.descripcion, tipo_etiqueta_id: Number(n.tipo_etiqueta_id),
        tamano: { ancho: tam.ancho, alto: tam.alto } })
    }
    avisar(t('Design “{0}” created as draft version 1.', [p.nombre]))
    router.push(`/etiquetas/disenos/${p.id}`)
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
    router.push(`/etiquetas/disenos/${p.id}`)
  } catch (e) {
    errorApi(e)
  }
}
// Archivar un diseño en uso avisa qué queda sin diseño
async function archivar(p) {
  if (p.estado === 'ACTIVA' && p.usos) {
    const donde = seUsaEn(p)
    if (!(await confirmar(t('This design is in use ({0}). Those places stop using it and fall back to what they inherit, or are left without a design.', [donde]),
      { titulo: t('Archive design'), boton: t('Archive'), peligro: true }))) return
  }
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
  <CabezaEtiquetado :titulo="t('Label designs')" :texto="t('Each design belongs to a label type; place the data of the item, the package or the PO and send it to approval.')">
    <button v-if="puede('etiquetas.disenar') && tipos.length" type="button" class="btn btn-primario" @click="abrirNuevo()"><Icono nombre="mas" />{{ t('New design') }}</button>
  </CabezaEtiquetado>

  <div class="barra-filtros">
    <label class="buscador"><Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" :placeholder="t('Search design')" :aria-label="t('Search design')" /></label>
    <Seleccion v-model="filtros.estado_version" :aria-label="t('Version')">
      <option value="">{{ t('Any version') }}</option>
      <option value="PENDIENTE">{{ t('With a version pending approval') }}</option>
      <option value="BORRADOR">{{ t('With a draft') }}</option>
    </Seleccion>
    <label class="check"><input type="checkbox" :checked="filtros.estado === 'ARCHIVADA'" @change="filtros.estado = $event.target.checked ? 'ARCHIVADA' : 'ACTIVA'" /> {{ t('Archived') }}</label>
  </div>

  <div v-if="cargando && !datos.items.length && !tipos.length" class="vacio">{{ t('Loading…') }}</div>
  <EstadoVacio v-else-if="!tipos.length" icono="etiqueta" :titulo="t('Your company has no label types yet')"
               :texto="t('Create the label types first (Setup); each design belongs to one.')">
    <router-link to="/etiquetas/configuracion?vista=tipos" class="btn btn-primario">{{ t('Go to setup') }}</router-link>
  </EstadoVacio>
  <p v-else-if="!grupos.length" class="vacio">{{ t('No designs match these filters.') }}</p>
  <section v-for="g in grupos" :key="g.tipo.id" class="grupo-etq">
    <div class="grupo-cabeza">
      <h2>{{ tx(g.tipo.nombre) }} <span class="ayuda">· {{ SUJETOS()[g.tipo.sujeto] }} · {{ CANTIDADES()[g.tipo.cantidad] }}</span></h2>
      <button v-if="puede('etiquetas.disenar') && g.tipo.activo" type="button" class="btn btn-chico" @click="abrirNuevo(g.tipo.id)"><Icono nombre="mas" :tam="14" />{{ t('New design') }}</button>
    </div>
    <p v-if="!g.disenos.length" class="ayuda">{{ t('No designs of this type yet.') }}</p>
    <ul v-else class="tarjetas-etq">
      <li v-for="p in g.disenos" :key="p.id" class="tarjeta-etq" :class="{ apagada: p.estado === 'ARCHIVADA' }">
        <router-link :to="`/etiquetas/disenos/${p.id}`" class="miniatura-etq" :aria-label="t('Open {0}', [p.nombre])">
          <img v-if="miniatura(p)" :src="miniatura(p)" :alt="t('Preview of {0}', [p.nombre])" loading="lazy" />
        </router-link>
        <div class="cuerpo-etq">
          <router-link :to="`/etiquetas/disenos/${p.id}`" class="nombre-etq">{{ tx(p.nombre) }}</router-link>
          <div class="chips-etq">
            <span class="etiqueta ms-0">{{ medida(p.vigente || p.ultima) }}</span>
            <span v-if="p.vigente" class="etiqueta ok ms-0">{{ t('In use: version {0}', [p.vigente.numero]) }}</span>
            <span v-else class="etiqueta aviso ms-0">{{ t('Not approved yet') }}</span>
            <span v-if="abierta(p)" class="ms-0"><EstadoBadge :estado="p.ultima.estado" tipo="etiqueta" /> v{{ p.ultima.numero }}</span>
          </div>
          <p class="ayuda">
            <template v-if="p.usos">{{ t('Used in: {0}', [seUsaEn(p)]) }} · <router-link to="/etiquetas/configuracion" class="enlace">{{ t('see') }}</router-link></template>
            <template v-else>{{ t('Not used anywhere yet') }}</template>
            · {{ t('Updated {0}', [fmtFecha(p.actualizada_en)]) }}</p>
        </div>
        <div class="acciones-etq">
          <router-link :to="`/etiquetas/disenos/${p.id}`" class="btn btn-chico">{{ puede('etiquetas.disenar') && p.estado === 'ACTIVA' ? t('Edit') : t('Open') }}</router-link>
          <button v-if="puede('etiquetas.disenar')" type="button" class="btn btn-chico" @click="copia = { id: p.id, nombre: t('{0} (copy)', [p.nombre]) }">{{ t('Duplicate') }}</button>
          <button v-if="puede('etiquetas.disenar') || puede('etiquetas.aprobar')" type="button" class="btn btn-chico" @click="archivar(p)">{{ p.estado === 'ACTIVA' ? t('Archive') : t('Reactivate') }}</button>
        </div>
      </li>
    </ul>
  </section>

  <Modal v-if="nuevo" :titulo="t('New label design')" ancho="640px" @cerrar="nuevo = null">
    <form id="form-etq" class="formulario-etq" @submit.prevent="crear">
      <label class="campo"><span class="req">{{ t('Label type') }}</span>
        <Seleccion v-model="nuevo.tipo_etiqueta_id" required>
          <option v-for="tp in tipos.filter((x) => x.activo)" :key="tp.id" :value="tp.id">{{ tx(tp.nombre) }} ({{ SUJETOS()[tp.sujeto] }})</option>
        </Seleccion>
        <small class="ayuda">{{ t('The editor offers only the data of what this type labels.') }}</small></label>
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="nuevo.nombre" required maxlength="120" :placeholder="t('E.g. Apparel hang tag 2×3 in')" /></label>
      <fieldset class="campo">
        <legend>{{ t('Start from') }}</legend>
        <div class="desde">
          <label class="check"><input v-model="nuevo.desde" type="radio" value="blanco" /> {{ t('Blank') }}</label>
          <label class="check"><input v-model="nuevo.desde" type="radio" value="copia" :disabled="!copiables.length" /> {{ t('A copy of another design of this type') }}</label>
        </div>
      </fieldset>
      <label v-if="nuevo.desde === 'copia'" class="campo"><span class="req">{{ t('Design to copy') }}</span>
        <Seleccion v-model="nuevo.copia_id" required><option v-for="p in copiables" :key="p.id" :value="p.id">{{ tx(p.nombre) }}</option></Seleccion></label>
      <div v-else class="rejilla-campos">
        <label class="campo"><span>{{ t('Dimensions') }}</span>
          <Seleccion :model-value="nuevo.tamano" @update:model-value="(v) => (nuevo.tamano = Number(v))">
            <option v-for="(x, i) in tamanos" :key="i" :value="i">{{ x.nombre }} ({{ fmtNum(x.ancho, 1) }} × {{ fmtNum(x.alto, 1) }} mm)</option>
            <option :value="-1">{{ t('Custom dimensions') }}</option>
          </Seleccion></label>
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
.grupo-etq { margin-bottom: 26px; }
.grupo-cabeza { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.grupo-cabeza h2 { margin: 0; font-size: 1.05rem; }
.tarjetas-etq { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.tarjeta-etq { background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio-panel); display: flex; flex-direction: column; overflow: hidden; box-shadow: var(--sombra); }
.tarjeta-etq.apagada { opacity: 0.65; }
.miniatura-etq { display: flex; align-items: center; justify-content: center; overflow: hidden; height: 160px; background: repeating-conic-gradient(var(--linea-suave) 0% 25%, var(--superficie-2) 0% 50%) 0 0 / 16px 16px; border-bottom: 1px solid var(--linea); padding: 12px; }
.miniatura-etq img { max-width: 100%; max-height: 100%; object-fit: contain; box-shadow: 0 1px 4px rgb(0 0 0 / 18%); background: #fff; }
.cuerpo-etq { padding: 12px 14px 4px; display: flex; flex-direction: column; gap: 6px; flex: 1; }
.nombre-etq { font-weight: 650; color: var(--tinta); text-decoration: none; }
.nombre-etq:hover { color: var(--acento-texto); }
.chips-etq { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.acciones-etq { display: flex; gap: 6px; padding: 10px 14px 14px; flex-wrap: wrap; }
.formulario-etq { display: flex; flex-direction: column; gap: 14px; }
.desde { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 6px; }
fieldset.campo { border: 0; padding: 0; margin: 0; }
</style>
