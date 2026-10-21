<script setup>
import { tx } from '@/i18n/index.js'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Icono from '@/componentes/Icono.vue'
import { esDe } from '@/nucleo/modulos.js'

// Barra del módulo (como en el ERP): sus apartados en pestañas y, a la derecha,
// la acción principal del módulo. Solo aparece si el módulo tiene más de un
// apartado o una acción principal; en el lienzo de diseño no se muestra.
const props = defineProps({ modulo: { type: Object, required: true } })
const route = useRoute()
const actual = computed(() => props.modulo.apartados.find((x) => esDe(x, route)))
const mostrarAccion = computed(() => props.modulo.accion && !esDe({ prefijos: [props.modulo.accion.a] }, route))
</script>

<template>
  <div v-if="modulo.apartados.length > 1 || modulo.accion" class="modulo-barra">
    <nav class="pestanas" :aria-label="tx(modulo.texto)">
      <router-link v-for="x in modulo.apartados" :key="x.a" :to="x.a" class="pestana"
                   :aria-current="actual === x ? (route.fullPath === x.a ? 'page' : 'true') : undefined">{{ tx(x.texto) }}</router-link>
    </nav>
    <div v-if="mostrarAccion" class="modulo-barra-accion">
      <router-link class="btn btn-primario" :to="modulo.accion.a"><Icono nombre="mas" :tam="16" />{{ tx(modulo.accion.texto) }}</router-link>
    </div>
  </div>
</template>
