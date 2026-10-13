<script setup>
import { t } from '@/i18n/index.js'
import Icono from '@/componentes/Icono.vue'

// Pestañas del módulo de facturación y pagos
const ENLACES = [
  { to: '/comercial/documentos', texto: t('Documents'), icono: 'factura' },
  { to: '/comercial/pagos', texto: t('Collections and payments'), icono: 'moneda' },
  { to: '/comercial/terceros', texto: t('Business partners'), icono: 'usuarios' },
]
</script>

<template>
  <nav class="segmentos nav-comercial" :aria-label="t('Billing')">
    <router-link v-for="e in ENLACES" :key="e.to" :to="e.to" class="segmento" active-class="" exact-active-class=""
                 :aria-current="$route.path.startsWith(e.to) ? 'page' : undefined" :aria-pressed="$route.path.startsWith(e.to)">
      <Icono :nombre="e.icono" :tam="15" />{{ e.texto }}
    </router-link>
  </nav>
</template>

<style scoped>
.nav-comercial { margin-bottom: 14px; }
.nav-comercial .segmento { display: inline-flex; align-items: center; gap: 6px; text-decoration: none; }
</style>
