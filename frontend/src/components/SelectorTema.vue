<script setup>
import { t, tx } from '../i18n/index.js'
import { tema } from '../stores/tema'
import { guardarPerfil, sesion } from '../stores/sesion'

// Con sesión, el tema elegido queda en el perfil
function elegir(v) {
  tema.value = v
  if (sesion.usuario) guardarPerfil({ tema: v }).catch(() => {})
}
import Icono from './Icono.vue'

const OPCIONES = [['claro', 'sol', t('Light theme')], ['oscuro', 'luna', t('Dark theme')], ['sistema', 'monitor', t('Same as the system')]]
</script>

<template>
  <div class="tema" role="group" :aria-label="t('Theme')">
    <button v-for="[v, icono, texto] in OPCIONES" :key="v" type="button" :aria-pressed="tema === v" :aria-label="tx(texto)" :title="tx(texto)" @click="elegir(v)">
      <Icono :nombre="icono" :tam="16" />
    </button>
  </div>
</template>
