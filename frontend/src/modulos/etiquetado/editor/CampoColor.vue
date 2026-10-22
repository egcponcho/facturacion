<script setup>
import { t } from '@/i18n/index.js'

// Color (#rrggbb) con selector y texto; con `ninguno`, se puede dejar sin color.
const props = defineProps({
  modelValue: { type: String, default: null },
  etiqueta: { type: String, required: true },
  ninguno: Boolean,
  disabled: Boolean,
})
const emit = defineEmits(['update:modelValue'])
function escribir(ev) {
  const v = ev.target.value.trim()
  if (/^#[0-9a-fA-F]{6}$/.test(v)) emit('update:modelValue', v.toLowerCase())
}
</script>

<template>
  <div class="campo-color">
    <span class="medida-etq">{{ props.etiqueta }}</span>
    <div class="cc-fila">
      <input type="color" :value="props.modelValue || '#ffffff'" :disabled="props.disabled" :aria-label="props.etiqueta"
             :class="{ sin: !props.modelValue }" @input="emit('update:modelValue', $event.target.value)" />
      <input type="text" class="cc-hex" :value="props.modelValue || ''" :placeholder="t('None')" maxlength="7" :disabled="props.disabled"
             :aria-label="props.etiqueta" @change="escribir" />
      <button v-if="props.ninguno && props.modelValue" type="button" class="btn btn-icono btn-chico" :disabled="props.disabled" :title="t('No color')"
              :aria-label="t('No color')" @click="emit('update:modelValue', null)">×</button>
    </div>
  </div>
</template>

<style scoped>
.campo-color { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.medida-etq { font-size: var(--t-2xs); color: var(--tinta-3); }
.cc-fila { display: flex; gap: 4px; align-items: center; }
.cc-fila input[type='color'] { width: 34px; height: 32px; padding: 2px; border: 1px solid var(--linea); border-radius: 6px; background: var(--superficie); flex: none; }
.cc-fila input[type='color'].sin { background: repeating-linear-gradient(45deg, #fff 0 4px, #e5e7eb 4px 8px); }
.cc-hex { width: 100%; min-width: 0; font-family: ui-monospace, monospace; font-size: var(--t-xs); }
</style>
