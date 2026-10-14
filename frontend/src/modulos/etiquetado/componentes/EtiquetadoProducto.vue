<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// Etiquetado de un producto, por variante (artículo): su familia de
// etiquetado, el diseño y la versión que se usaría y por qué, la vista previa
// con sus datos reales y el acceso a generar, a las excepciones y al historial.
const props = defineProps({ productoId: { type: Number, required: true } })
const articulos = ref([])
const familias = ref([])
const elecciones = ref({})
const modalidad = ref('OC_ARTICULO')
const cargando = ref(false)

async function cargar() {
  cargando.value = true
  try {
    const r = await api.get('/etiquetas/articulos', { producto_id: props.productoId, size: 200 })
    articulos.value = r.items
    await resolver()
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
async function resolver() {
  const pares = await Promise.all(articulos.value.map((a) => api.get('/etiquetas/resolver', { modalidad: modalidad.value, articulo_id: a.id })
    .then((r) => [a.id, r]).catch(() => [a.id, null])))
  elecciones.value = Object.fromEntries(pares)
}
watch(modalidad, resolver)
onMounted(() => {
  cargar()
  if (puede('etiquetas.familias')) api.get('/etiquetas/familias', { activas: true }).then((r) => (familias.value = r)).catch(() => {})
})

async function cambiarFamilia(a, id) {
  try {
    await api.post('/etiquetas/articulos/familia', { familia_id: id === '' || id === 'ninguna' ? null : Number(id), ids: [a.id] })
    avisar(t('Labeling family of {0} changed.', [a.sku]))
    await cargar()
  } catch (e) {
    errorApi(e)
  }
}
const sinFamilia = computed(() => articulos.value.filter((a) => !a.familia).length)

const previa = ref(null)
async function verPrevia(a) {
  const e = elecciones.value[a.id]
  try {
    const r = await api.post('/etiquetas/vista-previa', { version_id: e.version_id, articulo_id: a.id })
    previa.value = { a, e, ...r }
  } catch (err) {
    errorApi(err)
  }
}
const MODOS = computed(() => [['OC_ARTICULO', t('PO and item')], ['ARTICULO', t('Item')]])
</script>

<template>
  <div class="panel mt-chico etq-producto">
    <div class="fila-flex entre">
      <p class="ayuda mb-0">{{ t('Which label design each variant uses, by priority: PO exception, item, product, labeling family, general.') }}</p>
      <Segmentos v-model="modalidad" :opciones="MODOS" :etiqueta="t('Data on the label')" />
    </div>
    <p v-if="sinFamilia" class="nota aviso mt-chico"><Icono nombre="alerta" :tam="16" />{{ t('{0} variants have no labeling family: they only get item, product or general designs.', [sinFamilia]) }}</p>
    <div class="tabla-marco mt-chico etq-tabla">
    <table class="tabla">
      <thead><tr><th>{{ t('SKU') }}</th><th>{{ t('Color') }}</th><th>{{ t('Size') }}</th><th>{{ t('Labeling family') }}</th><th>{{ t('Design and version') }}</th><th>{{ t('Why') }}</th><th /></tr></thead>
      <tbody>
        <tr v-for="a in articulos" :key="a.id">
          <td><strong class="codigo">{{ a.sku }}</strong></td>
          <td>{{ a.color }}</td>
          <td>{{ a.talla }}</td>
          <td>
            <Seleccion v-if="puede('etiquetas.familias')" :model-value="a.familia_id || ''" :aria-label="t('Labeling family')" @change="(v) => cambiarFamilia(a, v)">
              <option value="">{{ t('Without family') }}</option>
              <option v-for="f in familias" :key="f.id" :value="f.id">{{ tx(f.nombre) }}</option>
            </Seleccion>
            <span v-else-if="a.familia" class="etiqueta ms-0">{{ tx(a.familia) }}</span>
            <span v-else class="etiqueta aviso ms-0">{{ t('Without family') }}</span>
          </td>
          <td>
            <template v-if="elecciones[a.id]?.plantilla">{{ tx(elecciones[a.id].plantilla) }} <span class="etiqueta ms-0">v{{ elecciones[a.id].version }}</span></template>
            <span v-else-if="elecciones[a.id]?.ambigua" class="texto-aviso">{{ t('Several apply: chosen when generating') }}</span>
            <span v-else-if="elecciones[a.id]" class="texto-error">{{ t('No approved design applies') }}</span>
          </td>
          <td class="ayuda">{{ tx(elecciones[a.id]?.motivo || '') }}<template v-for="(x, i) in elecciones[a.id]?.avisos || []" :key="i"><br />{{ tx(x) }}</template></td>
          <td class="num nowrap">
            <button v-if="elecciones[a.id]?.version_id" type="button" class="btn btn-chico" @click="verPrevia(a)"><Icono nombre="ojo" :tam="15" />{{ t('See') }}</button>
            <router-link v-if="modalidad === 'ARTICULO' && elecciones[a.id]?.version_id && puede('etiquetas.generar')" :to="{ path: '/etiquetas/generar', query: { articulo: a.id } }" class="btn btn-chico">{{ t('Generate') }}</router-link>
          </td>
        </tr>
        <tr v-if="!articulos.length && !cargando"><td colspan="7" class="ayuda">{{ t('This product has no variants yet.') }}</td></tr>
      </tbody>
    </table>
    </div>
    <div class="fila-flex mt-chico">
      <router-link v-if="puede('etiquetas.asignar')" :to="{ path: '/etiquetas', query: { vista: 'asignaciones' } }" class="btn btn-chico"><Icono nombre="ruta" :tam="15" />{{ t('Assign a design to this product or an item') }}</router-link>
      <router-link :to="{ path: '/etiquetas', query: { vista: 'historial' } }" class="btn btn-chico btn-texto"><Icono nombre="historial" :tam="15" />{{ t('Generated labels') }}</router-link>
    </div>

    <Modal v-if="previa" :titulo="`${previa.a.sku} · ${tx(previa.e.plantilla)} v${previa.e.version}`" ancho="640px" @cerrar="previa = null">
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="etq-previa" v-html="previa.svg" />
      <p class="ayuda">{{ tx(previa.e.motivo || '') }}</p>
      <ul v-if="previa.problemas.length" class="etq-lista">
        <li v-for="(x, i) in previa.problemas" :key="i" :class="x.nivel"><strong v-if="x.nombre">{{ x.nombre }}: </strong>{{ tx(x.mensaje) }}</li>
      </ul>
    </Modal>
  </div>
</template>

<style scoped>
.etq-previa { display: flex; justify-content: center; padding: 14px; background: repeating-conic-gradient(#eef1f5 0 25%, #fff 0 50%) 0 0 / 14px 14px; border-radius: 8px; }
.etq-previa :deep(svg) { max-width: 100%; height: auto; max-height: 420px; box-shadow: 0 1px 3px rgba(16, 24, 40, 0.25); }
.etq-lista { margin: 8px 0 0; padding-left: 18px; font-size: 0.82rem; }
.etq-lista .error { color: var(--error); }
.etq-lista .advertencia { color: var(--aviso); }
.texto-aviso { color: var(--aviso); font-size: 0.82rem; }
.etq-producto td :deep(.sb) { min-width: 150px; }
.etq-tabla { overflow-x: auto; }
.etq-tabla td.ayuda { min-width: 180px; }
</style>
