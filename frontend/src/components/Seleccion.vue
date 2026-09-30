<script setup>
import { computed, useAttrs, useSlots } from 'vue'
import SelectBusqueda from './SelectBusqueda.vue'

// Reemplazo directo del select nativo: toma las <option> escritas dentro y las
// muestra con la lista con búsqueda del sistema. La opción sin valor ("…: all",
// "Choose…") es el texto vacío. change emite el valor elegido.
defineOptions({ inheritAttrs: false })
const props = defineProps({
  modelValue: { type: [String, Number, Boolean], default: undefined },
  value: { type: [String, Number, Boolean], default: undefined }, // como :value del select nativo (sin v-model)
  disabled: Boolean,
  required: Boolean,
  etiqueta: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'change'])
const slots = useSlots()
const attrs = useAttrs()

function texto(hijos) {
  if (hijos == null) return ''
  if (typeof hijos === 'string' || typeof hijos === 'number') return String(hijos)
  if (Array.isArray(hijos)) return hijos.map((h) => texto(typeof h === 'object' && h ? h.children : h)).join('')
  return ''
}
function recorrer(nodos, out) {
  for (const n of nodos || []) {
    if (!n || typeof n !== 'object') continue
    if (n.type === 'option') {
      const v = n.props && 'value' in n.props ? n.props.value : texto(n.children)
      out.push({ valor: v ?? '', texto: texto(n.children).trim(), deshabilitada: n.props?.disabled })
    } else if (Array.isArray(n.children)) recorrer(n.children, out)
  }
  return out
}
const todas = computed(() => recorrer(slots.default?.() || [], []))
const vacia = computed(() => todas.value.find((o) => o.valor === '' || o.valor === null))
// Filtros cuyas opciones repiten la etiqueta ("Stage: all", "Stage: In transit"):
// la lista muestra solo el valor y el botón "Stage: valor"
const prefijoComun = computed(() => {
  const m = (vacia.value?.texto || '').match(/^(.{2,30}?):\s/)
  const resto = todas.value.filter((o) => o !== vacia.value)
  return m && resto.length && resto.every((o) => o.texto.startsWith(`${m[1]}: `)) ? m[1] : ''
})
const opciones = computed(() => todas.value.filter((o) => o !== vacia.value && !o.deshabilitada)
  .map((o) => (prefijoComun.value ? { ...o, texto: o.texto.slice(prefijoComun.value.length + 2) } : o)))
const valor = computed(() => props.modelValue ?? props.value ?? '')
const clase = computed(() => String(attrs.class || '').split(/\s+/).filter((c) => c && !['entrada', 'celda'].includes(c)).join(' '))
const etq = computed(() => props.etiqueta || attrs['aria-label'] || '')

function cambiar(v) {
  emit('update:modelValue', v)
  emit('change', v)
}
</script>

<template>
  <SelectBusqueda :class="clase" :style="attrs.style" :boton-id="attrs.id" :model-value="valor" :opciones="opciones" :vacio="vacia?.texto || ''"
                  :placeholder="vacia?.texto || 'Choose…'"   :etiqueta="prefijoComun || etq" :prefijo="!!prefijoComun" :deshabilitado="disabled" :requerido="required"
                  @update:model-value="cambiar" />
</template>
