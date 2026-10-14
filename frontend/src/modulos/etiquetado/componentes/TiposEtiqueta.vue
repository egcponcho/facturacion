<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { CANTIDADES, SUJETOS, catalogos } from '@/modulos/etiquetado/etiquetas.js'

// Tipos de etiqueta de la empresa: qué se etiqueta (artículo, bulto o
// documento), cuántas salen de cada uno y si es obligatoria. Son las columnas
// de «Qué diseño lleva cada cosa».
const emit = defineEmits(['cambio'])
const lista = ref([])
const cargando = ref(false)
const cantidadesDe = ref({})
const editable = computed(() => puede('etiquetas.configurar'))

async function cargar() {
  cargando.value = true
  try {
    lista.value = await api.get('/etiquetas/tipos', { todos: true })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(() => {
  cargar()
  catalogos().then((c) => (cantidadesDe.value = c.cantidades)).catch(() => {})
})
alCambiar(() => cargar(), ['/etiquetas/tipos'])

const columnas = computed(() => [
  { clave: 'orden', texto: '#', num: true, prioridad: 2, filtro: false },
  { clave: 'nombre', texto: t('Label type'), fija: true, prioridad: 1 },
  { clave: 'sujeto', texto: t('What is labeled'), prioridad: 1, textoValor: (v) => SUJETOS()[v] || v },
  { clave: 'cantidad', texto: t('How many'), prioridad: 2, textoValor: (v) => CANTIDADES()[v] || v },
  { clave: 'obligatoria', texto: t('Required'), prioridad: 2, opciones: [[true, t('Yes')], [false, t('No')]] },
  { clave: 'disenos', texto: t('Designs'), num: true, prioridad: 3 },
  { clave: 'usos', texto: t('Places'), num: true, prioridad: 3 },
  { clave: 'activo', texto: t('Status'), prioridad: 2, opciones: [[true, t('Active')], [false, t('Inactive')]] },
])

const edicion = ref(null)
function editar(x) {
  edicion.value = x ? { ...x } : { codigo: '', nombre: '', descripcion: '', sujeto: 'ARTICULO', cantidad: 'POR_UNIDAD', obligatoria: false, activo: true }
}
watch(() => edicion.value?.sujeto, (s) => {
  const e = edicion.value
  if (e && s && cantidadesDe.value[s] && !cantidadesDe.value[s].includes(e.cantidad)) e.cantidad = cantidadesDe.value[s][0]
})
// El código sale del nombre mientras no se escriba uno
function sugerirCodigo() {
  const e = edicion.value
  if (e.id || e.codigoTocado) return
  e.codigo = e.nombre.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 30)
}
async function guardar() {
  const e = edicion.value
  const datos = { codigo: e.codigo, nombre: e.nombre, descripcion: e.descripcion, sujeto: e.sujeto, cantidad: e.cantidad,
    obligatoria: e.obligatoria, activo: e.activo }
  try {
    if (e.id) await api.patch(`/etiquetas/tipos/${e.id}`, { ...datos, version: e.version })
    else await api.post('/etiquetas/tipos', datos)
    avisar(e.id ? t('Label type saved.') : t('Label type “{0}” created.', [e.nombre]))
    edicion.value = null
    await cargar()
    emit('cambio')
  } catch (err) {
    if (err.status === 409) {
      avisar(t('Someone else changed this label type: it was reloaded.'), 'aviso')
      edicion.value = null
      cargar()
    } else errorApi(err)
  }
}
async function mover(x, delta) {
  const orden = [...lista.value].sort((a, b) => a.orden - b.orden || a.id - b.id)
  const i = orden.findIndex((y) => y.id === x.id)
  const j = i + delta
  if (j < 0 || j >= orden.length) return
  ;[orden[i], orden[j]] = [orden[j], orden[i]]
  try {
    // Solo los que cambian de lugar
    await Promise.all(orden.map((y, k) => (y.orden !== k + 1 ? api.patch(`/etiquetas/tipos/${y.id}`, { orden: k + 1, version: y.version }) : null)))
    await cargar()
    emit('cambio')
  } catch (e) {
    errorApi(e)
    cargar()
  }
}
const conDisenos = computed(() => edicion.value?.id && edicion.value.disenos > 0)
</script>

<template>
  <p class="nota mb-3"><Icono nombre="info" :tam="16" />{{ t('Each label type is a column of “Which design goes on what”. Required types must have a design for every record before printing.') }}</p>
  <TablaDatos tabla="etiquetas_tipos" :columnas="columnas" :filas="lista" :cargando="cargando" orden-inicial="orden:asc" fila-clicable
              :clase-fila="(x) => ({ apagada: !x.activo })" :etiqueta="t('Label types')" @fila="(x) => editable && editar(x)">
    <template #filtros>
      <button v-if="editable" type="button" class="btn btn-primario separar" @click="editar(null)"><Icono nombre="mas" />{{ t('New label type') }}</button>
    </template>
    <template #celda-nombre="{ fila: x }"><strong>{{ tx(x.nombre) }}</strong><span class="sub">{{ x.codigo }}</span></template>
    <template #celda-obligatoria="{ fila: x }"><span v-if="x.obligatoria" class="etiqueta aviso ms-0">{{ t('Required') }}</span><span v-else class="apagado">{{ t('Optional') }}</span></template>
    <template #celda-activo="{ fila: x }"><span class="etiqueta ms-0" :class="x.activo ? 'ok' : ''">{{ x.activo ? t('Active') : t('Inactive') }}</span></template>
    <template #acciones="{ fila: x }">
      <template v-if="editable">
        <button type="button" class="btn-icono" :aria-label="t('Move up')" :title="t('Move up')" @click.stop="mover(x, -1)"><Icono nombre="arriba" :tam="15" /></button>
        <button type="button" class="btn-icono" :aria-label="t('Move down')" :title="t('Move down')" @click.stop="mover(x, 1)"><Icono nombre="abajo" :tam="15" /></button>
      </template>
    </template>
    <template #vacio>{{ t('No label types yet.') }}</template>
  </TablaDatos>

  <Modal v-if="edicion" :titulo="edicion.id ? t('Label type {0}', [tx(edicion.nombre)]) : t('New label type')" ancho="560px" @cerrar="edicion = null">
    <form id="form-tipo" class="form-tipo" @submit.prevent="guardar">
      <label class="campo"><span class="req">{{ t('Name') }}</span>
        <input v-model="edicion.nombre" required maxlength="120" :placeholder="t('E.g. Hang tag')" @input="sugerirCodigo" /></label>
      <label class="campo"><span class="req">{{ t('Code') }}</span>
        <input v-model="edicion.codigo" required maxlength="30" pattern="[A-Za-z0-9][A-Za-z0-9_\-]*" @input="edicion.codigoTocado = true" />
        <small class="ayuda">{{ t('Capital letters, digits, - and _. It identifies the type in files and integrations.') }}</small></label>
      <fieldset class="campo">
        <legend class="req">{{ t('What is labeled') }}</legend>
        <div class="opciones-sujeto">
          <label v-for="(txt, s) in SUJETOS()" :key="s" class="check"><input v-model="edicion.sujeto" type="radio" :value="s" :disabled="conDisenos" /> {{ txt }}</label>
        </div>
        <small v-if="conDisenos" class="ayuda">{{ t('The type already has designs: what it labels cannot change.') }}</small>
      </fieldset>
      <label class="campo"><span class="req">{{ t('How many labels come out') }}</span>
        <Seleccion v-model="edicion.cantidad">
          <option v-for="c in cantidadesDe[edicion.sujeto] || []" :key="c" :value="c">{{ CANTIDADES()[c] }}</option>
        </Seleccion></label>
      <label class="check"><input v-model="edicion.obligatoria" type="checkbox" /> {{ t('Required: every record must have a design of this type to print') }}</label>
      <label class="campo"><span>{{ t('Description') }}</span><textarea v-model="edicion.descripcion" rows="2" maxlength="300"></textarea></label>
      <label v-if="edicion.id" class="check"><input v-model="edicion.activo" type="checkbox" /> {{ t('Active (shown in the screens and the matrix)') }}</label>
    </form>
    <template #pie>
      <button type="button" class="btn separar" @click="edicion = null">{{ t('Cancel') }}</button>
      <button type="submit" class="btn btn-primario" form="form-tipo">{{ t('Save') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.form-tipo { display: flex; flex-direction: column; gap: 14px; }
fieldset.campo { border: 0; padding: 0; margin: 0; }
.opciones-sujeto { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 6px; }
:deep(tr.apagada > td) { opacity: 0.6; }
</style>
