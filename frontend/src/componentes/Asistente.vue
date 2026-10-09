<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import Icono from './Icono.vue'

// Asistente por pasos: «Paso N de M», barra de avance, la lista de pasos (se
// puede volver a cualquiera sin perder lo escrito) y los botones Atrás /
// Guardar borrador / Siguiente, o la acción final en el último paso. Qué se
// valida y cuándo se guarda lo decide la pantalla que lo usa. En el celular
// ocupa toda la pantalla.
const props = defineProps({
  documento: { type: String, default: '' }, // qué se está armando («New purchase order», «PO 4500…»)
  pasos: { type: Array, required: true }, // [{ clave, titulo, errores: n, completo: bool, bloqueado: bool }]
  actual: { type: Number, default: 0 },
  ocupado: Boolean,
  guardado: { type: String, default: '' }, // estado del guardado («Saved at 10:42», «Saving…»)
  textoFinal: { type: String, default: t('Finish') },
  conBorrador: { type: Boolean, default: true },
})
const emit = defineEmits(['ir', 'anterior', 'siguiente', 'guardar', 'finalizar', 'cerrar'])
const ultimo = computed(() => props.actual === props.pasos.length - 1)
const paso = computed(() => props.pasos[props.actual] || {})
const porcentaje = computed(() => Math.round(((props.actual + 1) * 100) / props.pasos.length))
const marca = (p, i) => (i === props.actual ? 'actual' : p.errores ? 'error' : p.completo ? 'completo' : '')
</script>

<template>
  <section class="asistente" :aria-label="tx(documento || paso.titulo)">
    <header class="as-cabeza">
      <div class="as-titulos">
        <span class="eyebrow">{{ t('Step {0} of {1}', [actual + 1, pasos.length]) }}<template v-if="documento"> · {{ tx(documento) }}</template></span>
        <h1>{{ tx(paso.titulo) }}</h1>
      </div>
      <span class="as-guardado" role="status" aria-live="polite">{{ tx(guardado) }}</span>
      <button type="button" class="btn-icono as-cerrar" :aria-label="t('Close the assistant')" @click="emit('cerrar')"><Icono nombre="cerrar" :tam="20" /></button>
    </header>
    <div class="as-barra" role="progressbar" :aria-label="t('Progress')" aria-valuemin="1" :aria-valuemax="pasos.length" :aria-valuenow="actual + 1">
      <div :style="{ width: `${porcentaje}%` }"></div>
    </div>
    <nav class="as-pasos" :aria-label="t('Steps')">
      <ol>
        <li v-for="(p, i) in pasos" :key="p.clave">
          <button type="button" class="as-paso" :class="marca(p, i)" :aria-current="i === actual ? 'step' : undefined"
                  :disabled="p.bloqueado || ocupado" @click="i !== actual && emit('ir', i)">
            <span class="as-marca">
              <Icono v-if="marca(p, i) === 'completo'" nombre="check" :tam="13" />
              <Icono v-else-if="marca(p, i) === 'error'" nombre="alerta" :tam="13" />
              <template v-else>{{ tx(i + 1) }}</template>
            </span>
            <span class="as-paso-titulo">{{ tx(p.titulo) }}</span>
            <span v-if="marca(p, i) === 'error'" class="oculto-visual">{{ t('(needs attention)') }}</span>
          </button>
        </li>
      </ol>
    </nav>
    <div class="as-cuerpo"><slot /></div>
    <footer class="as-pie">
      <button v-if="actual > 0" type="button" class="btn" :disabled="ocupado" @click="emit('anterior')"><Icono nombre="atras" :tam="16" />{{ t('Back') }}</button>
      <span class="as-espacio"></span>
      <button v-if="conBorrador" type="button" class="btn btn-fantasma" :disabled="ocupado" @click="emit('guardar')">{{ t('Save draft') }}</button>
      <button v-if="!ultimo" type="button" class="btn btn-primario" :disabled="ocupado" @click="emit('siguiente')">{{ t('Next') }}<Icono nombre="derecha" :tam="16" /></button>
      <button v-else type="button" class="btn btn-primario" :disabled="ocupado" @click="emit('finalizar')"><Icono nombre="check" :tam="16" />{{ tx(textoFinal) }}</button>
    </footer>
  </section>
</template>

<style scoped>
.asistente { display: flex; flex-direction: column; gap: 14px; max-width: 1080px; }
.as-cabeza { display: flex; align-items: flex-start; gap: 12px; }
.as-titulos { flex: 1; min-width: 0; }
.as-titulos h1 { margin: 2px 0 0; }
.as-guardado { color: var(--tinta-3); font-size: 0.84rem; white-space: nowrap; align-self: center; }
.as-barra { height: 4px; border-radius: 4px; background: var(--linea-suave); overflow: hidden; }
.as-barra > div { height: 100%; background: var(--acento); transition: width 0.2s ease-out; }
.as-pasos ol { list-style: none; margin: 0; padding: 0; display: flex; gap: 6px; flex-wrap: wrap; }
.as-paso { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--linea); background: var(--superficie); color: var(--tinta-2);
  border-radius: 20px; padding: 4px 12px 4px 4px; font: inherit; font-size: 0.85rem; cursor: pointer; }
.as-paso:hover:not(:disabled) { border-color: var(--borde-hover); }
.as-paso:disabled { cursor: default; opacity: 0.6; }
.as-marca { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--linea-suave); font-size: 0.78rem; font-weight: 650; }
.as-paso.actual { border-color: var(--acento); color: var(--acento-texto); background: var(--acento-claro); font-weight: 620; }
.as-paso.actual .as-marca { background: var(--acento); color: var(--sobre-acento); }
.as-paso.completo .as-marca { background: var(--ok-fondo); color: var(--ok); }
.as-paso.error { border-color: var(--aviso-borde); }
.as-paso.error .as-marca { background: var(--aviso-fondo); color: var(--aviso); }
.as-cuerpo { display: flex; flex-direction: column; gap: 16px; }
.as-pie { position: sticky; bottom: 0; z-index: 15; display: flex; align-items: center; gap: 8px; padding: 12px 0;
  background: linear-gradient(to top, var(--papel) 75%, transparent); }
.as-espacio { flex: 1; }
@media (max-width: 720px) {
  /* Pantalla completa: el asistente tapa el menú y se desplaza solo su contenido */
  .asistente { position: fixed; inset: 0; z-index: 48; max-width: none; gap: 10px; padding: 12px 16px 0; background: var(--papel); }
  .as-cuerpo { flex: 1; overflow-y: auto; margin: 0 -16px; padding: 0 16px 12px; }
  .as-titulos h1 { font-size: 1.25rem; }
  .as-guardado { display: none; }
  .as-pasos ol { flex-wrap: nowrap; overflow-x: auto; }
  .as-paso { padding: 4px; }
  .as-paso:not(.actual) .as-paso-titulo { display: none; }
  .as-pie { margin: 0 -16px; padding: 10px 16px calc(10px + env(safe-area-inset-bottom)); background: var(--superficie); border-top: 1px solid var(--linea); }
  .as-pie .btn-fantasma { padding-inline: 8px; }
}
</style>
