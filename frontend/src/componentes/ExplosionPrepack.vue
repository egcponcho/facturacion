<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import { errorApi } from '@/stores/ui'
import { fmtNum, unidadTxt } from '@/nucleo/utils'
import Icono from './Icono.vue'
import Modal from './Modal.vue'

// Explosión de un artículo prepack: qué sólidos y cuántos trae cada caja.
// Es de solo lectura: la explosión de un prepack nunca se modifica.
const props = defineProps({ sku: { type: String, required: true }, cajas: { type: Number, default: 0 } })
defineEmits(['cerrar'])
const e = ref(null)
const totalCajas = computed(() => (props.cajas || 0) * (e.value?.total || 0))

onMounted(async () => {
  try {
    e.value = await api.get(`/catalogos/explosion/${props.sku}`)
  } catch (err) {
    errorApi(err)
  }
})
</script>

<template>
  <Modal :titulo="tx(e ? t('Prepack breakdown {0}', [e.codigo]) : t('Prepack breakdown'))" ancho="640px" @cerrar="$emit('cerrar')">
    <template v-if="e">
      <div class="explosion-cabeza">
        <div><span class="ayuda">{{ t('Item code') }}</span><b class="codigo">{{ tx(e.sku) }}</b></div>
        <div><span class="ayuda">{{ t('Style · color') }}</span><b>{{ tx(e.estilo) }} · {{ tx(e.color) }}</b></div>
        <div><span class="ayuda">{{ t('Prepack ID (size)') }}</span><b>{{ tx(e.codigo) }}</b></div>
        <div><span class="ayuda">{{ t('Unit of measure') }}</span><b>{{ t('CJ · prepack carton') }}</b></div>
      </div>
      <div class="tabla-marco" style="box-shadow: none">
        <table class="tabla" v-tarjetas>
          <thead>
            <tr>
              <th>{{ t('Solid SKU') }}</th><th>{{ t('Size') }}</th><th>{{ t('UoM') }}</th><th class="num">{{ t('Per carton') }}</th>
              <th v-if="cajas" class="num">{{ t('Total in {0} cartons', [fmtNum(cajas)]) }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in e.componentes" :key="c.articulo_id">
              <td class="codigo">{{ tx(c.sku) }}</td>
              <td><b>{{ tx(c.talla) }}</b></td>
              <td><span class="etiqueta" style="margin-inline-start: 0">{{ tx(c.unidad) }}</span></td>
              <td class="num">{{ fmtNum(c.cantidad) }}</td>
              <td v-if="cajas" class="num fuerte">{{ fmtNum(c.cantidad * cajas) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="3">{{ t('Total') }}</td>
              <td class="num">{{ fmtNum(e.total) }} {{ tx(unidadTxt(e.unidad_componentes, e.total)) }}</td>
              <td v-if="cajas" class="num">{{ fmtNum(totalCajas) }} {{ tx(unidadTxt(e.unidad_componentes, totalCajas)) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p class="ayuda"><Icono nombre="candado" :tam="13" /> {{ t('The breakdown is fixed: for another size run, create a new prepack with another code.') }}</p>
    </template>
    <p v-else class="ayuda">{{ t('Loading…') }}</p>
    <template #pie><button class="btn" @click="$emit('cerrar')">{{ t('Close') }}</button></template>
  </Modal>
</template>
