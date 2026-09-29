<script setup>
import Icono from './Icono.vue'

// Etapas de un documento. estado: hecho | actual | alerta | pendiente
const props = defineProps({ pasos: { type: Array, required: true } })
</script>

<template>
  <ol class="pasos" aria-label="Progress">
    <li v-for="(p, i) in props.pasos" :key="p.titulo" class="paso" :class="p.estado" :aria-current="p.estado === 'actual' ? 'step' : undefined">
      <div class="paso-cabeza">
        <span class="paso-marca">
          <Icono v-if="p.estado === 'hecho'" nombre="check" :tam="15" />
          <Icono v-else-if="p.estado === 'alerta'" nombre="alerta" :tam="14" />
          <template v-else>{{ i + 1 }}</template>
        </span>
        <span class="paso-linea" aria-hidden="true"></span>
      </div>
      <div class="paso-texto">
        <div class="paso-titulo">{{ p.titulo }}<span class="oculto-visual"> ({{ { hecho: 'done', actual: 'in progress', alerta: 'needs attention', pendiente: 'pending' }[p.estado] }})</span></div>
        <div v-if="p.detalle" class="paso-detalle">{{ p.detalle }}</div>
        <slot :name="`paso-${i}`" />
      </div>
    </li>
  </ol>
</template>
