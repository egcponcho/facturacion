<script setup>
import { t, tx } from '@/i18n/index.js'
import { onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import BarraFlujo from '@/modulos/inicio/componentes/BarraFlujo.vue'
import BloqueEnvios from '@/modulos/inicio/componentes/BloqueEnvios.vue'
import BloqueProveedores from '@/modulos/inicio/componentes/BloqueProveedores.vue'
import TableroView from '@/modulos/seguimiento/vistas/TableroView.vue'
import { esInterno, sesion } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'

// Tablero ejecutivo (Análisis): cómo va la operación de punta a punta. Arriba los
// indicadores principales con su tendencia (tablero «resumen», que cada persona
// puede ajustar); debajo la cadena de suministro, los embarques en curso y el
// cumplimiento por proveedor. Estos bloques también se pueden poner en el Inicio.
const d = ref(null)
async function cargar() {
  try {
    d.value = await api.get('/dashboard', { proveedor_id: sesion.proveedorId })
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)
watch(() => sesion.proveedorId, cargar)
</script>

<template>
  <TableroView modulo="resumen" incrustado :titulo="t('Executive dashboard')" />
  <template v-if="d">
    <div class="tablero ejecutivo">
      <section class="panel">
        <div class="panel-cabeza"><div><h2>{{ t('Supply chain') }}</h2><p>{{ t('From PO to load unit, by unit of measure.') }}</p></div></div>
        <BarraFlujo :flujo="d.flujo" />
      </section>
      <BloqueEnvios :envios="d.envios" />
    </div>
    <BloqueProveedores v-if="esInterno() && d.proveedores.length" class="ejecutivo" :proveedores="d.proveedores" />
    <p v-else-if="!esInterno()" class="ayuda ejecutivo">{{ tx(t('Showing your own data only.')) }}</p>
  </template>
</template>

<style scoped>
.ejecutivo { margin-top: 16px; }
</style>
