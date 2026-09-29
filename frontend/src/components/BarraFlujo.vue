<script setup>
import { computed, ref } from 'vue'
import { cantTxt, pct } from '../utils'

// Dónde está la mercancía: una barra apilada por unidad de medida (nunca se
// suman pares con unidades). Rampa ordinal de un solo tono: más oscuro =
// más avanzado en el proceso.
const props = defineProps({ flujo: { type: Object, required: true } })

const ETAPAS = [
  ['por_facturar', 'Por facturar', '#86b6ef'],
  ['sin_pl', 'Facturado sin packing list', '#5598e7'],
  ['sin_caja', 'En packing list, sin caja', '#2a78d6'],
  ['empacado', 'Empacado', '#1c5cab'],
  ['embarcado', 'Embarcado', '#104281'],
]
const NOMBRES = { PAR: 'Pares', UN: 'Unidades' }
const activo = ref(null)

const filas = computed(() => Object.entries(props.flujo).map(([unidad, v]) => {
  const total = ETAPAS.reduce((a, [k]) => a + (v[k] || 0), 0)
  return { unidad, total, segmentos: ETAPAS.map(([k, texto, color]) => ({ k, texto, color, valor: v[k] || 0 })).filter((s) => s.valor > 0) }
}).filter((f) => f.total > 0))
</script>

<template>
  <div class="flujo">
    <p v-if="!filas.length" class="ayuda">Todavía no hay mercancía en proceso.</p>
    <div v-for="f in filas" :key="f.unidad" class="flujo-fila">
      <h3><span>{{ NOMBRES[f.unidad] || f.unidad }}</span><span class="apagado">{{ cantTxt(f.total, f.unidad) }}</span></h3>
      <div class="flujo-barra" role="img" :aria-label="f.segmentos.map((s) => `${s.texto}: ${cantTxt(s.valor, f.unidad)}`).join('; ')">
        <div v-for="s in f.segmentos" :key="s.k" class="flujo-seg" :style="{ flexGrow: s.valor, flexBasis: 0, background: s.color }"
             tabindex="0" @mouseenter="activo = `${f.unidad}-${s.k}`" @mouseleave="activo = null" @focus="activo = `${f.unidad}-${s.k}`" @blur="activo = null">
          <div v-if="activo === `${f.unidad}-${s.k}`" class="info-flotante" style="left: 50%; top: 0">
            <b>{{ cantTxt(s.valor, f.unidad) }}</b>{{ s.texto }} · {{ pct(s.valor, f.total) }}%
          </div>
        </div>
      </div>
    </div>
    <div v-if="filas.length" class="leyenda">
      <span v-for="[k, texto, color] in ETAPAS" :key="k"><i :style="{ background: color }"></i>{{ texto }}</span>
    </div>
  </div>
</template>
