<script setup>
import { t } from '@/i18n/index.js'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Icono from '@/componentes/Icono.vue'

// Cabecera común del etiquetado: dos tareas separadas (imprimir, a diario;
// configurar, de vez en cuando) y los diseños. Cada sección es su propia página.
defineProps({ titulo: { type: String, required: true }, texto: { type: String, default: '' } })
const route = useRoute()
const secciones = computed(() => [
  ['/etiquetas', t('Print'), 'etiqueta'],
  ['/etiquetas/disenos', t('Designs'), 'capas'],
  ['/etiquetas/configuracion', t('Setup'), 'engrane'],
])
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ titulo }}</h1>
      <p v-if="texto">{{ texto }}</p>
    </div>
    <div class="acciones"><slot /></div>
  </div>
  <nav class="pestanas" :aria-label="t('Labels')">
    <router-link v-for="[ruta, nombre, icono] in secciones" :key="ruta" :to="ruta" class="pestana"
                 :aria-current="route.path === ruta || (ruta !== '/etiquetas' && route.path.startsWith(ruta + '/')) ? 'page' : undefined"><Icono :nombre="icono" :tam="15" />{{ nombre }}</router-link>
  </nav>
</template>

<style scoped>
.pestana[aria-current='page'] { color: var(--acento-texto); border-bottom-color: var(--acento); }
</style>
