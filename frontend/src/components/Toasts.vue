<script setup>
import { cerrarAviso, ui } from '../stores/ui'
import Icono from './Icono.vue'
</script>

<template>
  <div class="avisos" aria-live="polite">
    <div v-for="t in ui.toasts.slice(-3)" :key="t.id" class="aviso-toast" :class="t.tipo" role="status">
      <Icono :nombre="t.tipo === 'error' ? 'alerta' : 'check'" :tam="18" />
      <div>
        {{ t.mensaje }}
        <ul v-if="t.detalle?.length">
          <li v-for="(d, i) in t.detalle" :key="i">{{ d }}</li>
        </ul>
      </div>
      <button type="button" aria-label="Cerrar aviso" @click="cerrarAviso(t.id)"><Icono nombre="cerrar" :tam="16" /></button>
    </div>
  </div>
</template>
