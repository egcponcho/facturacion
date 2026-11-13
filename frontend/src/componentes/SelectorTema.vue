<script setup>
import { t, tx } from '@/i18n/index.js'
import { tema } from '@/stores/tema'
import { guardarPerfil, sesion } from '@/stores/sesion'

// Con sesión, el tema elegido queda en el perfil
function elegir(v) {
  tema.value = v
  if (sesion.usuario) guardarPerfil({ tema: v }).catch(() => {})
}
import Icono from './Icono.vue'

// compacto: un solo botón (barra superior) que pasa de claro a oscuro y al revés
// según el tema que se ve ahora (también cuando sigue al sistema)
defineProps({ compacto: { type: Boolean, default: false } })
const oscuroAhora = () => tema.value === 'oscuro'
  || (tema.value === 'sistema' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)

const OPCIONES = [['claro', 'sol', t('Light theme')], ['oscuro', 'luna', t('Dark theme')], ['sistema', 'monitor', t('Same as the system')]]
</script>

<template>
  <button v-if="compacto" type="button" class="btn-icono" :aria-label="oscuroAhora() ? t('Light theme') : t('Dark theme')"
          :title="oscuroAhora() ? t('Light theme') : t('Dark theme')" @click="elegir(oscuroAhora() ? 'claro' : 'oscuro')">
    <Icono :nombre="oscuroAhora() ? 'sol' : 'luna'" :tam="18" />
  </button>
  <div v-else class="tema" role="group" :aria-label="t('Theme')">
    <button v-for="[v, icono, texto] in OPCIONES" :key="v" type="button" :aria-pressed="tema === v" :aria-label="tx(texto)" :title="tx(texto)" @click="elegir(v)">
      <Icono :nombre="icono" :tam="16" />
    </button>
  </div>
</template>
