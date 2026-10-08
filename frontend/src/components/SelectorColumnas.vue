<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, onBeforeUnmount, ref } from 'vue'
import { errorApi } from '../stores/ui'
import Icono from './Icono.vue'

// Botón «Columnas»: cada persona elige qué columnas ve en la tabla (dentro de
// lo que su rol permite). Se guarda en su perfil.
//   columnas: el objeto que devuelve useColumnas()
const props = defineProps({ columnas: { type: Object, required: true } })
const abierto = ref(false)
const raiz = ref(null)
const ocupado = ref(false)
const opciones = computed(() => props.columnas.permitidas.value.filter((c) => !c.fija))
const ocultas = computed(() => opciones.value.filter((c) => !props.columnas.ver(c.clave)).length)

function fuera(e) {
  if (raiz.value && !raiz.value.contains(e.target)) cerrar()
}
function alternar() {
  abierto.value = !abierto.value
  if (abierto.value) setTimeout(() => document.addEventListener('click', fuera), 0)
  else document.removeEventListener('click', fuera)
}
function cerrar() {
  abierto.value = false
  document.removeEventListener('click', fuera)
}
onBeforeUnmount(() => document.removeEventListener('click', fuera))

async function guardar(claves) {
  ocupado.value = true
  try {
    await props.columnas.guardar(claves)
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
function cambiar(clave) {
  const actuales = opciones.value.filter((c) => props.columnas.ver(c.clave)).map((c) => c.clave)
  guardar(actuales.includes(clave) ? actuales.filter((x) => x !== clave) : [...actuales, clave])
}
</script>

<template>
  <div ref="raiz" class="sel-columnas" @keydown.esc="cerrar">
    <button type="button" class="btn btn-fantasma" :aria-expanded="abierto" aria-haspopup="true" @click="alternar">
      <Icono nombre="columnas" :tam="16" />{{ t('Columns') }}<span v-if="ocultas" class="cuenta">{{ opciones.length - ocultas }}/{{ opciones.length }}</span>
    </button>
    <div v-if="abierto" class="sel-columnas-menu" role="group" :aria-label="t('Columns')">
      <p class="sel-columnas-ayuda">{{ t('Choose what you see in this table. Only you see this change.') }}</p>
      <label v-for="c in opciones" :key="c.clave" class="sel-columnas-op">
        <input type="checkbox" :checked="columnas.ver(c.clave)" :disabled="ocupado" @change="cambiar(c.clave)" />
        <span>{{ tx(c.texto) }}</span>
      </label>
      <button type="button" class="btn btn-chico btn-fantasma" :disabled="ocupado" @click="guardar(null)">{{ t('Back to the initial view') }}</button>
    </div>
  </div>
</template>

<style scoped>
.sel-columnas { position: relative; }
.cuenta { margin-inline-start: 4px; font-size: 0.78rem; color: var(--tinta-3); font-weight: 600; }
.sel-columnas-menu { position: absolute; z-index: 30; inset-inline-end: 0; top: calc(100% + 6px); min-width: 260px; max-height: 420px; overflow: auto;
  background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; box-shadow: var(--sombra-flotante); padding: 8px; }
.sel-columnas-ayuda { margin: 2px 6px 8px; font-size: 0.8rem; color: var(--tinta-3); }
.sel-columnas-op { display: flex; align-items: center; gap: 8px; padding: 6px; border-radius: 6px; cursor: pointer; font-size: 0.9rem; }
.sel-columnas-op:hover { background: var(--superficie-2); }
.sel-columnas-menu .btn { margin-top: 6px; width: 100%; justify-content: center; }
</style>
