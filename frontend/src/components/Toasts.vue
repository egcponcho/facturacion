<script setup>
import { cerrarAviso, ui } from '../stores/ui'
import Icono from './Icono.vue'

// Avisos flotantes: título por tipo, mensaje y detalle; los errores se quedan
// hasta cerrarlos si traen detalle.
const TITULO = { ok: 'Done', error: 'Could not complete', aviso: 'Check this', info: 'Note' }
const ICONO = { ok: 'check', error: 'alerta', aviso: 'alerta', info: 'info' }
</script>

<template>
  <div class="avisos" aria-live="polite">
    <div v-for="t in ui.toasts.slice(-3)" :key="t.id" class="aviso-toast" :class="t.tipo" :role="t.tipo === 'error' ? 'alert' : 'status'">
      <span class="aviso-icono"><Icono :nombre="ICONO[t.tipo] || 'info'" :tam="16" /></span>
      <div class="aviso-cuerpo">
        <b>{{ TITULO[t.tipo] || 'Note' }}</b>
        <span>{{ t.mensaje }}</span>
        <ul v-if="t.detalle?.length">
          <li v-for="(d, i) in t.detalle.slice(0, 6)" :key="i">{{ d }}</li>
          <li v-if="t.detalle.length > 6">and {{ t.detalle.length - 6 }} more</li>
        </ul>
      </div>
      <button type="button" aria-label="Close notice" @click="cerrarAviso(t.id)"><Icono nombre="cerrar" :tam="16" /></button>
    </div>
  </div>
</template>
