<script setup>
import { t, tx } from '../i18n/index.js'
const props = defineProps({ estado: { type: String, default: '' } })
const MAPA = {
  BORRADOR: [t('Draft'), 'neutro'],
  EN_CORRECCION: [t('In correction'), 'aviso'],
  FINALIZADA: [t('Finalized'), 'ok'],
  FINALIZADO: [t('Finalized'), 'ok'],
  CANCELADA: [t('Cancelled'), 'error'],
  CANCELADO: [t('Cancelled'), 'error'],
  DISPONIBLE: [t('Available'), 'ok'],
  PARCIAL: [t('Partial'), 'aviso'],
  FACTURADA: [t('Invoiced'), 'neutro'],
  NO_DISPONIBLE: [t('Not available'), 'error'],
  SIN_CAJA: [t('Not packed'), 'error'],
  COMPLETO: [t('Packed'), 'ok'],
  TENTATIVA: [t('Tentative'), 'aviso'],
  CONFIRMADA: [t('Confirmed'), 'ok'],
  PLANIFICADO: [t('Planned'), 'neutro'],
  EN_TRANSITO: [t('In transit'), 'info'],
  ARRIBADO: [t('Arrived'), 'info'],
  ENTREGADO: [t('Delivered'), 'ok'],
  RECIBIDO: [t('Received'), 'ok'],
  // Liberación de la OC (estados universales)
  RELEASED: [t('Released'), 'ok'],
  PENDING: [t('Not released'), 'aviso'],
  // Ficha técnica y clasificación del producto
  borrador: [t('Draft'), 'neutro'],
  sugerida: [t('Draft · complete'), 'neutro'],
  revision: [t('In review'), 'info'],
  aprobado: [t('Approved'), 'ok'],
  corregido: [t('Approved'), 'ok'],
  observado: [t('Returned'), 'aviso'],
}
</script>

<template>
  <span class="estado" :class="`estado-${MAPA[props.estado]?.[1] || 'neutro'}`">
    <span class="estado-marca" aria-hidden="true"></span>{{ tx(MAPA[props.estado]?.[0] || props.estado) }}
  </span>
</template>
