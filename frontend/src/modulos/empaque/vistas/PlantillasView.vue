<script setup>
import { codigosUnidad, etiquetaUnidad, pasoCantidad } from '@/nucleo/unidades.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { api } from '@/nucleo/api'
import CeldaEditable from '@/componentes/CeldaEditable.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { eligeProveedor, esInterno, nombreProveedor, sesion } from '@/stores/sesion'
import { avisar, errorApi, guardando } from '@/stores/ui'

const lista = ref([])
const incluirInactivas = ref(false)
const cargando = ref(false)
// Cada plantilla es una fila editable; las columnas filtran por sus valores como el resto de tablas
const columnas = computed(() => [
  { clave: 'nombre', texto: t('Name'), fija: true, prioridad: 1 },
  { clave: 'cantidad_por_caja', texto: t('Per carton'), num: true, prioridad: 1 },
  { clave: 'unidad', texto: t('Unit'), prioridad: 2, textoValor: (v) => etiquetaUnidad(v) },
  { clave: 'largo', texto: t('Length'), num: true, prioridad: 3 },
  { clave: 'ancho', texto: t('Width'), num: true, prioridad: 3 },
  { clave: 'alto', texto: t('Height'), num: true, prioridad: 3 },
  { clave: 'tipo_empaque_id', texto: t('Packaging type'), prioridad: 3, textoValor: (v) => tx(tipos.value.find((x) => x.id === Number(v))?.nombre || t('Default')) },
  { clave: 'tara', texto: t('Tare kg'), num: true, prioridad: 3 },
  { clave: 'activa', texto: t('Status'), prioridad: 2, opciones: [[true, t('Active')], [false, t('Inactive')]] },
])
const vacia = () => ({ nombre: '', cantidad_por_caja: '', unidad: 'PAR', tipo_empaque_id: '', largo: '', ancho: '', alto: '', tara: '' })
const nueva = reactive(vacia())
const formAbierto = ref(false) // alta en ventana emergente
const NUMERICOS = ['largo', 'ancho', 'alto', 'tara']
// La plantilla guarda solo el empaque (tipo, medidas y tara): el neto sale del peso de cada artículo
const tipos = ref([])
api.get('/tipos-empaque').then((r) => (tipos.value = r)).catch(() => {})
function elegirTipo(id) {
  nueva.tipo_empaque_id = id
  const x = tipos.value.find((y) => y.id === Number(id))
  if (x) for (const c of NUMERICOS) if (nueva[c] === '' && x[c] != null) nueva[c] = x[c]
}

async function cargar() {
  if (!sesion.proveedorId) {
    lista.value = []
    return
  }
  cargando.value = true
  try {
    lista.value = await api.get('/plantillas', { proveedor_id: sesion.proveedorId, incluir_inactivas: incluirInactivas.value })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}

const guardarCampo = (plantilla, campo) => async (valor) => {
  try {
    await guardando(api.patch(`/plantillas/${plantilla.id}`, { [campo]: valor }))
    await cargar()
  } catch (e) {
    errorApi(e)
    throw e
  }
}

async function alternarActiva(plantilla) {
  try {
    await api.patch(`/plantillas/${plantilla.id}`, { activa: !plantilla.activa })
    avisar(plantilla.activa ? t('Template deactivated; it will no longer appear when packing.') : t('Template activated.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

async function crear() {
  const datos = { proveedor_id: sesion.proveedorId, nombre: nueva.nombre, unidad: nueva.unidad, cantidad_por_caja: Number(nueva.cantidad_por_caja),
    tipo_empaque_id: nueva.tipo_empaque_id || null }
  for (const c of NUMERICOS) datos[c] = nueva[c] === '' ? null : Number(nueva[c])
  try {
    await api.post('/plantillas', datos)
    avisar(t('Template “{0}” created.', [nueva.nombre]))
    Object.assign(nueva, vacia())
    formAbierto.value = false
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

onMounted(cargar)
watch([() => sesion.proveedorId, incluirInactivas], cargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Carton templates') }}</h1>
      <p>{{ t('They quickly fill in the quantity per carton, packaging type, dimensions and tare. They are optional, and changing them does not modify cartons already created. With a casepack or a prepack the quantity per carton comes from the PO; with an inner pack, the template quantity must be a multiple of it.') }}</p>
    </div>
  </div>

  <p v-if="eligeProveedor() && !sesion.proveedorId" class="nota">{{ t('Choose a supplier above to see and edit its templates.') }}</p>

  <template v-else>

    <TablaDatos tabla="plantillas_empaque" :columnas="columnas" :filas="lista" :cargando="cargando" orden-inicial="nombre:asc"
                :clase-fila="(x) => ({ apagada: !x.activa })" :externos="{ inactivas: incluirInactivas ? '1' : '' }" :etiqueta="t('Carton templates')"
                @vista="(x) => (incluirInactivas = x.inactivas === '1')">
      <template #filtros>
        <label class="check"><input v-model="incluirInactivas" type="checkbox" /> {{ t('Show inactive') }}</label>
        <button type="button" class="btn btn-primario separar" @click="formAbierto = true"><Icono nombre="mas" />{{ t('New template') }}</button>
      </template>
      <template #celda-nombre="{ fila: x }"><div class="col-nombre"><CeldaEditable :valor="x.nombre" :guardar="guardarCampo(x, 'nombre')" :etiqueta="t('Name')" /></div></template>
      <template #celda-cantidad_por_caja="{ fila: x }"><div class="col-num"><CeldaEditable tipo="number" :min="1" paso="1" :valor="x.cantidad_por_caja" :guardar="guardarCampo(x, 'cantidad_por_caja')" :etiqueta="t('Quantity per carton')" /></div></template>
      <template #celda-unidad="{ fila: x }">
        <Seleccion class="celda" :value="x.unidad" :aria-label="t('Unit')" @change="guardarCampo(x, 'unidad')($event).catch(() => {})">
          <option v-for="u in codigosUnidad()" :key="u" :value="u">{{ etiquetaUnidad(u) }}</option>
        </Seleccion>
      </template>
      <template v-for="c in ['largo', 'ancho', 'alto', 'tara']" :key="c" #[`celda-${c}`]="{ fila: x }">
        <div class="col-num"><CeldaEditable tipo="number" :min="0" :valor="x[c]" :guardar="guardarCampo(x, c)" :etiqueta="c === 'tara' ? t('Tare kg') : tx(c)" /></div>
      </template>
      <template #celda-tipo_empaque_id="{ fila: x }">
        <Seleccion class="celda col-tipo" :value="x.tipo_empaque_id || ''" :aria-label="t('Packaging type')" @change="guardarCampo(x, 'tipo_empaque_id')($event || null).catch(() => {})">
          <option value="">{{ t('Default') }}</option>
          <option v-for="y in tipos" :key="y.id" :value="y.id">{{ tx(y.nombre) }}</option>
        </Seleccion>
      </template>
      <template #celda-activa="{ fila: x }"><span class="etiqueta ms-0" :class="x.activa ? 'ok' : ''">{{ x.activa ? t('Active') : t('Inactive') }}</span></template>
      <template #acciones="{ fila: x }"><button type="button" class="btn btn-chico" @click="alternarActiva(x)">{{ tx(x.activa ? t('Deactivate') : t('Activate')) }}</button></template>
      <template #vacio>{{ t('No templates. Create the first one above or save one from a carton in a packing list.') }}</template>
    </TablaDatos>
  </template>
  <Modal v-if="formAbierto" :titulo="t('New template{0}', [esInterno() ? t(' for {0}', [nombreProveedor(sesion.proveedorId)]) : ''])" ancho="680px" @cerrar="formAbierto = false">
      <form id="form-plantilla" class="rejilla-campos" @submit.prevent="crear">
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="nueva.nombre" required /></label>
        <label class="campo"><span class="req">{{ t('Quantity per carton') }}</span><input v-model="nueva.cantidad_por_caja" type="number" :min="pasoCantidad(nueva.unidad)" :step="pasoCantidad(nueva.unidad)" required /></label>
        <label class="campo"><span class="req">{{ t('Unit') }}</span>
          <Seleccion v-model="nueva.unidad"><option v-for="u in codigosUnidad()" :key="u" :value="u">{{ etiquetaUnidad(u) }}</option></Seleccion>
        </label>
        <label class="campo"><span>{{ t('Packaging type') }}</span>
          <Seleccion :model-value="nueva.tipo_empaque_id" @update:model-value="elegirTipo"><option value="">{{ t('Default') }}</option>
            <option v-for="x in tipos" :key="x.id" :value="x.id">{{ tx(x.nombre) }}</option></Seleccion>
        </label>
        <label class="campo"><span>{{ t('Length cm') }}</span><input v-model="nueva.largo" type="number" min="0" step="any" /></label>
        <label class="campo"><span>{{ t('Width cm') }}</span><input v-model="nueva.ancho" type="number" min="0" step="any" /></label>
        <label class="campo"><span>{{ t('Height cm') }}</span><input v-model="nueva.alto" type="number" min="0" step="any" /></label>
        <label class="campo"><span>{{ t('Tare (empty carton) kg') }}</span><input v-model="nueva.tara" type="number" min="0" step="any" /></label>
      </form>
      <p class="ayuda mt">{{ t('Only the packaging is saved: the net weight comes from the unit weight of each item and the gross weight adds the tare of each packaging level (carton, inner packs, pallet).') }}</p>
    <template #pie>
      <button class="btn" @click="formAbierto = false">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-plantilla">{{ t('Create template') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.col-nombre { min-width: 200px; }
.col-num { width: 90px; }
.col-tipo { min-width: 150px; }
:deep(tr.apagada > td) { opacity: 0.6; }
</style>
