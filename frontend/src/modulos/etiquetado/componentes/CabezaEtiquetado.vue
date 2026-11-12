<script setup>
// Cabecera común de las páginas del etiquetado. Sus apartados (Imprimir,
// Diseños y Configuración) van en la barra del módulo (nucleo/modulos.js).
defineProps({ titulo: { type: String, required: true }, texto: { type: String, default: '' } })
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ titulo }}</h1>
      <p v-if="texto">{{ texto }}</p>
    </div>
    <div class="acciones"><slot /></div>
  </div>
</template>
