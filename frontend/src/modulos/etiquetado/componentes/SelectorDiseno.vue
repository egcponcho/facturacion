<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Seleccion from '@/componentes/Seleccion.vue'
import { fmtNum } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'

// Elegir un diseño de un tipo de etiqueta: solo los diseños de ese tipo, con
// su miniatura y si tiene una versión aprobada (sin ella, solo imprime en prueba).
const props = defineProps({
  tipoId: { type: Number, required: true },
  modelValue: { type: [Number, String], default: '' },
  vacio: { type: String, default: '' }, // texto de la opción sin diseño (si se permite)
  etiqueta: { type: String, default: '' },
  miniatura: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])
const disenos = ref([])
async function cargar() {
  try {
    disenos.value = (await api.get('/etiquetas/plantillas', { tipo_etiqueta_id: props.tipoId, size: 200 })).items
  } catch (e) {
    errorApi(e)
  }
}
watch(() => props.tipoId, cargar, { immediate: true })
const elegido = computed(() => disenos.value.find((d) => d.id === Number(props.modelValue)) || null)
const medida = (d) => {
  const v = d.vigente || d.ultima
  return v ? `${fmtNum(v.ancho_mm, 1)} × ${fmtNum(v.alto_mm, 1)} mm` : ''
}
const imagen = (d) => (d.vigente || d.ultima ? `/api/etiquetas/versiones/${(d.vigente || d.ultima).id}/miniatura.svg?v=${encodeURIComponent(d.actualizada_en || '')}` : null)
defineExpose({ elegido, recargar: cargar })
</script>

<template>
  <div class="sd">
    <div class="sd-campo">
      <Seleccion :model-value="modelValue === null ? '' : modelValue" :aria-label="etiqueta || t('Design')"
                 @update:model-value="(v) => emit('update:modelValue', v === '' ? '' : Number(v))">
        <option v-if="vacio" value="">{{ vacio }}</option>
        <option v-else value="" disabled>{{ t('Choose a design…') }}</option>
        <option v-for="d in disenos" :key="d.id" :value="d.id">
          {{ tx(d.nombre) }} · {{ medida(d) }} · {{ d.vigente ? t('v{0} approved', [d.vigente.numero]) : t('not approved') }}</option>
      </Seleccion>
      <p v-if="elegido && !elegido.vigente" class="sd-aviso"><span class="etiqueta aviso ms-0">{{ t('Not approved yet') }}</span>
        {{ t('It prints only in test mode until a version is approved.') }}</p>
      <p v-if="!disenos.length" class="ayuda">{{ t('There are no designs of this label type yet.') }}
        <router-link to="/etiquetas/disenos" class="enlace">{{ t('Create one') }}</router-link></p>
    </div>
    <div v-if="miniatura && elegido && imagen(elegido)" class="sd-mini"><img :src="imagen(elegido)" :alt="t('Preview of {0}', [elegido.nombre])" /></div>
  </div>
</template>

<style scoped>
.sd { display: flex; gap: 12px; align-items: flex-start; }
.sd-campo { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.sd-aviso { margin: 0; font-size: 0.82rem; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.sd-mini { width: 112px; height: 84px; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 1px solid var(--linea); border-radius: 8px; padding: 6px;
  background: repeating-conic-gradient(var(--linea-suave) 0% 25%, var(--superficie-2) 0% 50%) 0 0 / 12px 12px; flex: none; }
.sd-mini img { max-width: 100%; max-height: 100%; object-fit: contain; background: #fff; box-shadow: 0 1px 3px rgb(0 0 0 / 18%); }
@media (max-width: 560px) { .sd-mini { display: none; } }
</style>
