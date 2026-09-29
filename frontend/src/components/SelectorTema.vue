<script setup>
import { tema } from '../stores/tema'
import Icono from './Icono.vue'

const OPCIONES = [['claro', 'sol', 'Tema claro'], ['oscuro', 'luna', 'Tema oscuro'], ['sistema', 'monitor', 'Igual que el sistema']]
</script>

<template>
  <div class="tema" role="group" aria-label="Tema">
    <button v-for="[v, icono, texto] in OPCIONES" :key="v" type="button" :aria-pressed="tema === v" :aria-label="texto" :title="texto" @click="tema = v">
      <Icono :nombre="icono" :tam="16" />
    </button>
  </div>
</template>
