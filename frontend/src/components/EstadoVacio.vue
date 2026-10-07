<script setup>
import { tx } from '../i18n/index.js'
import Icono from './Icono.vue'

// Estado vacío que enseña: qué es esto, qué se necesita para que aparezca algo
// y la acción para empezar (slot). Para listas sin ningún registro todavía;
// cuando los filtros no encuentran nada basta el mensaje corto de siempre.
const props = defineProps({
  icono: { type: String, default: 'info' },
  titulo: { type: String, required: true },
  texto: { type: String, default: '' },
  requisitos: { type: Array, default: () => [] }, // textos «Para crear uno necesita…»
  tituloRequisitos: { type: String, default: '' },
})
</script>

<template>
  <div class="estado-vacio">
    <span class="estado-vacio-icono"><Icono :nombre="props.icono" :tam="24" /></span>
    <h3>{{ tx(props.titulo) }}</h3>
    <p v-if="props.texto">{{ tx(props.texto) }}</p>
    <template v-if="props.requisitos.length">
      <p v-if="props.tituloRequisitos" class="estado-vacio-sub">{{ tx(props.tituloRequisitos) }}</p>
      <ul><li v-for="r in props.requisitos" :key="r"><Icono nombre="check" :tam="14" />{{ tx(r) }}</li></ul>
    </template>
    <div v-if="$slots.default" class="fila-flex estado-vacio-acciones"><slot /></div>
  </div>
</template>

<style scoped>
.estado-vacio { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 8px; padding: 28px 16px; max-width: 560px; margin: 0 auto; white-space: normal; }
.estado-vacio h3 { margin: 4px 0 0; font-size: 1.05rem; }
.estado-vacio p { margin: 0; color: var(--tinta-3); line-height: 1.5; }
.estado-vacio-icono { width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); }
.estado-vacio-sub { font-weight: 600; color: inherit !important; margin-top: 6px !important; }
.estado-vacio ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; text-align: start; }
.estado-vacio li { display: flex; align-items: center; gap: 8px; color: var(--tinta-3); }
.estado-vacio li svg { color: var(--ok); }
.estado-vacio-acciones { justify-content: center; margin-top: 8px; }
</style>
