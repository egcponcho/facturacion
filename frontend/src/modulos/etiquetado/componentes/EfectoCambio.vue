<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref } from 'vue'
import Icono from '@/componentes/Icono.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import { fmtNum } from '@/nucleo/utils'

// «Qué cambia al guardar»: el resultado de POST /etiquetas/usos/simular (no
// guarda nada). Se usa en la celda, en el producto y en la OC.
const props = defineProps({ efecto: { type: Object, default: null }, cargando: Boolean, sinCambios: Boolean })
const verArticulos = ref(false)
</script>

<template>
  <section class="efecto" aria-live="polite">
    <h4><Icono nombre="info" :tam="15" />{{ t('What changes when saving') }}</h4>
    <p v-if="sinCambios" class="ayuda">{{ t('Nothing has changed yet.') }}</p>
    <p v-else-if="cargando && !efecto" class="ayuda">{{ t('Calculating…') }}</p>
    <template v-else-if="efecto">
      <template v-if="efecto.sujeto === 'ARTICULO'">
        <p>
          <strong>{{ t('{0} items change design.', [fmtNum(efecto.cambian)]) }}</strong>
          <span v-if="efecto.alcance" class="ayuda"> {{ t('({0} items in this place)', [fmtNum(efecto.alcance)]) }}</span>
        </p>
        <p v-if="efecto.sin_diseno" class="aviso-txt"><Icono nombre="alerta" :tam="14" /> {{ t('{0} items are left without a design of this type.', [fmtNum(efecto.sin_diseno)]) }}</p>
        <p v-else class="ayuda">{{ t('No item is left without a design.') }}</p>
      </template>
      <p v-else>{{ t('It applies to every package or document of this place.') }}</p>
      <p v-if="efecto.trabajos" class="aviso-txt">{{ t('{0} open labeling jobs will have to be checked again.', [fmtNum(efecto.trabajos)]) }}</p>
      <button v-if="efecto.ejemplos?.length" type="button" class="btn btn-chico" @click="verArticulos = true">{{ t('See the items') }}<Icono nombre="derecha" :tam="13" /></button>
    </template>
  </section>

  <PanelLateral v-if="verArticulos" :titulo="t('Items that change design')" @cerrar="verArticulos = false">
    <table class="tabla">
      <thead><tr><th>{{ t('Item') }}</th><th>{{ t('Before') }}</th><th>{{ t('After') }}</th></tr></thead>
      <tbody>
        <tr v-for="x in props.efecto.ejemplos" :key="x.articulo_id">
          <td class="codigo">{{ x.sku }}</td><td>{{ x.antes ? tx(x.antes) : t('No design') }}</td>
          <td><strong>{{ x.despues ? tx(x.despues) : t('No design') }}</strong></td>
        </tr>
      </tbody>
    </table>
    <p v-if="props.efecto.cambian > props.efecto.ejemplos.length" class="ayuda">{{ t('Showing {0} of {1}.', [props.efecto.ejemplos.length, fmtNum(props.efecto.cambian)]) }}</p>
  </PanelLateral>
</template>

<style scoped>
.efecto { border: 1px solid var(--linea); border-radius: 10px; padding: 10px 14px; background: var(--superficie-2); display: flex; flex-direction: column; gap: 4px; }
.efecto h4 { margin: 0 0 4px; font-size: 0.88rem; display: flex; gap: 6px; align-items: center; }
.efecto p { margin: 0; font-size: 0.86rem; display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
.efecto .btn { align-self: flex-start; margin-top: 4px; }
.aviso-txt { color: var(--aviso); }
</style>
