<script setup>
import { t } from '../i18n/index.js'
import { ref } from 'vue'
import { clasificarVarios } from '../clasificacion/useClasificacion'
import { avisar, errorApi } from '../stores/ui'
import CargaMasiva from './CargaMasiva.vue'

// Carga de artículos con su ficha técnica: el servidor guarda los artículos y
// la ficha de cada estilo-color; en seguida el motor completa lo que falta y
// sugiere la partida de cada producto cargado.
const emit = defineEmits(['cerrar', 'listo'])
const avance = ref(null)
const clasificados = ref(null)

async function alCargar(r) {
  clasificados.value = null
  if (!r.productos?.length) {
    emit('listo')
    return
  }
  avance.value = { n: 0, total: r.productos.length }
  try {
    const x = await clasificarVarios(r.productos, (n, total) => (avance.value = { n, total }))
    clasificados.value = x.clasificados
    avisar(t('{0} products classified by the engine. Review them in Products.', [x.clasificados]))
  } catch (e) {
    errorApi(e)
  } finally {
    avance.value = null
    emit('listo')
  }
}
</script>

<template>
  <CargaMasiva :titulo="t('Upload items with their technical sheet')" ruta="/catalogos/articulos/importar" plantilla="/catalogos/articulos/plantilla"
               :ayuda="t('Sheet Generics: one row per generic (style-color) with its data and technical sheet. Sheet Sizes: one row per size with your item code, or leave it empty to use the generic plus a size code. After the upload the engine completes the sheet and suggests the HS code.')"
               @cerrar="emit('cerrar')" @cargado="alCargar">
    <template #resultado="{ resultado }">
      <template v-if="resultado.productos_total"> {{ t('{0} products (style-color).', [resultado.productos_total]) }}</template>
      <template v-if="avance"> {{ t('Classifying {0} of {1}…', [avance.n, avance.total]) }}</template>
      <template v-else-if="clasificados !== null"> {{ t('{0} classified as drafts; send them to review from', [clasificados]) }} <router-link to="/productos?estado=sugerida">{{ t('Products') }}</router-link>.</template>
    </template>
  </CargaMasiva>
</template>
