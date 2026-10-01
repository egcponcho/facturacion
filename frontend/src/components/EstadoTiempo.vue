<script setup>
import { t } from '../i18n/index.js'
import { computed } from 'vue'
import { TIEMPO } from '../utils'

// En tiempo / en riesgo / atrasado frente a la fecha requerida en tienda, con
// los días de holgura; sin fechas suficientes se muestra como pendiente
const props = defineProps({ estado: { type: String, default: null }, holgura: { type: Number, default: null } })
const info = computed(() => TIEMPO[props.estado] || [t('No date yet'), 'neutro'])
const detalle = computed(() => (props.holgura === null || props.holgura === undefined ? t('Missing the in-store date or the logistics dates')
  : props.holgura < 0 ? t('{0} d late for the store', [-props.holgura]) : t('{0} d margin', [props.holgura])))
</script>

<template>
  <span class="etiqueta" :class="info[1]" style="margin-inline-start: 0" :title="detalle">{{ info[0] }}<template v-if="props.holgura !== null && props.holgura !== undefined"> · {{ props.holgura < 0 ? `+${-props.holgura}` : props.holgura }} d</template></span>
</template>
