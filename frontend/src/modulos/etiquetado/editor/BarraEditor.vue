<script setup>
import { t } from '@/i18n/index.js'
import { computed } from 'vue'
import Icono from '@/componentes/Icono.vue'
import { usarEditor } from './estado.js'
import MenuBarra from './MenuBarra.vue'

// Barra del editor, de izquierda a derecha: insertar (clic al centro o
// arrastrar a la etiqueta), deshacer, lo que se hace con lo elegido (alinear,
// agrupar, orden, girar, bloquear, duplicar, borrar; aparece al elegir algo)
// y la vista (zoom, cuadrícula e imán).
const emit = defineEmits(['acercar', 'alejar', 'zoom100', 'ajustar', 'campos'])
const ed = usarEditor()
const est = ed.estado
const sel = computed(() => ed.seleccionados.value)
const editable = computed(() => est.editable)

const INSERTAR = computed(() => [
  ['texto', t('Text'), 'texto', {}],
  ['codigo', t('Barcode'), 'barras', {}],
  ['codigo', t('QR code'), 'qr', { simbologia: 'qr', w: 20, h: 20, valor: '{{articulo.sku}}', legible: false }],
  ['imagen', t('Image'), 'imagen', {}],
  ['rect', t('Rectangle'), 'cuadro', {}],
  ['elipse', t('Ellipse'), 'circulo', {}],
  ['linea', t('Line'), 'linea', {}],
  ...(est.colecciones.length ? [['tabla', t('Table'), 'tabla', {
    coleccion: est.colecciones[0].clave,
    columnas: est.colecciones[0].columnas.slice(0, 3).map((c) => ({ campo: c.clave, titulo: c.etiqueta, ancho: 1, alin: c.tipo === 'numero' ? 'der' : 'izq' })),
  }]] : []),
])
function arrastrar(ev, tipo, extra) {
  ev.dataTransfer.setData('application/x-etiqueta', JSON.stringify({ tipo, extra }))
  ev.dataTransfer.effectAllowed = 'copy'
}
const ALINEAR = computed(() => [['izq', 'alin-izq', t('Left')], ['centro', 'alin-centro', t('Center')], ['der', 'alin-der', t('Right')],
  ['arriba', 'alin-arriba', t('Top')], ['medio', 'alin-medio', t('Middle')], ['abajo', 'alin-abajo', t('Bottom')]])
const bloqueados = computed(() => sel.value.length > 0 && sel.value.every((e) => e.bloqueado))
const ocultos = computed(() => sel.value.length > 0 && sel.value.every((e) => e.visible === false))
</script>

<template>
  <div class="barra-ed" role="toolbar" :aria-label="t('Editor tools')">
    <!-- Insertar -->
    <div class="be-grupo be-insertar" :aria-label="t('Add')">
      <button v-for="[tipo, texto, icono, extra] in INSERTAR" :key="texto" type="button" class="be-btn" :disabled="!editable" draggable="true"
              :title="t('{0}: click to add it, or drag it onto the label', [texto])" @click="ed.agregar(tipo, extra)" @dragstart="arrastrar($event, tipo, extra)">
        <Icono :nombre="icono" :tam="17" /><span class="be-txt">{{ texto }}</span>
      </button>
      <button type="button" class="be-btn be-campo" :disabled="!editable" :title="t('Add a data field (SKU, PO, size…)')" @click="emit('campos')">
        <Icono nombre="campo" :tam="17" /><span class="be-txt">{{ t('Data field') }}</span>
      </button>
    </div>
    <span class="be-sep" />
    <div class="be-grupo">
      <button type="button" class="be-btn be-icono" :disabled="!editable || !est.historia.length" :title="t('Undo (Ctrl+Z)')" :aria-label="t('Undo')" @click="ed.deshacer()"><Icono nombre="deshacer" :tam="17" /></button>
      <button type="button" class="be-btn be-icono" :disabled="!editable || !est.futuro.length" :title="t('Redo (Ctrl+Y)')" :aria-label="t('Redo')" @click="ed.rehacer()"><Icono nombre="rehacer" :tam="17" /></button>
    </div>

    <!-- Lo elegido -->
    <template v-if="sel.length && editable">
      <span class="be-sep" />
      <div class="be-grupo be-seleccion">
        <MenuBarra icono="alin-centro" :texto="t('Align')" :titulo="t('Align and distribute')">
          <p class="mb-seccion">{{ sel.length > 1 ? t('With each other') : t('To the label') }}</p>
          <button v-for="[m, i, txt] in ALINEAR" :key="m" type="button" @click="ed.alinear(m)"><Icono :nombre="i" :tam="16" />{{ txt }}</button>
          <hr />
          <button type="button" @click="ed.centrar('ambos')"><Icono nombre="ajustar" :tam="16" />{{ t('Center on the label') }}</button>
          <button type="button" :disabled="sel.length < 3" @click="ed.distribuir('h')"><Icono nombre="dist-h" :tam="16" />{{ t('Same horizontal space') }}</button>
          <button type="button" :disabled="sel.length < 3" @click="ed.distribuir('v')"><Icono nombre="dist-v" :tam="16" />{{ t('Same vertical space') }}</button>
          <button type="button" :disabled="sel.length < 2" @click="ed.igualar('w')"><Icono nombre="arribaabajo" :tam="16" />{{ t('Same width') }}</button>
          <button type="button" :disabled="sel.length < 2" @click="ed.igualar('h')"><Icono nombre="arribaabajo" :tam="16" />{{ t('Same height') }}</button>
        </MenuBarra>
        <button v-if="ed.agrupables.value" type="button" class="be-btn" :title="t('Group: they move and are selected as one (Ctrl+G)')" @click="ed.agrupar()">
          <Icono nombre="agrupar" :tam="17" /><span class="be-txt-sel">{{ t('Group them') }}</span></button>
        <button v-if="ed.agrupados.value" type="button" class="be-btn" :title="t('Ungroup (Ctrl+Shift+G)')" @click="ed.desagrupar()">
          <Icono nombre="desagrupar" :tam="17" /><span class="be-txt-sel">{{ t('Ungroup') }}</span></button>
        <MenuBarra icono="capas" :texto="t('Order')" :titulo="t('Order of the layers')">
          <button type="button" @click="ed.ordenar('frente')"><Icono nombre="frente" :tam="16" />{{ t('Bring to front') }}<kbd>Ctrl ]</kbd></button>
          <button type="button" @click="ed.ordenar('subir')"><Icono nombre="arriba" :tam="16" />{{ t('Bring forward') }}<kbd>]</kbd></button>
          <button type="button" @click="ed.ordenar('bajar')"><Icono nombre="abajo" :tam="16" />{{ t('Send backward') }}<kbd>[</kbd></button>
          <button type="button" @click="ed.ordenar('fondo')"><Icono nombre="fondo" :tam="16" />{{ t('Send to back') }}<kbd>Ctrl [</kbd></button>
        </MenuBarra>
        <button type="button" class="be-btn be-icono" :title="t('Rotate 90°')" :aria-label="t('Rotate 90°')" @click="ed.girar(90)"><Icono nombre="girar" :tam="17" /></button>
        <button type="button" class="be-btn be-icono" :class="{ activo: bloqueados }" :aria-pressed="bloqueados" :title="bloqueados ? t('Unlock') : t('Lock')"
                :aria-label="t('Lock')" @click="ed.alternar('bloqueado')"><Icono nombre="candado" :tam="17" /></button>
        <button type="button" class="be-btn be-icono" :class="{ activo: ocultos }" :aria-pressed="ocultos" :title="ocultos ? t('Show') : t('Hide')"
                :aria-label="t('Hide')" @click="ed.alternar('visible')"><Icono nombre="ojo" :tam="17" /></button>
        <button type="button" class="be-btn be-icono" :title="t('Duplicate (Ctrl+D)')" :aria-label="t('Duplicate')" @click="ed.duplicar()"><Icono nombre="copiar" :tam="17" /></button>
        <button type="button" class="be-btn be-icono be-peligro" :title="t('Delete (Del)')" :aria-label="t('Delete')" @click="ed.eliminar()"><Icono nombre="basura" :tam="17" /></button>
      </div>
    </template>

    <span class="be-crece" />
    <!-- Vista -->
    <div class="be-grupo">
      <button type="button" class="be-btn be-icono" :title="t('Zoom out')" :aria-label="t('Zoom out')" @click="emit('alejar')"><Icono nombre="zoom-menos" :tam="17" /></button>
      <button type="button" class="be-btn be-zoom" :title="t('Actual scale (100 %)')" @click="emit('zoom100')">{{ Math.round(est.zoom * 100) }} %</button>
      <button type="button" class="be-btn be-icono" :title="t('Zoom in')" :aria-label="t('Zoom in')" @click="emit('acercar')"><Icono nombre="zoom-mas" :tam="17" /></button>
      <button type="button" class="be-btn be-icono" :title="t('Fit to screen (Ctrl+0)')" :aria-label="t('Fit to screen')" @click="emit('ajustar')"><Icono nombre="ajustar" :tam="17" /></button>
      <button type="button" class="be-btn be-icono" :class="{ activo: est.diseno.cuadricula.visible }" :aria-pressed="est.diseno.cuadricula.visible"
              :title="t('Show grid')" :aria-label="t('Show grid')" @click="est.diseno.cuadricula.visible = !est.diseno.cuadricula.visible"><Icono nombre="cuadricula" :tam="17" /></button>
      <button type="button" class="be-btn" :class="{ activo: est.diseno.cuadricula.ajustar }" :aria-pressed="est.diseno.cuadricula.ajustar"
              :title="t('Elements snap to the grid when moved')" @click="est.diseno.cuadricula.ajustar = !est.diseno.cuadricula.ajustar">{{ t('Grid magnet') }}</button>
    </div>
  </div>
</template>

<style scoped>
.barra-ed { display: flex; align-items: center; gap: 4px; padding: 4px 6px; background: var(--superficie); border: 1px solid var(--linea);
  border-radius: 10px; min-height: 44px; overflow-x: auto; scrollbar-width: thin; }
.be-grupo { display: flex; align-items: center; gap: 2px; flex: none; }
.be-sep { width: 1px; height: 24px; background: var(--linea); margin: 0 4px; flex: none; }
.be-crece { flex: 1; min-width: 8px; }
.be-btn { display: inline-flex; align-items: center; gap: 5px; height: 32px; padding: 0 8px; border: 1px solid transparent; border-radius: 7px;
  background: none; color: var(--tinta-2); font: inherit; font-size: var(--t-xs); cursor: pointer; white-space: nowrap; }
.be-btn:hover:not(:disabled) { background: var(--superficie-2); color: var(--tinta); }
.be-btn:disabled { opacity: 0.4; cursor: default; }
.be-btn.activo { background: var(--acento-claro); border-color: var(--acento-medio); color: var(--acento-texto); }
.be-icono { width: 32px; padding: 0; justify-content: center; }
.be-insertar .be-btn { cursor: grab; }
.be-insertar .be-btn:active { cursor: grabbing; }
.be-campo { color: var(--acento-texto); }
.be-peligro:hover:not(:disabled) { color: var(--error); background: var(--error-fondo); }
.be-zoom { min-width: 54px; justify-content: center; font-variant-numeric: tabular-nums; }
.be-seleccion :deep(.mb-boton) { height: 32px; border-color: transparent; background: none; }
/* Pantallas medianas: los botones de insertar quedan solo con ícono (el texto va en su descripción) */
@media (max-width: 1500px) {
  .be-insertar .be-btn:not(.be-campo) .be-txt { display: none; }
  .be-insertar .be-btn:not(.be-campo) { width: 32px; padding: 0; justify-content: center; }
}
@media (max-width: 1250px) {
  .be-txt-sel, .be-campo .be-txt { display: none; }
  .be-seleccion :deep(.mb-texto) { display: none; }
}
</style>
