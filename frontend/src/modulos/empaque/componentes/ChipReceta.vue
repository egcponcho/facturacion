<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { avisar, errorApi } from '@/stores/ui'

// La receta de empaque de una línea de OC: nombre, de dónde salió (a mano, por
// una regla o del casepack de la OC) y si la cantidad no completa cajas. Con
// permiso se cambia en el mismo lugar o se devuelve a las reglas.
const props = defineProps({
  posicion: { type: Object, required: true }, // la línea de /ordenes/{id}/posiciones, con su `receta`
  ocId: { type: Number, required: true },
  editable: { type: Boolean, default: false },
})
const emit = defineEmits(['cambiada'])
const ORIGEN = { MANUAL: () => t('chosen'), REGLA: () => t('by rule'), DATOS: () => t('from PO') }
const abierto = ref(false)
const recetas = ref([])
const elegida = ref('')
function abrir() {
  const r = props.posicion.receta
  elegida.value = r?.origen === 'MANUAL' ? String(r.receta_id) : ''
  abierto.value = true
  if (!recetas.value.length) api.get('/recetas-empaque').then((x) => (recetas.value = x)).catch(errorApi)
}
async function guardar() {
  try {
    await api.put(`/ordenes/${props.ocId}/posiciones/${props.posicion.id}/receta`, { receta_id: Number(elegida.value) || null })
    avisar(t('Line {0}: packing updated.', [props.posicion.posicion]))
    abierto.value = false
    emit('cambiada')
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <span class="chip-receta-celda">
    <template v-if="posicion.receta?.receta_id">
      <span class="etiqueta info ms-0 chip" :title="tx(posicion.receta.resumen)"><Icono nombre="caja" :tam="12" />{{ tx(posicion.receta.receta) }}
        <small>· {{ ORIGEN[posicion.receta.origen]?.() }}</small></span>
      <span v-if="posicion.receta.aviso" class="etiqueta aviso ms-0">{{ tx(posicion.receta.aviso) }}</span>
    </template>
    <span v-else class="ayuda">{{ t('No recipe') }}</span>
    <button v-if="editable" type="button" class="btn-icono" :aria-label="t('Change the packing recipe of line {0}', [posicion.posicion])"
            :title="t('Change the packing recipe')" @click="abrir"><Icono nombre="editar" :tam="14" /></button>
  </span>
  <Modal v-if="abierto" :titulo="t('Packing of line {0}', [posicion.posicion])" ancho="520px" @cerrar="abierto = false">
    <form :id="`form-receta-${posicion.id}`" class="form-receta" @submit.prevent="guardar">
      <label class="campo"><span>{{ t('Packing recipe') }}</span>
        <Seleccion v-model="elegida">
          <option value="">{{ t('According to the rules') }}</option>
          <option v-for="r in recetas" :key="r.id" :value="String(r.id)">{{ tx(r.nombre) }} · {{ tx(r.resumen) }}</option>
        </Seleccion>
      </label>
      <p v-if="posicion.receta?.receta_id" class="ayuda mt-0">{{ t('Now: {0} ({1}).', [tx(posicion.receta.resumen), ORIGEN[posicion.receta.origen]?.()]) }}</p>
      <p class="ayuda">{{ t('The line keeps a copy of the recipe levels: changing the recipe later does not change this line.') }}</p>
    </form>
    <template #pie>
      <button class="btn" type="button" @click="abierto = false">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" :form="`form-receta-${posicion.id}`">{{ t('Save packing') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.chip-receta-celda { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.chip { display: inline-flex; align-items: center; gap: 4px; }
.chip small { opacity: 0.8; }
.form-receta { display: flex; flex-direction: column; gap: 8px; }
</style>
