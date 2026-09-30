<script setup>
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
    avisar(`${x.clasificados} products classified by the engine. Review them in Products.`)
  } catch (e) {
    errorApi(e)
  } finally {
    avance.value = null
    emit('listo')
  }
}
</script>

<template>
  <CargaMasiva titulo="Upload items with their technical sheet" ruta="/catalogos/articulos/importar" plantilla="/catalogos/articulos/plantilla"
               ayuda="Rows of the same style and color share one product. Fill the technical sheet columns you have: after the upload the engine completes the rest and suggests the HS code."
               @cerrar="emit('cerrar')" @cargado="alCargar">
    <template #resultado="{ resultado }">
      <template v-if="resultado.productos_total"> {{ resultado.productos_total }} products (style-color).</template>
      <template v-if="avance"> Classifying {{ avance.n }} of {{ avance.total }}…</template>
      <template v-else-if="clasificados !== null"> {{ clasificados }} classified; they are waiting for review in <router-link to="/productos?estado=sugerida">Products</router-link>.</template>
    </template>
  </CargaMasiva>
</template>
