<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { avisar, errorApi } from '../stores/ui'
import CargaArchivo from './CargaArchivo.vue'
import Icono from './Icono.vue'
import Modal from './Modal.vue'

// Carga masiva desde Excel: plantilla con las columnas y los valores
// permitidos, el archivo y el resultado fila por fila.
const props = defineProps({
  titulo: { type: String, required: true },
  ruta: { type: String, required: true }, // POST del archivo
  plantilla: { type: String, default: '' }, // GET de la plantilla
  params: { type: Object, default: () => ({}) },
  ayuda: { type: String, default: '' },
})
const emit = defineEmits(['cerrar', 'cargado'])
const archivo = ref(null)
const resultado = ref(null)
const ocupado = ref(false)

async function bajarPlantilla() {
  try {
    await api.descargar(props.plantilla, 'template.xlsx', props.params)
  } catch (e) {
    errorApi(e)
  }
}
async function subir() {
  const datos = new FormData()
  datos.append('archivo', archivo.value)
  ocupado.value = true
  try {
    const q = new URLSearchParams(Object.entries(props.params).filter(([, v]) => v !== '' && v != null && v !== false)).toString()
    resultado.value = await api.post(props.ruta + (q ? `?${q}` : ''), datos)
    const r = resultado.value
    avisar(`${r.creados ?? 0} created and ${r.actualizados ?? 0} updated${r.errores?.length ? `; ${r.errores.length} rows with errors` : ''}.`,
      r.errores?.length ? 'error' : 'ok')
    emit('cargado', r)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <Modal :titulo="props.titulo" ancho="700px" @cerrar="emit('cerrar')">
    <ol class="pasos-carga">
      <li><b>Download the template.</b> It has the columns, the allowed values in drop-down lists and an Instructions sheet.
        <button v-if="props.plantilla" type="button" class="btn btn-chico" @click="bajarPlantilla"><Icono nombre="descargar" :tam="14" />Excel template</button></li>
      <li><b>Fill it in</b> (or use your own file with the same column names) and upload it.</li>
    </ol>
    <p v-if="props.ayuda" class="ayuda">{{ props.ayuda }}</p>
    <slot />
    <CargaArchivo v-model="archivo" />
    <template v-if="resultado">
      <div class="nota ok mt-chico"><Icono nombre="check" />
        <span>{{ resultado.creados ?? 0 }} created and {{ resultado.actualizados ?? 0 }} updated<template v-if="resultado.borrados">; {{ resultado.borrados }} replaced</template>.
          <slot name="resultado" :resultado="resultado" /></span></div>
      <div v-if="resultado.errores?.length" class="nota error bloque mt-chico">
        <b>{{ resultado.errores.length }} rows were not loaded:</b>
        <ul class="lista-mensajes"><li v-for="(e, i) in resultado.errores.slice(0, 50)" :key="i">Row {{ e.fila }}: {{ e.mensaje }}</li></ul>
      </div>
    </template>
    <template #pie>
      <button class="btn" @click="emit('cerrar')">{{ resultado ? 'Close' : 'Cancel' }}</button>
      <button class="btn btn-primario" :disabled="!archivo || ocupado" @click="subir"><Icono nombre="importar" />{{ ocupado ? 'Loading…' : 'Upload' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.pasos-carga { margin: 0 0 12px; padding-left: 20px; display: flex; flex-direction: column; gap: 8px; font-size: 0.9rem; }
.pasos-carga .btn { margin-left: 8px; }
</style>
