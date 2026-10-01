<script setup>
import { t, tx } from '../i18n/index.js'
import { cerrarAviso, ui } from '../stores/ui'
import Icono from './Icono.vue'

// Avisos flotantes: título por tipo, mensaje y detalle; los errores se quedan
// hasta cerrarlos si traen detalle.
const TITULO = { ok: t('Done'), error: t('Could not complete'), aviso: t('Check this'), info: t('Note') }
const ICONO = { ok: 'check', error: 'alerta', aviso: 'alerta', info: 'info' }
</script>

<template>
  <div class="avisos" aria-live="polite">
    <div v-for="txt in ui.toasts.slice(-3)" :key="txt.id" class="aviso-toast" :class="txt.tipo" :role="txt.tipo === 'error' ? 'alert' : 'status'">
      <span class="aviso-icono"><Icono :nombre="ICONO[txt.tipo] || 'info'" :tam="16" /></span>
      <div class="aviso-cuerpo">
        <b>{{ tx(TITULO[txt.tipo] || t('Note')) }}</b>
        <span>{{ tx(txt.mensaje) }}</span>
        <ul v-if="txt.detalle?.length">
          <li v-for="(d, i) in txt.detalle.slice(0, 6)" :key="i">{{ tx(d) }}</li>
          <li v-if="txt.detalle.length > 6">{{ t('and {0} more', [txt.detalle.length - 6]) }}</li>
        </ul>
      </div>
      <button type="button" :aria-label="t('Close notice')" @click="cerrarAviso(txt.id)"><Icono nombre="cerrar" :tam="16" /></button>
    </div>
  </div>
</template>
