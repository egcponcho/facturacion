<script setup>
import { t, tx } from '../i18n/index.js'
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
    await api.descargar(props.ruta, t('reporte.{0}', [formato]), { ...props.params, formato })
  } catch (e) {
    errorApi(e)
  } finally {
    bajando.value = ''
  }
}
</script>

<template>
  <div class="acciones-exportar">
    <button type="button" class="btn btn-fantasma btn-chico" :disabled="!!bajando" :title="t('PDF report with the applied filters')" @click="bajar('pdf')">
      <Icono nombre="descargar" :tam="14" />{{ tx(bajando === 'pdf' ? t('Generating…') : 'PDF') }}
    </button>
    <button type="button" class="btn btn-fantasma btn-chico" :disabled="!!bajando" :title="t('Excel report with the applied filters and the detail')" @click="bajar('xlsx')">
      <Icono nombre="descargar" :tam="14" />{{ tx(bajando === 'xlsx' ? t('Generating…') : t('Excel')) }}
    </button>
  </div>
</template>

<style scoped>
.acciones-exportar { display: inline-flex; gap: 6px; }
</style>
