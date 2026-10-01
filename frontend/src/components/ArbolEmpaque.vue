<script setup>
import { t, tx } from '../i18n/index.js'
import { computed } from 'vue'
import CeldaEditable from './CeldaEditable.vue'
import Icono from './Icono.vue'
import { cantTxt, fmtNum, plural } from '../utils'

// Estructura física del packing list: empaques dentro de empaques con el
// producto en las hojas. Cada nivel muestra su tara y el peso bruto que
// acumula (producto + tara de todo lo que lleva dentro). El volumen es el de
// las medidas exteriores del nivel más alto.
const props = defineProps({
  grupos: { type: Array, required: true },
  editable: Boolean,
  ocupado: Boolean,
  guardar: { type: Function, default: null }, // (grupo, campo) => (valor) => Promise
})
const emit = defineEmits(['deshacer'])

const porId = computed(() => Object.fromEntries(props.grupos.map((g) => [g.id, g])))
const raices = computed(() => props.grupos.filter((g) => !g.padre_id || !porId.value[g.padre_id]))
// Filas aplanadas con su profundidad, en orden de lectura
const filas = computed(() => {
  const out = []
  const visitar = (g, nivel) => {
    out.push({ g, nivel })
    for (const h of g.hijos || []) if (porId.value[h.id]) visitar(porId.value[h.id], nivel + 1)
  }
  for (const r of raices.value) visitar(r, 0)
  return out
})
const ICONO = { SOPORTE: 'capas', BULTO: 'caja', INTERIOR: 'archivo' }
const contenidoTxt = (g) => (g.items || []).map((i) => `${cantTxt(i.cantidad_por_caja, i.unidad)} ${i.estilo} ${i.talla || ''}`.trim()).join(' + ')
</script>

<template>
  <div class="arbol" role="tree" :aria-label="t('Physical packing structure')">
    <div v-for="{ g, nivel } in filas" :key="g.id" class="nodo" :class="[`c-${g.cuenta_como}`]" role="treeitem" :aria-level="nivel + 1"
         :style="{ '--nivel': nivel }">
      <span class="guia" aria-hidden="true"></span>
      <span class="icono"><Icono :nombre="ICONO[g.cuenta_como] || 'caja'" :tam="15" /></span>
      <div class="cuerpo">
        <div class="titulo">
          <b>{{ tx(g.etiqueta_rango) }}</b>
          <span class="tipo">{{ tx(g.tipo) }}</span>
          <span class="cuantos">{{ g.por_padre ? t('{0} per {1}', [fmtNum(g.por_padre), tx(porId[g.padre_id]?.tipo || '').toLowerCase()]) : plural(g.num_cajas, t('unit'), t('units')) }}</span>
        </div>
        <div v-if="g.items?.length" class="sub">{{ tx(contenidoTxt(g)) }} {{ t('per unit') }}</div>
        <div class="medidas">
          <template v-if="editable && guardar && g.cuenta_como === 'SOPORTE'">
            <label v-for="campo in ['largo', 'ancho', 'alto']" :key="campo" class="mini">
              <span>{{ tx({ largo: t('L'), ancho: t('W'), alto: t('H') }[campo]) }}</span>
              <CeldaEditable tipo="number" :min="0" :valor="g[campo]" :guardar="guardar(g, campo)" :etiqueta="t('{0} of {1}', [campo, g.etiqueta_rango])" />
            </label>
            <label class="mini"><span>{{ t('Tare') }}</span>
              <CeldaEditable tipo="number" :min="0" :valor="g.tara" :guardar="guardar(g, 'peso_tara')" :etiqueta="t('Tare of {0}', [g.etiqueta_rango])" /></label>
          </template>
          <template v-else>
            <span v-if="g.largo">{{ fmtNum(g.largo) }}×{{ fmtNum(g.ancho) }}×{{ fmtNum(g.alto) }} cm</span>
            <span>{{ t('tare {0} kg', [fmtNum(g.tara || 0, 2)]) }}</span>
          </template>
        </div>
      </div>
      <div class="pesos">
        <span :title="t('Net per unit: products only')">{{ t('Net {0}', [g.peso_neto_caja != null ? fmtNum(g.peso_neto_caja, 2) : '—']) }}</span>
        <b :title="t('Gross per unit: products + tare of every level inside')">{{ t('Gross {0} kg', [g.peso_bruto_caja != null ? fmtNum(g.peso_bruto_caja, 2) : '—']) }}</b>
        <span v-if="!g.padre_id && g.cbm_total" class="sub">{{ fmtNum(g.cbm_total, 3) }} m³</span>
      </div>
      <button v-if="editable && g.hijos?.length && g.cuenta_como === 'SOPORTE'" class="btn btn-chico btn-fantasma" :disabled="ocupado"
              :title="t('Take its contents out and remove it')" @click="emit('deshacer', g)">{{ t('Undo') }}</button>
    </div>
    <p v-if="!filas.length" class="ayuda">{{ t('No packaging yet.') }}</p>
  </div>
</template>

<style scoped>
.arbol { display: flex; flex-direction: column; gap: 4px; }
.nodo { display: grid; grid-template-columns: calc(var(--nivel) * 22px) auto 1fr auto auto; gap: 10px; align-items: center;
  padding: 8px 10px; border-radius: var(--radio); border: 1px solid var(--linea); background: var(--superficie); }
.nodo.c-SOPORTE { background: color-mix(in srgb, var(--acento) 6%, var(--superficie)); }
.nodo.c-INTERIOR { background: var(--superficie-2); }
.guia { height: 100%; border-inline-end: 2px dotted var(--linea); }
.icono { width: 28px; height: 28px; border-radius: 8px; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); }
.cuerpo { min-width: 0; }
.titulo { display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: baseline; }
.tipo { font-size: 0.8rem; color: var(--tinta-2); }
.cuantos { font-size: 0.78rem; color: var(--tinta-3); }
.sub { font-size: 0.78rem; color: var(--tinta-3); }
.medidas { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 0.8rem; color: var(--tinta-2); margin-top: 2px; }
.mini { display: inline-flex; align-items: center; gap: 4px; }
.mini > span { color: var(--tinta-3); }
.mini :deep(.celda-editable), .mini :deep(input) { width: 70px; }
.pesos { display: flex; flex-direction: column; align-items: flex-end; font-size: 0.8rem; color: var(--tinta-2); white-space: nowrap; }
.pesos b { color: var(--tinta); font-size: 0.86rem; }
@media (max-width: 640px) {
  .nodo { grid-template-columns: calc(var(--nivel) * 12px) auto 1fr; }
  .pesos { grid-column: 3; align-items: flex-start; flex-direction: row; gap: 8px; }
  .nodo > .btn { grid-column: 3; justify-self: start; }
}
</style>
