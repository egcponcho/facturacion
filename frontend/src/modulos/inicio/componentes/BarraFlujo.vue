<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref } from 'vue'
import { cantTxt, pct } from '@/nucleo/utils'

// Dónde está la mercancía: una barra apilada por unidad de medida (nunca se
// suman pares con unidades). Rampa ordinal de un solo tono: más contraste
// con el fondo = más avanzado en el proceso (se invierte en tema oscuro).
const props = defineProps({ flujo: { type: Object, required: true } })

const ETAPAS = [
  ['por_facturar', t('To invoice'), 'var(--flujo-1)'],
  ['sin_pl', t('Invoiced, no packing list'), 'var(--flujo-2)'],
  ['sin_caja', t('In packing list, not packed'), 'var(--flujo-3)'],
  ['empacado', t('Packed'), 'var(--flujo-4)'],
  ['embarcado', t('Shipped'), 'var(--flujo-5)'],
]
const NOMBRES = { PAR: t('Pairs'), UN: t('Units') }
const activo = ref(null)

const filas = computed(() => Object.entries(props.flujo).map(([unidad, v]) => {
  const total = ETAPAS.reduce((a, [k]) => a + (v[k] || 0), 0)
  return { unidad, total, segmentos: ETAPAS.map(([k, texto, color]) => ({ k, texto, color, valor: v[k] || 0 })).filter((s) => s.valor > 0) }
}).filter((f) => f.total > 0))
</script>

<template>
  <div class="flujo">
    <p v-if="!filas.length" class="ayuda">{{ t('No goods in process yet.') }}</p>
    <div v-for="f in filas" :key="f.unidad" class="flujo-fila">
      <h3><span>{{ tx(NOMBRES[f.unidad] || f.unidad) }}</span><span class="apagado">{{ cantTxt(f.total, f.unidad) }}</span></h3>
      <div class="flujo-barra" role="img" :aria-label="tx(f.segmentos.map((s) => `${s.texto}: ${cantTxt(s.valor, f.unidad)}`).join('; '))">
        <div v-for="s in f.segmentos" :key="s.k" class="flujo-seg" :style="{ flexGrow: s.valor, flexBasis: 0, background: s.color }"
             tabindex="0" @mouseenter="activo = `${f.unidad}-${s.k}`" @mouseleave="activo = null" @focus="activo = `${f.unidad}-${s.k}`" @blur="activo = null">
          <div v-if="activo === `${f.unidad}-${s.k}`" class="info-flotante" style="inset-inline-start: 50%; top: 0">
            <b>{{ cantTxt(s.valor, f.unidad) }}</b>{{ tx(s.texto) }} · {{ tx(pct(s.valor, f.total)) }}%
          </div>
        </div>
      </div>
    </div>
    <div v-if="filas.length" class="leyenda">
      <span v-for="[k, texto, color] in ETAPAS" :key="k"><i :style="{ background: color }"></i>{{ tx(texto) }}</span>
    </div>
  </div>
</template>
