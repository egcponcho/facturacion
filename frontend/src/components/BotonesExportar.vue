<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { errorApi } from '../stores/ui'
import Icono from './Icono.vue'

// Descarga el reporte del tablero con los filtros de la pantalla.
const props = defineProps({ ruta: { type: String, required: true }, params: { type: Object, default: () => ({}) } })
const bajando = ref('')
async function bajar(formato) {
  bajando.value = formato
  try {
    await api.descargar(props.ruta, `reporte.${formato}`, { ...props.params, formato })
  } catch (e) {
    errorApi(e)
  } finally {
    bajando.value = ''
  }
}
</script>

<template>
  <div class="acciones-exportar">
    <button type="button" class="btn btn-fantasma btn-chico" :disabled="!!bajando" title="Reporte en PDF con los filtros aplicados" @click="bajar('pdf')">
      <Icono nombre="descargar" :tam="14" />{{ bajando === 'pdf' ? 'Generando…' : 'PDF' }}
    </button>
    <button type="button" class="btn btn-fantasma btn-chico" :disabled="!!bajando" title="Reporte en Excel con los filtros aplicados y el detalle" @click="bajar('xlsx')">
      <Icono nombre="descargar" :tam="14" />{{ bajando === 'xlsx' ? 'Generando…' : 'Excel' }}
    </button>
  </div>
</template>

<style scoped>
.acciones-exportar { display: inline-flex; gap: 6px; }
</style>
