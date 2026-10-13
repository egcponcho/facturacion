<script setup>
import { provide } from 'vue'

// Bloque del detalle de una fila (TablaDatos): sangría y guía a la izquierda
// para que se lea como contenido de la fila de arriba. Una TablaDatos que va
// dentro se dibuja como tabla anidada (compacta, sin barra repetida).
provide('tablaAnidada', true)
</script>

<template>
  <div class="detalle-anidado"><slot /></div>
</template>
