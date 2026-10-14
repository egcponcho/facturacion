<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icono from '@/componentes/Icono.vue'
import { puede } from '@/stores/sesion'
import ListaPlantillas from '@/modulos/etiquetado/componentes/ListaPlantillas.vue'
import FamiliasEtiquetado from '@/modulos/etiquetado/componentes/FamiliasEtiquetado.vue'
import ArticulosFamilia from '@/modulos/etiquetado/componentes/ArticulosFamilia.vue'
import AsignacionesEtiqueta from '@/modulos/etiquetado/componentes/AsignacionesEtiqueta.vue'
import CamposEtiqueta from '@/modulos/etiquetado/componentes/CamposEtiqueta.vue'
import HistorialEtiquetas from '@/modulos/etiquetado/componentes/HistorialEtiquetas.vue'
import TrabajosEtiqueta from '@/modulos/etiquetado/componentes/TrabajosEtiqueta.vue'

// Etiquetado: trabajos (borradores y generados), diseños con versiones,
// familias propias (no la clasificación arancelaria), la familia de cada
// artículo, las reglas que eligen el diseño de cada registro, los campos
// lógicos y el historial de etiquetas generadas. La pestaña viaja en la dirección.
const route = useRoute()
const router = useRouter()
const pestanas = computed(() => [
  ...(puede('etiquetas.generar') ? [['trabajos', t('Labeling jobs'), 'archivo']] : []),
  ['disenos', t('Designs'), 'etiqueta'],
  ['familias', t('Labeling families'), 'capas'],
  ['articulos', t('Items'), 'lista'],
  ['asignaciones', t('Rules'), 'ruta'],
  ['campos', t('Logical fields'), 'filtro'],
  ['historial', t('Generated labels'), 'historial'],
])
const vista = computed(() => (pestanas.value.some((p) => p[0] === route.query.vista) ? route.query.vista : 'disenos'))
const ir = (v) => router.replace({ query: { ...route.query, vista: v === 'disenos' ? undefined : v } })
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Labels') }}</h1>
      <p>{{ t('Design labels with real data from items, purchase orders and packages; rules choose the design of each record and one assistant generates them from any origin.') }}</p>
    </div>
    <div class="acciones">
      <router-link v-if="puede('etiquetas.generar')" class="btn btn-primario" to="/etiquetas/trabajos/nuevo"><Icono nombre="mas" />{{ t('New labeling job') }}</router-link>
    </div>
  </div>
  <nav class="pestanas" role="tablist" :aria-label="t('Labels')">
    <button v-for="[clave, texto, icono] in pestanas" :key="clave" type="button" class="pestana" role="tab" :aria-selected="vista === clave"
            @click="ir(clave)"><Icono :nombre="icono" :tam="15" />{{ tx(texto) }}</button>
  </nav>
  <ListaPlantillas v-if="vista === 'disenos'" />
  <FamiliasEtiquetado v-else-if="vista === 'familias'" />
  <ArticulosFamilia v-else-if="vista === 'articulos'" />
  <AsignacionesEtiqueta v-else-if="vista === 'asignaciones'" />
  <CamposEtiqueta v-else-if="vista === 'campos'" />
  <TrabajosEtiqueta v-else-if="vista === 'trabajos'" />
  <HistorialEtiquetas v-else />
</template>
