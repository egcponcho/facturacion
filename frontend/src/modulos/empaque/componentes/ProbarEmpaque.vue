<script setup>
import { t, tx } from '@/i18n/index.js'
import { ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { fmtNum } from '@/nucleo/utils'
import { buscarOrdenes } from '@/modulos/etiquetado/componentes/buscadores.js'
import { avisar, errorApi } from '@/stores/ui'

// Probar: se elige una OC y se ve, por posición, la receta que tiene hoy (y de
// dónde salió) y la que le darían las reglas, con la explicación regla por regla.
const props = defineProps({ editable: { type: Boolean, default: false } })
const oc = ref('')
const r = ref(null)
const ORIGEN = { MANUAL: () => t('chosen by hand'), REGLA: () => t('by a rule'), DATOS: () => t('from the PO casepack') }
const OPS = { igual: '=', distinto: '≠', en: '∈', no_en: '∉', mayor: '>', menor: '<', mayor_igual: '≥', menor_igual: '≤' }

async function cargar() {
  if (!oc.value) {
    r.value = null
    return
  }
  try {
    r.value = await api.post('/reglas-empaque/probar', { oc_id: Number(oc.value) })
  } catch (e) {
    errorApi(e)
  }
}
watch(oc, cargar)
async function aplicar() {
  try {
    const x = await api.post('/reglas-empaque/reaplicar', { oc_id: Number(oc.value) })
    avisar(t('{0} lines of the PO took the recipe of the rules.', [x.cambiaron]))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
const valor = (v) => (Array.isArray(v) ? v.join(', ') : v ?? '—')
</script>

<template>
  <div class="probar">
    <p class="ayuda mt-0">{{ t('Choose a PO to see, line by line, the recipe it has today and the one the rules would give it, and why.') }}</p>
    <label class="campo elegir"><span>{{ t('Purchase order') }}</span>
      <SelectBusqueda v-model="oc" :buscar="buscarOrdenes" :etiqueta="t('Purchase order')" :prefijo="false" :vacio="t('None')" /></label>
    <template v-if="r">
      <div class="tabla-scroll">
        <table class="tabla">
          <thead><tr><th>{{ t('Line') }}</th><th>{{ t('Item') }}</th><th class="num">{{ t('Quantity') }}</th><th>{{ t('Today') }}</th>
            <th>{{ t('With the rules') }}</th><th>{{ t('Why') }}</th></tr></thead>
          <tbody>
            <tr v-for="f in r.posiciones" :key="f.posicion_id">
              <td>{{ f.posicion }}</td>
              <td>{{ f.articulo }}</td>
              <td class="num">{{ fmtNum(f.cantidad) }}</td>
              <td>
                <template v-if="f.actual.receta"><b>{{ tx(f.actual.receta) }}</b> <span class="ayuda">{{ ORIGEN[f.actual.origen]?.() }}</span>
                  <div class="ayuda">{{ tx(f.actual.resumen) }}</div>
                  <div v-if="f.actual.aviso" class="aviso-txt">{{ tx(f.actual.aviso) }}</div></template>
                <span v-else class="ayuda">{{ t('No recipe') }}</span>
              </td>
              <td><template v-if="f.reglas.receta"><b>{{ tx(f.reglas.receta) }}</b><div class="ayuda">{{ tx(f.reglas.resumen) }}</div></template>
                <span v-else class="ayuda">{{ t('No rule applies') }}</span></td>
              <td>
                <details v-if="f.explicacion.length">
                  <summary>{{ t('{0} rules for this item', [f.explicacion.length]) }}</summary>
                  <ul class="explicacion">
                    <li v-for="e in f.explicacion" :key="e.regla_id" :class="{ gana: e.gana }">
                      <b>{{ e.orden }}. {{ tx(e.destino) }}</b> → {{ tx(e.receta) }}
                      <span class="etiqueta ms-0" :class="e.gana ? 'ok' : e.cumple ? 'info' : ''">{{ e.gana ? t('Wins') : e.cumple ? t('Applies, less specific') : !e.vigente ? t('Not in force') : t('Does not apply') }}</span>
                      <ul v-if="e.condiciones.length" class="conds">
                        <li v-for="(c, k) in e.condiciones" :key="k" :class="c.cumple ? 'ok-txt' : 'aviso-txt'">
                          {{ tx(c.etiqueta) }} {{ OPS[c.op] || tx(c.op) }} {{ valor(c.valor) }} <span class="ayuda">({{ t('value: {0}', [valor(c.real)]) }})</span>
                        </li>
                      </ul>
                    </li>
                  </ul>
                </details>
                <span v-else class="ayuda">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <button v-if="props.editable" type="button" class="btn" @click="aplicar">{{ t('Apply the rules to the lines of this PO that follow them') }}</button>
      <p class="ayuda">{{ t('Lines with a recipe chosen by hand or from the PO casepack, and invoiced lines, keep theirs.') }}</p>
    </template>
  </div>
</template>

<style scoped>
.probar { display: flex; flex-direction: column; gap: 10px; }
.elegir { max-width: 360px; }
.tabla-scroll { overflow-x: auto; }
.num { text-align: end; font-variant-numeric: tabular-nums; }
.explicacion { margin: 4px 0 0; padding-inline-start: 16px; font-size: var(--t-sm); display: flex; flex-direction: column; gap: 4px; }
.explicacion li.gana { font-weight: 600; }
.conds { list-style: none; padding: 0; margin: 2px 0 0; }
.ok-txt { color: var(--ok); }
.aviso-txt { color: var(--aviso); }
summary { cursor: pointer; }
</style>
