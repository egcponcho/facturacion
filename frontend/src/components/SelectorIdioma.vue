<script setup>
import { IDIOMAS, cambiarIdioma, idioma, t } from '../i18n/index.js'
import Icono from './Icono.vue'

// Idioma de la interfaz: cada uno con su nombre en su propio idioma
</script>

<template>
  <label class="idioma" :title="t('Language')">
    <Icono nombre="globo" :tam="16" />
    <select :value="idioma" :aria-label="t('Language')" @change="cambiarIdioma($event.target.value)">
      <option v-for="x in IDIOMAS" :key="x.codigo" :value="x.codigo" :lang="x.codigo">{{ x.nombre }}</option>
    </select>
  </label>
</template>

<style scoped>
.idioma { display: inline-flex; align-items: center; gap: 4px; padding: 0 8px; height: 34px; border: 1px solid var(--linea); border-radius: 8px; background: var(--superficie-2); color: var(--tinta-2); }
.idioma select { border: 0; background: transparent; color: var(--tinta); font: inherit; font-size: 0.86rem; font-weight: 600; cursor: pointer; padding: 0 2px; }
.idioma select:focus { outline: none; }
.idioma:focus-within { border-color: var(--acento); }
</style>
