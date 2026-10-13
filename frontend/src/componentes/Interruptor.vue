<script setup>
// Interruptor accesible (role="switch") para valores sí/no.
defineProps({ modelValue: Boolean, etiqueta: { type: String, default: '' }, deshabilitado: Boolean })
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <button type="button" role="switch" class="interruptor" :aria-checked="modelValue" :aria-label="etiqueta" :title="etiqueta"
          :disabled="deshabilitado" @click="emit('update:modelValue', !modelValue)"><span></span></button>
</template>

<style scoped>
.interruptor { width: 34px; height: 20px; border-radius: 99px; border: 0; padding: 2px; background: var(--linea); cursor: pointer; display: inline-flex; transition: background 0.15s; flex: none; }
.interruptor span { width: 16px; height: 16px; border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgb(0 0 0 / 25%); transition: transform 0.15s; }
.interruptor[aria-checked='true'] { background: var(--acento); }
.interruptor[aria-checked='true'] span { transform: translateX(14px); }
[dir='rtl'] .interruptor[aria-checked='true'] span { transform: translateX(-14px); }
.interruptor:disabled { opacity: 0.5; cursor: not-allowed; }
.interruptor:focus-visible { outline: 2px solid var(--acento); outline-offset: 2px; }
</style>
