<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { errorApi } from '../stores/ui'
import { fmtNum, unidadTxt } from '../utils'
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
  <Modal :titulo="e ? `Prepack breakdown ${e.codigo}` : 'Prepack breakdown'" ancho="640px" @cerrar="$emit('cerrar')">
    <template v-if="e">
      <div class="explosion-cabeza">
        <div><span class="ayuda">Item code</span><b class="codigo">{{ e.sku }}</b></div>
        <div><span class="ayuda">Style · color</span><b>{{ e.estilo }} · {{ e.color }}</b></div>
        <div><span class="ayuda">Prepack ID (size)</span><b>{{ e.codigo }}</b></div>
        <div><span class="ayuda">Unit of measure</span><b>CJ · prepack carton</b></div>
      </div>
      <div class="tabla-marco" style="box-shadow: none">
        <table class="tabla">
          <thead>
            <tr>
              <th>Solid SKU</th><th>Size</th><th>UoM</th><th class="num">Per carton</th>
              <th v-if="cajas" class="num">Total in {{ fmtNum(cajas) }} cartons</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in e.componentes" :key="c.articulo_id">
              <td class="codigo">{{ c.sku }}</td>
              <td><b>{{ c.talla }}</b></td>
              <td><span class="etiqueta" style="margin-left: 0">{{ c.unidad }}</span></td>
              <td class="num">{{ fmtNum(c.cantidad) }}</td>
              <td v-if="cajas" class="num fuerte">{{ fmtNum(c.cantidad * cajas) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="3">Total</td>
              <td class="num">{{ fmtNum(e.total) }} {{ unidadTxt(e.unidad_componentes, e.total) }}</td>
              <td v-if="cajas" class="num">{{ fmtNum(totalCajas) }} {{ unidadTxt(e.unidad_componentes, totalCajas) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p class="ayuda"><Icono nombre="candado" :tam="13" /> The breakdown is fixed: for another size run, create a new prepack with another code.</p>
    </template>
    <p v-else class="ayuda">Loading…</p>
    <template #pie><button class="btn" @click="$emit('cerrar')">Close</button></template>
  </Modal>
</template>
