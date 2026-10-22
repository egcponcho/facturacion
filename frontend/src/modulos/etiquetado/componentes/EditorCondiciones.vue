<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { LISTAS, NUMERICOS, OPERADORES, SIN_VALOR } from '@/modulos/etiquetado/etiquetas.js'

// Condiciones sobre los datos (campo, operador, valor); todas deben cumplirse.
// Se usa en las excepciones «Avanzado» y en las categorías de una familia.
const props = defineProps({
  modelValue: { type: Array, required: true }, // se edita en el lugar
  campos: { type: Array, default: () => [] },
  operadores: { type: Array, default: () => [] }, // operadores simples del servidor
  titulo: { type: String, default: '' },
  editable: { type: Boolean, default: true },
})
const lista = props.modelValue
const ops = computed(() => {
  const todos = OPERADORES()
  return (props.operadores.length ? props.operadores : Object.keys(todos)).map((op) => [op, todos[op] || op])
})
const agregar = () => lista.push({ campo: '', op: 'igual', valor: '' })
</script>

<template>
  <fieldset class="condiciones">
    <legend>{{ titulo || t('Conditions (all must be met)') }}</legend>
    <div v-for="(c, i) in lista" :key="i" class="condicion">
      <Seleccion v-model="c.campo" :aria-label="t('Field')" :disabled="!editable"><option value="">{{ t('Field…') }}</option>
        <option v-for="f in campos" :key="f.clave" :value="f.clave">{{ tx(f.etiqueta) }}</option></Seleccion>
      <Seleccion v-model="c.op" :aria-label="t('Operator')" :disabled="!editable"><option v-for="[op, txt] in ops" :key="op" :value="op">{{ txt }}</option></Seleccion>
      <input v-if="!SIN_VALOR.includes(c.op)" v-model="c.valor" :type="NUMERICOS.includes(c.op) ? 'number' : 'text'" :aria-label="t('Value')"
             :placeholder="LISTAS.includes(c.op) ? t('values separated by commas') : ''" :disabled="!editable" />
      <span v-else />
      <button v-if="editable" type="button" class="btn-icono" :aria-label="t('Remove')" @click="lista.splice(i, 1)"><Icono nombre="cerrar" :tam="14" /></button>
    </div>
    <button v-if="editable" type="button" class="btn btn-chico" @click="agregar"><Icono nombre="mas" :tam="14" />{{ t('Add a condition') }}</button>
  </fieldset>
</template>

<style scoped>
.condiciones { border: 1px dashed var(--linea); border-radius: 8px; padding: 8px; display: flex; flex-direction: column; gap: 6px; margin: 0; }
.condiciones legend { font-size: var(--t-sm); padding: 0 4px; }
.condiciones > .btn { align-self: flex-start; }
.condicion { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1.4fr) minmax(0, 1.4fr) auto; gap: 6px; align-items: center; }
@media (max-width: 600px) { .condicion { grid-template-columns: 1fr auto; } }
</style>
