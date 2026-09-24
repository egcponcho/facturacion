<script setup>
const props = defineProps({ estado: { type: String, default: '' } })
const MAPA = {
  BORRADOR: ['Borrador', 'neutro'],
  EN_CORRECCION: ['En corrección', 'aviso'],
  FINALIZADA: ['Finalizada', 'ok'],
  FINALIZADO: ['Finalizado', 'ok'],
  CANCELADA: ['Cancelada', 'error'],
  CANCELADO: ['Cancelado', 'error'],
  DISPONIBLE: ['Disponible', 'ok'],
  PARCIAL: ['Parcial', 'aviso'],
  FACTURADA: ['Facturada', 'neutro'],
  NO_DISPONIBLE: ['No disponible', 'error'],
  SIN_CAJA: ['Sin caja', 'error'],
  COMPLETO: ['En cajas', 'ok'],
  TENTATIVA: ['Tentativa', 'aviso'],
  CONFIRMADA: ['Confirmada', 'ok'],
  PLANIFICADO: ['Planificado', 'neutro'],
  EN_TRANSITO: ['En tránsito', 'info'],
  ARRIBADO: ['Arribado', 'info'],
  ENTREGADO: ['Entregado', 'ok'],
  RECIBIDO: ['Recibido', 'ok'],
}
</script>

<template>
  <span class="estado" :class="`estado-${MAPA[props.estado]?.[1] || 'neutro'}`">
    <span class="estado-marca" aria-hidden="true"></span>{{ MAPA[props.estado]?.[0] || props.estado }}
  </span>
</template>
