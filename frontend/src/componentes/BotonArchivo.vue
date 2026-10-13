<script setup>
import { ref } from 'vue'

// Botón que abre el selector de archivos (subir un logo, una foto, un paquete):
// el contenido del botón va en la ranura y su aspecto en `class` (por defecto
// un botón chico). Emite `elegir` con el File; elegir el mismo archivo otra vez
// vuelve a avisar.
defineOptions({ inheritAttrs: false })
const props = defineProps({
  acepta: { type: String, default: '' },
  deshabilitado: Boolean,
  etiqueta: { type: String, default: '' },
})
const emit = defineEmits(['elegir'])
const entrada = ref(null)
function cambio(e) {
  const archivo = e.target.files?.[0]
  if (archivo) emit('elegir', archivo)
  e.target.value = ''
}
defineExpose({ abrir: () => entrada.value?.click() })
</script>

<template>
  <label :class="$attrs.class || 'btn btn-chico'" :style="$attrs.style" :title="$attrs.title" class="boton-archivo" :aria-disabled="props.deshabilitado || undefined">
    <slot />
    <input ref="entrada" type="file" :accept="props.acepta" class="oculto-visual" :disabled="props.deshabilitado"
           :aria-label="props.etiqueta || $attrs['aria-label']" @change="cambio" />
  </label>
</template>
