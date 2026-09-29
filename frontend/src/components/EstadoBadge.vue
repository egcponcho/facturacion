<script setup>
const props = defineProps({ estado: { type: String, default: '' } })
const MAPA = {
  BORRADOR: ['Draft', 'neutro'],
  EN_CORRECCION: ['In correction', 'aviso'],
  FINALIZADA: ['Finalized', 'ok'],
  FINALIZADO: ['Finalized', 'ok'],
  CANCELADA: ['Cancelled', 'error'],
  CANCELADO: ['Cancelled', 'error'],
  DISPONIBLE: ['Available', 'ok'],
  PARCIAL: ['Partial', 'aviso'],
  FACTURADA: ['Invoiced', 'neutro'],
  NO_DISPONIBLE: ['Not available', 'error'],
  SIN_CAJA: ['Not packed', 'error'],
  COMPLETO: ['Packed', 'ok'],
  TENTATIVA: ['Tentative', 'aviso'],
  CONFIRMADA: ['Confirmed', 'ok'],
  PLANIFICADO: ['Planned', 'neutro'],
  EN_TRANSITO: ['In transit', 'info'],
  ARRIBADO: ['Arrived', 'info'],
  ENTREGADO: ['Delivered', 'ok'],
  RECIBIDO: ['Received', 'ok'],
}
</script>

<template>
  <span class="estado" :class="`estado-${MAPA[props.estado]?.[1] || 'neutro'}`">
    <span class="estado-marca" aria-hidden="true"></span>{{ MAPA[props.estado]?.[0] || props.estado }}
  </span>
</template>
