<script setup>
import { tema } from '../stores/tema'
import Icono from './Icono.vue'

const OPCIONES = [['claro', 'sol', 'Light theme'], ['oscuro', 'luna', 'Dark theme'], ['sistema', 'monitor', 'Same as the system']]
</script>

<template>
  <div class="tema" role="group" aria-label="Theme">
    <button v-for="[v, icono, texto] in OPCIONES" :key="v" type="button" :aria-pressed="tema === v" :aria-label="texto" :title="texto" @click="tema = v">
      <Icono :nombre="icono" :tam="16" />
    </button>
  </div>
</template>
