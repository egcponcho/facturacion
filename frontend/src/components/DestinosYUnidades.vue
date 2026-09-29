<script setup>
import { computed } from 'vue'
import { MODOS } from '../composables/useRutas'
import { fmtNum, plural, porUnidadTxt } from '../utils'
import Icono from './Icono.vue'

// What the packing list carries per destination (cartons never mix
// destinations) and the load units that fit its volume and weight.
const props = defineProps({ pl: { type: Object, required: true } })

const destinos = computed(() => props.pl.destinos || [])
const modos = computed(() => Object.entries(props.pl.sugerencia_unidades?.modos || {}).filter(([, ops]) => ops.length))
</script>

<template>
  <div class="destinos-unidades">
    <div v-if="destinos.length">
      <h3>By destination</h3>
      <p class="ayuda">Cartons never mix destinations: pack and label each destination separately.</p>
      <ul class="lista-destinos">
        <li v-for="d in destinos" :key="d.centro_destino || '-'">
          <b>{{ d.centro_destino || 'No destination' }}</b>
          <span v-if="d.nombre" class="sub">{{ d.nombre }}<template v-if="d.pais"> · {{ d.pais }}</template></span>
          <span>{{ porUnidadTxt(d.por_unidad, null) }} · {{ plural(d.cajas, 'carton', 'cartons') }}</span>
        </li>
      </ul>
    </div>
    <div v-if="modos.length">
      <h3>Suggested load units</h3>
      <p class="ayuda">For {{ fmtNum(pl.sugerencia_unidades.cbm, 2) }} m³ and {{ fmtNum(pl.sugerencia_unidades.kg, 0) }} kg, using about 85% of each unit's volume.</p>
      <ul class="lista-destinos">
        <li v-for="[modo, ops] in modos" :key="modo">
          <b><Icono :nombre="MODOS[modo]?.icono || 'caja'" :tam="14" /> {{ MODOS[modo]?.nombre || modo }}</b>
          <span>
            <span class="etiqueta ok" style="margin-left: 0">{{ ops[0].texto }}</span>
            <template v-if="ops[0].pct_cbm"> {{ fmtNum(ops[0].pct_cbm, 0) }}% of the volume</template>
          </span>
          <span v-if="ops[0].nota" class="sub">{{ ops[0].nota }}</span>
          <span v-if="ops.length > 1" class="sub">Other options: {{ ops.slice(1).map((o) => o.texto).join(' · ') }}</span>
        </li>
      </ul>
    </div>
    <p v-if="!modos.length && pl.grupos?.length" class="ayuda">Add carton dimensions and weights to get load unit suggestions.</p>
  </div>
</template>

<style scoped>
.destinos-unidades { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; margin-top: 14px; }
.destinos-unidades h3 { margin: 0 0 4px; font-size: 0.95rem; }
.lista-destinos { list-style: none; margin: 8px 0 0; padding: 0; display: grid; gap: 8px; }
.lista-destinos li { display: grid; gap: 2px; padding: 8px 10px; border: 1px solid var(--linea); border-radius: 8px; }
.lista-destinos b { display: flex; align-items: center; gap: 6px; }
</style>
