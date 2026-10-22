<script setup>
import { t, tx } from '@/i18n/index.js'
import Icono from '@/componentes/Icono.vue'
import { fmtNum } from '@/nucleo/utils'

// Portada de una configuración: grupos de tarjetas, cada una dice para qué
// sirve y, si tiene clave, cuántos registros hay (cuentas[clave]; sin cargar
// aún muestra un esqueleto). La usan Configuración y la configuración de
// productos.
defineProps({
  grupos: { type: Array, required: true }, // [{ grupo, items: [{ a, icono, nombre, texto, clave? }] }]
  cuentas: { type: Object, default: () => ({}) },
})
const textoCuenta = (n) => (n === 1 ? t('1 record') : t('{0} records', [fmtNum(n)]))
</script>

<template>
  <div class="config-portada">
    <section v-for="g in grupos" :key="g.grupo" :aria-label="g.grupo">
      <h2 class="config-grupo">{{ g.grupo }}</h2>
      <div class="config-tarjetas">
        <router-link v-for="x in g.items" :key="x.a" :to="x.a" class="config-tarjeta">
          <span class="config-icono"><Icono :nombre="x.icono" :tam="20" /></span>
          <span class="config-texto"><b>{{ x.nombre }}</b><small>{{ x.texto }}</small></span>
          <span v-if="x.clave" class="config-cuenta" :class="{ vacia: cuentas[x.clave] === 0 }">
            <span v-if="cuentas[x.clave] === undefined" class="esqueleto" style="width: 28px; height: 14px" />
            <template v-else-if="cuentas[x.clave] === 0">{{ t('No records') }}</template>
            <template v-else>{{ tx(textoCuenta(cuentas[x.clave])) }}</template>
          </span>
        </router-link>
      </div>
    </section>
  </div>
</template>

<style scoped>
.config-portada { display: flex; flex-direction: column; gap: 22px; }
.config-grupo { font-size: var(--t-xs); text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); font-weight: 650; margin: 0 0 10px; }
.config-tarjetas { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.config-tarjeta {
  display: grid; grid-template-columns: auto minmax(0, 1fr); grid-template-rows: auto auto; gap: 4px 14px; padding: 16px; color: inherit; text-decoration: none;
  background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio-panel); box-shadow: var(--sombra);
  transition: border-color 150ms, box-shadow 150ms;
}
.config-tarjeta:hover { border-color: var(--acento-medio); box-shadow: var(--sombra-media); }
.config-icono { grid-row: span 2; width: 40px; height: 40px; border-radius: 10px; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); }
.config-texto { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.config-texto b { font-size: var(--t-md); }
.config-texto small { color: var(--tinta-3); font-size: var(--t-sm); line-height: 1.45; }
.config-cuenta { font-size: var(--t-xs); font-weight: 650; color: var(--tinta-2); font-variant-numeric: tabular-nums; }
.config-cuenta.vacia { color: var(--aviso); }
@media (max-width: 400px) { .config-tarjetas { grid-template-columns: minmax(0, 1fr); } }
@media (prefers-reduced-motion: reduce) { .config-tarjeta { transition: none; } }
</style>
