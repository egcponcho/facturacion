<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '@/nucleo/api'
import { sesion } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import Icono from './Icono.vue'
import Modal from './Modal.vue'

// Vistas guardadas de una pantalla: los filtros (y la pestaña) que la persona
// usa a menudo, con un nombre («VANS Panamá próximos XF», «Embarques con
// riesgo»). Se guardan en sus preferencias, en el servidor.
//   pantalla: clave de la pantalla; actual: filtros de ahora ({clave: valor});
//   evento «aplicar» con los filtros de la vista elegida.
const props = defineProps({ pantalla: { type: String, required: true }, actual: { type: Object, required: true } })
const emit = defineEmits(['aplicar'])
const abierto = ref(false)
const raiz = ref(null)
const nueva = ref(null)
const ocupado = ref(false)

const vistas = computed(() => sesion.usuario?.preferencias?.vistas?.[props.pantalla] || [])
const limpio = (q) => Object.fromEntries(Object.entries(q || {}).filter(([, v]) => v !== '' && v !== null && v !== undefined).map(([k, v]) => [k, String(v)]))
const igual = (a, b) => JSON.stringify(Object.entries(limpio(a)).sort()) === JSON.stringify(Object.entries(limpio(b)).sort())
const activa = computed(() => vistas.value.find((v) => igual(v.query, props.actual)))

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

async function guardar(lista, mensaje) {
  ocupado.value = true
  try {
    const r = await api.put(`/perfil/vistas/${props.pantalla}`, lista)
    sesion.usuario.preferencias = { ...(sesion.usuario.preferencias || {}), vistas: r.vistas }
    if (mensaje) avisar(mensaje)
    return true
  } catch (e) {
    errorApi(e)
    return false
  } finally {
    ocupado.value = false
  }
}
async function crear() {
  const nombre = (nueva.value?.nombre || '').trim()
  if (!nombre) return
  const otras = vistas.value.filter((v) => v.nombre.toLowerCase() !== nombre.toLowerCase())
  if (await guardar([...otras, { nombre, query: limpio(props.actual) }], t('View “{0}” saved.', [nombre]))) nueva.value = null
}
function quitar(v) {
  guardar(vistas.value.filter((x) => x !== v), t('View “{0}” deleted.', [v.nombre]))
}
function elegir(v) {
  cerrar()
  emit('aplicar', { ...v.query })
}
</script>

<template>
  <div ref="raiz" class="vistas-guardadas" @keydown.esc="cerrar">
    <button type="button" class="btn" :aria-expanded="abierto" aria-haspopup="true" @click="alternar">
      <Icono nombre="lista" :tam="15" />{{ tx(activa ? activa.nombre : t('Saved views')) }}<Icono nombre="abajo" :tam="13" />
    </button>
    <div v-if="abierto" class="vg-menu" role="menu">
      <p v-if="!vistas.length" class="ayuda vg-vacio">{{ t('Save the filters you use often to come back to them in one click.') }}</p>
      <div v-for="v in vistas" :key="v.nombre" class="vg-fila" :class="{ activa: activa === v }">
        <button type="button" class="vg-elegir" role="menuitem" @click="elegir(v)">{{ tx(v.nombre) }}</button>
        <button type="button" class="btn-icono" :aria-label="t('Delete view {0}', [v.nombre])" :disabled="ocupado" @click="quitar(v)"><Icono nombre="basura" :tam="14" /></button>
      </div>
      <button type="button" class="btn btn-chico vg-nueva" role="menuitem" @click="nueva = { nombre: '' }; cerrar()"><Icono nombre="mas" :tam="14" />{{ t('Save current filters as a view') }}</button>
    </div>
    <Modal v-if="nueva" :titulo="t('Save view')" ancho="440px" @cerrar="nueva = null">
      <label class="campo"><span class="req">{{ t('Name') }}</span>
        <input v-model="nueva.nombre" type="text" maxlength="60" :placeholder="t('E.g. VANS Panama next XF')" @keydown.enter.prevent="crear" /></label>
      <p class="ayuda">{{ t('It keeps the current filters and tab. A view with the same name is replaced.') }}</p>
      <template #pie>
        <button class="btn" @click="nueva = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" :disabled="ocupado || !nueva.nombre.trim()" @click="crear">{{ t('Save') }}</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.vistas-guardadas { position: relative; }
.vg-menu { position: absolute; z-index: 30; top: calc(100% + 4px); inset-inline-start: 0; min-width: 260px; max-width: 340px; background: var(--superficie);
  border: 1px solid var(--linea); border-radius: var(--radio-panel); box-shadow: var(--sombra-flotante); padding: 6px; display: flex; flex-direction: column; gap: 2px; }
.vg-fila { display: flex; align-items: center; gap: 4px; border-radius: var(--radio); }
.vg-fila.activa { background: var(--acento-claro); }
.vg-elegir { flex: 1; text-align: start; border: 0; background: none; font: inherit; color: inherit; padding: 8px 10px; cursor: pointer; border-radius: var(--radio); }
.vg-elegir:hover { background: var(--fila-hover); }
.vg-vacio { margin: 6px 8px; }
.vg-nueva { margin-top: 4px; justify-content: flex-start; }
</style>
