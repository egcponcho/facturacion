<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// Clases de material que reconoce la composición. Las de base vienen con el
// motor; una familia nueva agrega las suyas (cerámica, vidrio templado…) con
// sus palabras y la palabra con que va en la descripción aduanera. Una
// derivación «clase» de un atributo las lleva a sus opciones.
const edita = puede('clasificacion.configurar')
const clases = ref([])
const cargando = ref(true)
// Cada clase es una fila editable; las columnas filtran por sus valores como el resto de tablas
const columnas = computed(() => [
  { clave: 'codigo', texto: t('Code'), fija: true, prioridad: 1 },
  { clave: 'origen', texto: t('Origin'), prioridad: 3, opciones: [['MOTOR', t('Included')], ['USUARIO', t('Created by users')]],
    valor: (c) => (c.origen === 'MOTOR' ? 'MOTOR' : 'USUARIO') },
  { clave: 'nombre', texto: t('Name'), prioridad: 1 },
  { clave: 'palabras', texto: t('Extra words'), prioridad: 2 },
  { clave: 'texto_aduana', texto: t('In the customs description'), prioridad: 2 },
  { clave: 'activo', texto: t('Active'), prioridad: 2, opciones: [[true, t('Yes')], [false, t('No')]] },
])
const nueva = reactive({ codigo: '', nombre: '', palabras: '', texto_aduana: '' })

async function cargar() {
  try {
    clases.value = await api.get('/aranceles/materiales')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)
async function guardar(c, k, v) {
  try {
    const r = await api.patch(`/aranceles/materiales/${c.id}`, { [k]: v })
    Object.assign(c, r)
  } catch (e) {
    errorApi(e)
    cargar()
  }
}
async function agregar() {
  try {
    await api.post('/aranceles/materiales', { ...nueva })
    Object.assign(nueva, { codigo: '', nombre: '', palabras: '', texto_aduana: '' })
    avisar(t('Material class added.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <section class="panel">
    <h3><Icono nombre="capas" :tam="16" />{{ t('Material classes') }}</h3>
    <p class="ayuda">{{ t('The composition recognizes these classes of material. Add a class for a new family (e.g. ceramic: ceramica porcelain gres) or more words for an existing one; separate the words with spaces, and use ? for an optional letter (porcelanas?).') }}</p>
    <TablaDatos tabla="familias_materiales" :columnas="columnas" :filas="clases" :cargando="cargando" :clase-fila="(c) => ({ apagada: !c.activo })"
                :etiqueta="t('Material classes')">
      <template #celda-codigo="{ fila: c }"><span class="codigo">{{ tx(c.codigo) }}</span></template>
      <template #celda-origen="{ fila: c }"><span class="etiqueta ms-0" :class="c.origen === 'MOTOR' ? 'acento' : ''">{{ c.origen === 'MOTOR' ? t('Included') : t('Created by users') }}</span></template>
      <template #celda-nombre="{ fila: c }"><input class="celda" :value="c.nombre" :disabled="!edita" :aria-label="t('Name')" maxlength="80" @change="guardar(c, 'nombre', $event.target.value)" /></template>
      <template #celda-palabras="{ fila: c }"><input class="celda ancha" :value="c.palabras" :disabled="!edita" :aria-label="t('Extra words')" maxlength="1000"
                                                    :placeholder="c.origen === 'MOTOR' ? t('Base words included; add more') : ''" @change="guardar(c, 'palabras', $event.target.value)" /></template>
      <template #celda-texto_aduana="{ fila: c }"><input class="celda" :value="c.texto_aduana" :disabled="!edita" :aria-label="t('In the customs description')" maxlength="60" @change="guardar(c, 'texto_aduana', $event.target.value)" /></template>
      <template #celda-activo="{ fila: c }"><Interruptor :model-value="c.activo" :deshabilitado="!edita || c.origen === 'MOTOR'" :etiqueta="t('Active')" @update:model-value="guardar(c, 'activo', $event)" /></template>
      <template #vacio>{{ t('No results.') }}</template>
    </TablaDatos>
    <form v-if="edita" class="agregar" @submit.prevent="agregar">
      <strong>{{ t('New class') }}</strong>
      <input v-model="nueva.codigo" class="entrada" :placeholder="t('Code')" :aria-label="t('Code')" maxlength="30" />
      <input v-model="nueva.nombre" class="entrada" :placeholder="t('Name')" :aria-label="t('Name')" maxlength="80" />
      <input v-model="nueva.palabras" class="entrada ancha" :placeholder="t('e.g. ceramica ceramic porcelanas? gres')" :aria-label="t('Extra words')" maxlength="1000" />
      <input v-model="nueva.texto_aduana" class="entrada" :placeholder="t('e.g. CERÁMICA')" :aria-label="t('In the customs description')" maxlength="60" />
      <button class="btn btn-chico" type="submit" :disabled="!nueva.nombre || !nueva.palabras"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button>
    </form>
  </section>
</template>

<style scoped>
h3 { margin: 0 0 6px; font-size: var(--t-md); display: flex; gap: 6px; align-items: center; }
.celda { width: 100%; min-width: 90px; }
.celda::placeholder { color: var(--tinta-3); }
.celda.ancha { min-width: 220px; }
:deep(tr.apagada > td) { opacity: 0.55; }
.agregar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--linea-suave); }
.agregar .entrada { width: auto; flex: 1 1 140px; min-width: 0; }
.agregar .entrada.ancha { flex: 2 1 240px; }
</style>
