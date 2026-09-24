<script setup>
import { computed } from 'vue'

const props = defineProps({ page: Number, size: Number, total: Number })
const emit = defineEmits(['cambiar'])
const paginas = computed(() => Math.max(1, Math.ceil((props.total || 0) / props.size)))
</script>

<template>
  <div v-if="paginas > 1" class="fila-flex mt">
    <span class="ayuda">{{ props.total }} resultados, página {{ props.page }} de {{ paginas }}</span>
    <span class="separar"></span>
    <button class="btn btn-chico" :disabled="props.page <= 1" @click="emit('cambiar', props.page - 1)">Anterior</button>
    <button class="btn btn-chico" :disabled="props.page >= paginas" @click="emit('cambiar', props.page + 1)">Siguiente</button>
  </div>
</template>
