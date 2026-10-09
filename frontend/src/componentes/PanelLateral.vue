<script setup>
import { t, tx } from '@/i18n/index.js'
import { onBeforeUnmount, onMounted } from 'vue'
import Icono from './Icono.vue'
import { abrirCapa, cerrarCapa, esLaDeArriba } from '@/nucleo/capas.js'

// Panel lateral (drawer): para consultar un registro sin salir de la lista (se
// conservan filtros, página y orden) y para los procesos largos que no caben
// en una ventana (editor de roles, empaque automático, perfiles de
// importación). «Abrir detalle completo» lleva a su página. Esc o clic fuera
// lo cierran; los botones de la acción van en el pie (#pie), siempre visibles.
const props = defineProps({ titulo: { type: String, default: '' }, detalle: { type: String, default: '' }, ancho: { type: String, default: '460px' } })
const emit = defineEmits(['cerrar'])
let capa = null
const tecla = (e) => e.key === 'Escape' && esLaDeArriba(capa) && emit('cerrar')
onMounted(() => {
  capa = abrirCapa()
  document.addEventListener('keydown', tecla)
})
onBeforeUnmount(() => {
  cerrarCapa(capa)
  document.removeEventListener('keydown', tecla)
})
</script>

<template>
  <Teleport to="body">
    <div class="pl-fondo" @mousedown.self="emit('cerrar')">
      <aside class="pl-panel" role="dialog" aria-modal="true" :aria-label="tx(props.titulo)" :style="{ maxWidth: props.ancho }">
        <header class="pl-cabeza">
          <div class="pl-titulos"><h2>{{ tx(props.titulo) }}</h2><slot name="estado" /></div>
          <div class="fila-flex" style="gap: 6px; flex-wrap: nowrap">
            <router-link v-if="props.detalle" class="btn btn-chico" :to="props.detalle">{{ t('Open full detail') }}<Icono nombre="derecha" :tam="13" /></router-link>
            <button class="btn-icono" type="button" :aria-label="t('Close')" @click="emit('cerrar')"><Icono nombre="cerrar" :tam="20" /></button>
          </div>
        </header>
        <div class="pl-cuerpo"><slot /></div>
        <footer v-if="$slots.pie" class="pl-pie"><slot name="pie" /></footer>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.pl-fondo { position: fixed; inset: 0; z-index: 55; background: color-mix(in srgb, var(--velo) 60%, transparent); display: flex; justify-content: flex-end; animation: pl-aparecer 0.12s ease-out; }
@keyframes pl-aparecer { from { opacity: 0; } to { opacity: 1; } }
.pl-panel { width: 100%; height: 100%; background: var(--superficie); box-shadow: var(--sombra-flotante); display: flex; flex-direction: column; animation: pl-entrar 0.16s ease-out; }
@keyframes pl-entrar { from { transform: translateX(24px); } to { transform: none; } }
[dir='rtl'] .pl-fondo { justify-content: flex-start; }
.pl-cabeza { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; padding: 16px 18px 10px; border-bottom: 1px solid var(--linea-suave); }
.pl-titulos { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.pl-titulos h2 { margin: 0; font-size: 1.15rem; overflow-wrap: anywhere; }
.pl-cuerpo { flex: 1; min-height: 0; padding: 14px 18px 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
.pl-pie { display: flex; justify-content: flex-end; gap: var(--e-2); flex-wrap: wrap; padding: 12px 18px; border-top: 1px solid var(--linea-suave); background: var(--superficie); }
</style>
