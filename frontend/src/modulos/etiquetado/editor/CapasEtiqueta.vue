<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref } from 'vue'
import Icono from '@/componentes/Icono.vue'
import { usarEditor } from './estado.js'

// Capas: los elementos del de encima al de abajo. Clic elige (Mayús suma),
// arrastrar cambia el orden, el ojo oculta y el candado bloquea. Los elementos
// de un mismo grupo llevan la misma marca de color.
const ed = usarEditor()
const est = ed.estado
const ICONOS = { texto: 'texto', campo: 'campo', codigo: 'barras', imagen: 'imagen', rect: 'cuadro', elipse: 'circulo', linea: 'linea' }
const capas = computed(() => [...ed.elementos.value].reverse())
const campo = (c) => ed.camposTodos.value.find((x) => x.clave === c)
const nombre = (e) => e.nombre || (e.campo ? tx(campo(e.campo)?.etiqueta || e.campo) : e.tipo === 'texto' ? (e.contenido || '').slice(0, 30) : e.tipo === 'codigo' ? (e.simbologia || '').toUpperCase() : tx(TIPOS.value[e.tipo]))
const TIPOS = computed(() => ({ texto: t('Text'), campo: t('Field'), codigo: t('Code'), imagen: t('Image'), rect: t('Rectangle'), elipse: t('Ellipse'), linea: t('Line') }))
const COLORES = ['#3355e0', '#1baf7a', '#eb6834', '#e87ba4', '#4a3aa7', '#eda100']
const colorGrupo = (g) => COLORES[[...g].reduce((s, c) => s + c.charCodeAt(0), 0) % COLORES.length]

const arrastrado = ref(null)
const destino = ref(null)
function soltar(i) {
  if (arrastrado.value == null) return
  // i es la posición en la lista invertida
  ed.moverCapa(arrastrado.value, ed.elementos.value.length - 1 - i)
  arrastrado.value = null
  destino.value = null
}
const renombrando = ref(null)
function alternar(e, prop) {
  if (!est.editable) return
  e[prop] = prop === 'visible' ? e.visible === false : !e.bloqueado
}
</script>

<template>
  <div class="capas">
    <div class="capas-barra">
      <button type="button" class="btn btn-icono btn-chico" :disabled="!est.editable || !est.seleccion.length" :title="t('Bring to front')" :aria-label="t('Bring to front')" @click="ed.ordenar('frente')"><Icono nombre="frente" :tam="16" /></button>
      <button type="button" class="btn btn-icono btn-chico" :disabled="!est.editable || !est.seleccion.length" :title="t('Bring forward')" :aria-label="t('Bring forward')" @click="ed.ordenar('subir')"><Icono nombre="arriba" :tam="16" /></button>
      <button type="button" class="btn btn-icono btn-chico" :disabled="!est.editable || !est.seleccion.length" :title="t('Send backward')" :aria-label="t('Send backward')" @click="ed.ordenar('bajar')"><Icono nombre="abajo" :tam="16" /></button>
      <button type="button" class="btn btn-icono btn-chico" :disabled="!est.editable || !est.seleccion.length" :title="t('Send to back')" :aria-label="t('Send to back')" @click="ed.ordenar('fondo')"><Icono nombre="fondo" :tam="16" /></button>
      <button type="button" class="btn btn-icono btn-chico" :disabled="!est.editable || est.seleccion.length < 2" :title="t('Group (Ctrl+G)')" :aria-label="t('Group')" @click="ed.agrupar()"><Icono nombre="agrupar" :tam="16" /></button>
      <button type="button" class="btn btn-chico" :disabled="!est.editable || !ed.seleccionados.value.some((e) => e.grupo)" @click="ed.desagrupar()">{{ t('Ungroup') }}</button>
    </div>
    <ol v-if="capas.length" class="capas-lista">
      <li v-for="(e, i) in capas" :key="e.id" class="capa" :class="{ elegida: est.seleccion.includes(e.id), destino: destino === i, apagada: e.visible === false }"
          :draggable="est.editable" @dragstart="arrastrado = e.id" @dragover.prevent="destino = i" @dragleave="destino = null" @drop.prevent="soltar(i)"
          @click="ed.seleccionar(e.id, $event.shiftKey || $event.metaKey || $event.ctrlKey)">
        <span v-if="e.grupo" class="capa-grupo" :style="{ background: colorGrupo(e.grupo) }" :title="t('Grouped')" />
        <Icono :nombre="ICONOS[e.tipo]" :tam="15" class="capa-icono" />
        <input v-if="renombrando === e.id" v-model.trim="e.nombre" class="capa-nombre-input" :aria-label="t('Name')" maxlength="60"
               @keydown.enter="renombrando = null" @keydown.esc="renombrando = null" @blur="renombrando = null" @click.stop />
        <span v-else class="capa-nombre" :title="t('Double click to rename')" @dblclick.stop="est.editable && (renombrando = e.id)">{{ nombre(e) }}</span>
        <button type="button" class="capa-btn" :class="{ activo: e.visible === false }" :aria-label="e.visible === false ? t('Show') : t('Hide')"
                :title="e.visible === false ? t('Show') : t('Hide')" @click.stop="alternar(e, 'visible')"><Icono nombre="ojo" :tam="14" /></button>
        <button type="button" class="capa-btn" :class="{ activo: e.bloqueado }" :aria-label="e.bloqueado ? t('Unlock') : t('Lock')"
                :title="e.bloqueado ? t('Unlock') : t('Lock')" @click.stop="alternar(e, 'bloqueado')"><Icono nombre="candado" :tam="14" /></button>
      </li>
    </ol>
    <p v-else class="ayuda">{{ t('The label is empty. Add elements or fields from the library.') }}</p>
  </div>
</template>

<style scoped>
.capas-barra { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.capas-lista { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 1px; }
.capa { position: relative; display: flex; align-items: center; gap: 6px; padding: 5px 6px 5px 10px; border-radius: 6px; cursor: pointer; font-size: 0.8rem;
  border: 1px solid transparent; }
.capa:hover { background: var(--fila-hover); }
.capa.elegida { background: var(--acento-claro); border-color: var(--acento-medio); }
.capa.destino { border-top: 2px solid var(--acento); }
.capa.apagada .capa-nombre { color: var(--tinta-3); text-decoration: line-through; }
.capa-grupo { position: absolute; left: 2px; top: 6px; bottom: 6px; width: 3px; border-radius: 2px; }
.capa-icono { color: var(--tinta-3); flex: none; }
.capa-nombre { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.capa-nombre-input { flex: 1; min-width: 0; font-size: 0.8rem; padding: 2px 4px; }
.capa-btn { border: 0; background: none; padding: 2px; color: var(--tinta-3); opacity: 0.45; cursor: pointer; border-radius: 4px; display: inline-flex; }
.capa:hover .capa-btn, .capa-btn.activo { opacity: 1; }
.capa-btn.activo { color: var(--acento); }
</style>
