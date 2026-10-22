<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import { errorApi } from '@/stores/ui'
import { fmtNum, textoVariante, unidadTxt } from '@/nucleo/utils'
import Icono from './Icono.vue'
import Modal from './Modal.vue'
import TablaDatos from './TablaDatos.vue'

// Explosión de un artículo prepack: qué sólidos y cuántos trae cada caja.
// Es de solo lectura: la explosión de un prepack nunca se modifica.
const props = defineProps({ sku: { type: String, required: true }, cajas: { type: Number, default: 0 } })
defineEmits(['cerrar'])
const e = ref(null)
const totalCajas = computed(() => (props.cajas || 0) * (e.value?.total || 0))
const columnas = computed(() => [
  { clave: 'sku', texto: t('Item code'), fija: true, prioridad: 1 },
  { clave: 'variante', texto: t('Variant'), valor: (x) => textoVariante(x), prioridad: 1 },
  { clave: 'unidad', texto: t('UoM'), prioridad: 3 },
  { clave: 'cantidad', texto: t('Per pack'), num: true, prioridad: 1 },
  ...(props.cajas ? [{ clave: 'total', texto: t('Total in {0} packs', [fmtNum(props.cajas)]), num: true, prioridad: 2, valor: (c) => c.cantidad * props.cajas }] : []),
])

onMounted(async () => {
  try {
    e.value = await api.get(`/catalogos/explosion/${props.sku}`)
  } catch (err) {
    errorApi(err)
  }
})
</script>

<template>
  <Modal :titulo="tx(e ? t('Contents of pack {0}', [e.codigo]) : t('Contents of the pack'))" ancho="640px" @cerrar="$emit('cerrar')">
    <template v-if="e">
      <div class="explosion-cabeza">
        <div><span class="ayuda">{{ t('Item code') }}</span><b class="codigo">{{ tx(e.sku) }}</b></div>
        <div v-if="e.estilo || e.color"><span class="ayuda">{{ t('Model · fixed color') }}</span><b>{{ [e.estilo, e.color].filter(Boolean).map(tx).join(' · ') }}</b></div>
        <div><span class="ayuda">{{ t('Pack ID') }}</span><b>{{ tx(e.codigo) }}</b></div>
        <div><span class="ayuda">{{ t('Unit of measure') }}</span><b>{{ tx(e.unidad) }}</b></div>
      </div>
      <TablaDatos tabla="prepack_explosion" :columnas="columnas" :filas="e.componentes" clave-fila="articulo_id" :vistas-guardadas="false" :etiqueta="t('Contents of the pack')">
        <template #celda-sku="{ fila: c }"><span class="codigo">{{ tx(c.sku) }}</span></template>
        <template #celda-variante="{ fila: c }"><b>{{ tx(textoVariante(c)) }}</b></template>
        <template #celda-unidad="{ fila: c }"><span class="etiqueta ms-0">{{ tx(c.unidad) }}</span></template>
        <template #celda-cantidad="{ fila: c }">{{ fmtNum(c.cantidad) }}</template>
        <template #celda-total="{ fila: c }"><span class="fuerte">{{ fmtNum(c.cantidad * cajas) }}</span></template>
        <template #pie-inicio>{{ t('Total') }}</template>
        <template #pie-cantidad>{{ fmtNum(e.total) }} {{ tx(unidadTxt(e.unidad_componentes, e.total)) }}</template>
        <template v-if="cajas" #pie-total>{{ fmtNum(totalCajas) }} {{ tx(unidadTxt(e.unidad_componentes, totalCajas)) }}</template>
      </TablaDatos>
      <p class="ayuda"><Icono nombre="candado" :tam="13" /> {{ t('The contents are fixed: for other contents, create a new pack with another code.') }}</p>
    </template>
    <p v-else class="ayuda">{{ t('Loading…') }}</p>
    <template #pie><button class="btn" @click="$emit('cerrar')">{{ t('Close') }}</button></template>
  </Modal>
</template>
