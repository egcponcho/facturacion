<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref } from 'vue'
import { api } from '@/nucleo/api'
import { avisar } from '@/stores/ui'
import { puede } from '@/stores/sesion'
import Icono from '@/componentes/Icono.vue'

// Los errores de una ejecución: filas rechazadas (con la fila del archivo y el motivo) y
// conflictos de referencias externas. Las filas se descargan con sus columnas originales para
// corregirlas y volver a subirlas; un conflicto de código se resuelve desvinculando la
// referencia, con motivo (queda en el historial de la integración).
const props = defineProps({
  ejecucion: { type: Object, required: true }, // { id, integracion_id, errores }
  maximo: { type: Number, default: 20 },
})
const emit = defineEmits(['desvinculado'])

const errores = computed(() => props.ejecucion.errores || [])
const conFila = computed(() => errores.value.some((x) => x.fila != null))
const motivo = ref('')
const abierto = ref(null) // id de la referencia que se está desvinculando
const ocupado = ref(false)

async function descargar() {
  try {
    await api.descargar(`/integraciones/ejecuciones/${props.ejecucion.id}/rechazadas`, 'rejected.csv')
  } catch (e) {
    avisar(e.message, 'error')
  }
}
async function desvincular(c) {
  ocupado.value = true
  try {
    await api.post(`/integraciones/${props.ejecucion.integracion_id}/referencias/${c.referencia_id}/desvincular`, { motivo: motivo.value })
    avisar(t('Link removed: run the exchange again to link the right record.'))
    abierto.value = null
    motivo.value = ''
    emit('desvinculado')
  } catch (e) {
    avisar(e.message, 'error')
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <div v-if="errores.length" class="err-ejec">
    <ul class="lista-errores">
      <li v-for="(x, i) in errores.slice(0, maximo)" :key="i">
        <b>{{ x.fila != null ? t('Row {0}', [x.fila]) : x.referencia }}</b>: {{ (x.mensajes || []).map(tx).join(' ') }}
        <template v-if="x.conflicto?.referencia_id && puede('integraciones.configurar')">
          <button v-if="abierto !== x.conflicto.referencia_id" type="button" class="btn-enlace" @click="abierto = x.conflicto.referencia_id; motivo = ''">
            {{ t('Unlink {0}', [x.conflicto.motivo === 'otro_codigo' ? x.conflicto.codigo_actual : x.conflicto.codigo_externo]) }}</button>
          <span v-else class="err-desvincular">
            <input v-model="motivo" class="entrada" maxlength="300" :placeholder="t('Why is the link wrong?')" :aria-label="t('Reason')" />
            <button type="button" class="btn btn-chico btn-peligro" :disabled="ocupado || motivo.trim().length < 3" @click="desvincular(x.conflicto)">{{ t('Unlink') }}</button>
            <button type="button" class="btn btn-chico" @click="abierto = null">{{ t('Cancel') }}</button>
          </span>
        </template>
      </li>
    </ul>
    <p v-if="errores.length > maximo" class="ayuda">{{ t('And {0} more.', [errores.length - maximo]) }}</p>
    <button v-if="conFila" type="button" class="btn btn-chico" @click="descargar"><Icono nombre="descargar" :tam="14" />{{ t('Download rejected rows') }}</button>
  </div>
</template>

<style scoped>
.err-ejec { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.lista-errores { margin: 0; padding-inline-start: 18px; color: var(--error); font-size: var(--t-sm); }
.lista-errores li { margin-block: 2px; }
.btn-enlace { background: none; border: 0; padding: 0 0 0 6px; color: var(--acento-texto); font: inherit; text-decoration: underline; cursor: pointer; }
.err-desvincular { display: inline-flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-inline-start: 6px; color: var(--tinta); }
.err-desvincular .entrada { min-width: 220px; }
</style>
