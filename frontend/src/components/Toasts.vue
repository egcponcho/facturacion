<script setup>
import { cerrarAviso, ui } from '../stores/ui'
</script>

<template>
  <div class="avisos" aria-live="polite">
    <div v-for="t in ui.toasts.slice(-3)" :key="t.id" class="aviso-toast" :class="t.tipo" role="status">
      <div>
        {{ t.mensaje }}
        <ul v-if="t.detalle?.length">
          <li v-for="(d, i) in t.detalle" :key="i">{{ d }}</li>
        </ul>
      </div>
      <button type="button" aria-label="Cerrar aviso" @click="cerrarAviso(t.id)">×</button>
    </div>
  </div>
</template>
