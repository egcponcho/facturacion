<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref } from 'vue'
import { api } from '@/nucleo/api'
import { avisar, errorApi } from '@/stores/ui'
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
const vista = ref(null) // vista previa de la plantilla
const hoja = ref(0)

async function verPlantilla() {
  if (vista.value) return (vista.value = null)
  try {
    vista.value = await api.get(props.plantilla, { ...props.params, vista: 1 })
    hoja.value = 0
  } catch (e) {
    errorApi(e)
  }
}

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
    avisar(t('{0} created and {1} updated{2}.', [r.creados ?? 0, r.actualizados ?? 0, r.errores?.length ? t('; {0} rows with errors', [r.errores.length]) : '']),
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
  <Modal :titulo="tx(props.titulo)" :ancho="vista ? '960px' : '700px'" @cerrar="emit('cerrar')">
    <ol class="pasos-carga">
      <li><b>{{ t('Download the template.') }}</b> {{ t('It has the columns, the allowed values in drop-down lists and an Instructions sheet.') }}
        <button v-if="props.plantilla" type="button" class="btn btn-chico" @click="bajarPlantilla"><Icono nombre="descargar" :tam="14" />{{ t('Excel template') }}</button>
        <button v-if="props.plantilla" type="button" class="btn btn-chico" :aria-expanded="!!vista" @click="verPlantilla"><Icono nombre="lupa" :tam="14" />{{ tx(vista ? t('Hide preview') : t('Preview')) }}</button></li>
      <li><b>{{ t('Fill it in') }}</b> {{ t('(or use your own file with the same column names) and upload it.') }}</li>
    </ol>
    <div v-if="vista" class="vista-plantilla">
      <div v-if="vista.hojas.length > 1" class="pestanas-pildora" role="tablist">
        <button v-for="(h, i) in vista.hojas" :key="h.nombre" type="button" class="pildora" role="tab" :aria-selected="hoja === i" @click="hoja = i">{{ t('Sheet {0}', [h.nombre]) }}</button>
      </div>
      <div class="tabla-marco">
        <table class="tabla" v-tarjetas>
          <thead><tr><th v-for="c in vista.hojas[hoja].columnas" :key="c.nombre" :title="tx(c.ayuda)"><span :class="{ req: c.req }">{{ tx(c.nombre) }}</span></th></tr></thead>
          <tbody>
            <tr v-for="(f, i) in vista.hojas[hoja].filas" :key="i"><td v-for="(v, j) in f" :key="j">{{ tx(v) }}</td></tr>
            <tr v-if="!vista.hojas[hoja].filas.length"><td :colspan="vista.hojas[hoja].columnas.length" class="vacio">{{ t('No example rows.') }}</td></tr>
          </tbody>
        </table>
      </div>
      <details class="mt-chico">
        <summary>{{ t('What goes in each column') }}</summary>
        <dl class="guia-cols">
          <template v-for="c in vista.hojas[hoja].columnas" :key="c.nombre"><dt><span :class="{ req: c.req }">{{ tx(c.nombre) }}</span></dt><dd>{{ tx(c.ayuda || '—') }}</dd></template>
        </dl>
      </details>
      <ul v-if="vista.instrucciones.length" class="ayuda lista-instr"><li v-for="(txt, i) in vista.instrucciones" :key="i">{{ tx(txt) }}</li></ul>
    </div>
    <p v-if="props.ayuda" class="ayuda">{{ tx(props.ayuda) }}</p>
    <slot />
    <CargaArchivo v-model="archivo" />
    <template v-if="resultado">
      <div class="nota ok mt-chico"><Icono nombre="check" />
        <span>{{ t('{0} created and {1} updated', [resultado.creados ?? 0, resultado.actualizados ?? 0]) }}<template v-if="resultado.borrados">{{ t('; {0} replaced', [resultado.borrados]) }}</template>.
          <slot name="resultado" :resultado="resultado" /></span></div>
      <div v-if="resultado.errores?.length" class="nota error bloque mt-chico">
        <b>{{ t('{0} rows were not loaded:', [resultado.errores.length]) }}</b>
        <ul class="lista-mensajes"><li v-for="(e, i) in resultado.errores.slice(0, 50)" :key="i">{{ t('Row {0}: {1}', [e.fila, e.mensaje]) }}</li></ul>
      </div>
    </template>
    <template #pie>
      <button class="btn" @click="emit('cerrar')">{{ tx(resultado ? t('Close') : t('Cancel')) }}</button>
      <button class="btn btn-primario" :disabled="!archivo || ocupado" @click="subir"><Icono nombre="importar" />{{ tx(ocupado ? t('Loading…') : t('Upload')) }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.pasos-carga { margin: 0 0 12px; padding-inline-start: 20px; display: flex; flex-direction: column; gap: 8px; font-size: 0.9rem; }
.pasos-carga .btn { margin-inline-start: 8px; }
.vista-plantilla { margin-bottom: 12px; }
.vista-plantilla .pestanas-pildora { margin-bottom: 8px; }
.vista-plantilla .tabla-marco { max-height: 260px; overflow: auto; }
.vista-plantilla th, .vista-plantilla td { white-space: nowrap; font-size: 0.82rem; }
.guia-cols { display: grid; grid-template-columns: minmax(120px, max-content) 1fr; gap: 4px 12px; font-size: 0.84rem; margin: 8px 0 0; max-height: 220px; overflow: auto; }
.guia-cols dt { font-weight: 600; }
.guia-cols dd { margin: 0; color: var(--tinta-2); }
.lista-instr { margin: 8px 0 0; padding-inline-start: 18px; }
</style>
