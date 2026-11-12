<script setup>
import { computed } from 'vue'
import { t, tx } from '@/i18n/index.js'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'

// El valor de un atributo (de producto o de variante) con la entrada que pide su
// tipo: texto, número, una de sus opciones, fecha, sí/no o un registro de un
// catálogo (la marca: las del proveedor elegido, si hay uno).
const props = defineProps({
  atributo: { type: Object, required: true }, // { codigo, nombre, tipo, opciones, catalogo, unidad }
  modelValue: { type: [String, Number], default: '' },
  marcas: { type: Array, default: () => [] }, // opciones del catálogo de marcas ({ codigo, texto })
  requerido: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])
const valor = computed({ get: () => props.modelValue ?? '', set: (v) => emit('update:modelValue', v ?? '') })
const opciones = computed(() => (Array.isArray(props.atributo.opciones) ? props.atributo.opciones
  : String(props.atributo.opciones || '').split(',').map((x) => x.trim()).filter(Boolean)))
const nombre = computed(() => tx(props.atributo.nombre))
</script>

<template>
  <SelectBusqueda v-if="atributo.tipo === 'catalogo'" v-model="valor" :opciones="marcas.map((m) => ({ valor: m.codigo, texto: m.texto }))"
                  :vacio="requerido ? '' : t('None')" :requerido="requerido" :etiqueta="nombre" :prefijo="false" />
  <Seleccion v-else-if="atributo.tipo === 'opcion' || atributo.tipo === 'bool'" v-model="valor" class="entrada" :required="requerido" :aria-label="nombre">
    <option value="">{{ requerido ? t('Choose…') : t('None') }}</option>
    <template v-if="atributo.tipo === 'bool'"><option value="true">{{ t('Yes') }}</option><option value="false">{{ t('No') }}</option></template>
    <option v-for="o in opciones" v-else :key="o" :value="o">{{ tx(o) }}</option>
  </Seleccion>
  <input v-else v-model="valor" class="entrada" :type="atributo.tipo === 'numero' ? 'number' : atributo.tipo === 'fecha' ? 'date' : 'text'"
         :step="atributo.tipo === 'numero' ? 'any' : undefined" maxlength="200" :required="requerido" :aria-label="nombre"
         :placeholder="atributo.unidad ? atributo.unidad : ''" />
</template>
