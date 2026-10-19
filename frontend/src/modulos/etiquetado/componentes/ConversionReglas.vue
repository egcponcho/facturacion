<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { errorApi } from '@/stores/ui'

// Cómo quedaron las reglas de etiquetado anteriores al pasar a «qué diseño va en
// qué» (migración 0076): convertida o de baja y por qué, y lo que ya no aplica.
// Sale del historial que dejó la migración; si la empresa no tenía reglas, no se muestra.
const informe = ref(null)
onMounted(async () => {
  try {
    informe.value = await api.get('/etiquetas/usos/migracion')
  } catch (e) {
    if (e?.status !== 403) errorApi(e)
  }
})
const NIVELES = () => ({ GENERAL: t('Whole company'), FAMILIA: t('Labeling family'), PRODUCTO: t('Product'), SKU: t('Item'),
  TIPO_EMPAQUE: t('Package type') })
const filas = computed(() => (informe.value?.filas || []).map((x) => ({
  ...x, id: `${x.regla}-${x.uso_id}`, nivelTxt: NIVELES()[x.nivel] || x.nivel,
  por: x.motivo_baja ? tx(x.motivo_baja) : x.notas.map((n) => tx(n)).join(' '),
  estado: x.resultado === 'baja' ? 'BAJA' : (x.vigente ? 'VIGENTE' : 'RETIRADA'),
})))
const columnas = computed(() => [
  { clave: 'nombre', texto: t('Previous rule'), prioridad: 1 },
  { clave: 'estado', texto: t('Result'), prioridad: 1 },
  { clave: 'tipo', texto: t('Label type'), prioridad: 2 },
  { clave: 'plantilla', texto: t('Design'), prioridad: 2 },
  { clave: 'nivelTxt', texto: t('Where'), prioridad: 2 },
  { clave: 'por', texto: t('Why'), prioridad: 1, ordenable: false },
])
</script>

<template>
  <details v-if="filas.length" class="panel cr">
    <summary>
      <strong>{{ t('Conversion of the previous rules') }}</strong>
      <span class="ayuda"> · {{ t('{0} rules: {1} converted, {2} retired, {3} with notes', [informe.resumen.reglas, informe.resumen.convertidas,
                                                                                     informe.resumen.de_baja, informe.resumen.con_notas]) }}</span>
    </summary>
    <p class="ayuda">{{ t('When labeling moved to label types and «which design goes on what», each previous rule took its place (or became an exception). What no longer had a place was retired with its reason. Review the retired ones and the notes: nothing else changes what is printed.') }}</p>
    <TablaDatos tabla="etiquetas_conversion_reglas" :columnas="columnas" :filas="filas" :etiqueta="t('Conversion of the previous rules')">
      <template #celda-nombre="{ fila: x }">{{ x.nombre || `#${x.regla}` }} <span class="ayuda">({{ x.ambito }})</span></template>
      <template #celda-estado="{ fila: x }"><EstadoBadge :estado="x.estado" tipo="conversion_regla" /></template>
      <template #celda-plantilla="{ fila: x }">{{ x.plantilla ? tx(x.plantilla) : '—' }}</template>
      <template #celda-nivelTxt="{ fila: x }">{{ x.nivelTxt }}<span v-if="x.destino"> · {{ tx(x.destino) }}</span></template>
    </TablaDatos>
  </details>
</template>

<style scoped>
.cr { margin-bottom: 16px; }
.cr summary { cursor: pointer; }
.cr > p { margin: 8px 0; }
</style>
