<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import CeldaEditable from '../components/CeldaEditable.vue'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import Paginacion from '../components/Paginacion.vue'
import ThOrden from '../components/ThOrden.vue'
import { useTabla } from '../composables/useTabla'
import { esInterno, nombreProveedor, sesion } from '../stores/sesion'
import { avisar, errorApi, guardando } from '../stores/ui'

const lista = ref([])
const incluirInactivas = ref(false)
const tabla = useTabla(lista, { orden: 'nombre:asc' })
const vacia = () => ({ nombre: '', cantidad_por_caja: '', unidad: 'PAR', largo: '', ancho: '', alto: '', peso_neto: '', peso_bruto: '', tara: '' })
const nueva = reactive(vacia())
const formAbierto = ref(false) // alta en ventana emergente
const NUMERICOS = ['largo', 'ancho', 'alto', 'peso_neto', 'peso_bruto', 'tara']

async function cargar() {
  if (!sesion.proveedorId) {
    lista.value = []
    return
  }
  try {
    lista.value = await api.get('/plantillas', { proveedor_id: sesion.proveedorId, incluir_inactivas: incluirInactivas.value })
  } catch (e) {
    errorApi(e)
  }
}

const guardarCampo = (t, campo) => async (valor) => {
  try {
    await guardando(api.patch(`/plantillas/${t.id}`, { [campo]: valor }))
    await cargar()
  } catch (e) {
    errorApi(e)
    throw e
  }
}

async function alternarActiva(t) {
  try {
    await api.patch(`/plantillas/${t.id}`, { activa: !t.activa })
    avisar(t.activa ? 'Template deactivated; it will no longer appear when packing.' : 'Template activated.')
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

async function crear() {
  const datos = { proveedor_id: sesion.proveedorId, nombre: nueva.nombre, unidad: nueva.unidad, cantidad_por_caja: Number(nueva.cantidad_por_caja) }
  for (const c of NUMERICOS) datos[c] = nueva[c] === '' ? null : Number(nueva[c])
  try {
    await api.post('/plantillas', datos)
    avisar(`Template “${nueva.nombre}” created.`)
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
      <h1>Carton templates</h1>
      <p>They quickly fill in the quantity per carton, dimensions and weights. They are optional, and changing them does not modify cartons already created. With a casepack or a prepack the quantity per carton comes from the PO; with an inner pack, the template quantity must be a multiple of it.</p>
    </div>
  </div>

  <p v-if="esInterno() && !sesion.proveedorId" class="nota">Choose a supplier above to see and edit its templates.</p>

  <template v-else>

    <div class="filtros">
      <label class="check"><input v-model="incluirInactivas" type="checkbox" /> Show inactive</label>
      <button class="btn btn-primario separar" @click="formAbierto = true"><Icono nombre="mas" />New template</button>
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla">
        <thead>
          <tr>
            <ThOrden campo="nombre" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Name</ThOrden>
            <ThOrden campo="cantidad_por_caja" :orden="tabla.estado.orden" num @ordenar="tabla.ordenar">Per carton</ThOrden>
            <ThOrden campo="unidad" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Unit</ThOrden>
            <th class="num">Length</th>
            <th class="num">Width</th>
            <th class="num">Height</th>
            <th class="num">Net kg</th>
            <th class="num">Gross kg</th>
            <th class="num">Tare kg</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in tabla.filas.value" :key="t.id" :class="{ apagado: !t.activa }">
            <td style="min-width: 200px"><CeldaEditable :valor="t.nombre" :guardar="guardarCampo(t, 'nombre')" etiqueta="Name" /></td>
            <td class="num" style="width: 90px"><CeldaEditable tipo="number" :min="1" paso="1" :valor="t.cantidad_por_caja" :guardar="guardarCampo(t, 'cantidad_por_caja')" etiqueta="Quantity per carton" /></td>
            <td>
              <select class="celda" :value="t.unidad" aria-label="Unit" @change="guardarCampo(t, 'unidad')($event.target.value).catch(() => {})">
                <option value="PAR">Pairs</option><option value="UN">Units</option><option value="CJ">Prepack cartons</option>
              </select>
            </td>
            <td v-for="c in ['largo', 'ancho', 'alto', 'peso_neto', 'peso_bruto', 'tara']" :key="c" class="num" style="width: 88px">
              <CeldaEditable tipo="number" :min="0" :valor="t[c]" :guardar="guardarCampo(t, c)" :etiqueta="c" />
            </td>
            <td><button class="btn btn-chico" @click="alternarActiva(t)">{{ t.activa ? 'Deactivate' : 'Activate' }}</button></td>
          </tr>
          <tr v-if="!lista.length"><td colspan="10" class="vacio">No templates. Create the first one above or save one from a carton in a packing list.</td></tr>
        </tbody>
      </table>
    </div>
    <Paginacion :page="tabla.estado.pagina" :size="tabla.estado.porPagina" :total="tabla.total.value"
                @cambiar="(p) => (tabla.estado.pagina = p)" @tamano="(t) => (tabla.estado.porPagina = t)" />
  </template>
  <Modal v-if="formAbierto" :titulo="`New template${esInterno() ? ` for ${nombreProveedor(sesion.proveedorId)}` : ''}`" ancho="680px" @cerrar="formAbierto = false">
      <form id="form-plantilla" class="rejilla-campos" @submit.prevent="crear">
        <label class="campo"><span class="req">Name</span><input v-model="nueva.nombre" required /></label>
        <label class="campo"><span class="req">Quantity per carton</span><input v-model="nueva.cantidad_por_caja" type="number" min="1" required /></label>
        <label class="campo"><span class="req">Unit</span>
          <select v-model="nueva.unidad"><option value="PAR">Pairs</option><option value="UN">Units</option><option value="CJ">Prepack cartons (size runs)</option></select>
        </label>
        <label class="campo"><span>Length cm</span><input v-model="nueva.largo" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Width cm</span><input v-model="nueva.ancho" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Height cm</span><input v-model="nueva.alto" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Net weight kg</span><input v-model="nueva.peso_neto" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Gross weight kg</span><input v-model="nueva.peso_bruto" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Tare (empty carton) kg</span><input v-model="nueva.tara" type="number" min="0" step="any" /></label>
      </form>
      <p class="ayuda mt">The tare helps estimate the gross weight of partial cartons.</p>
    <template #pie>
      <button class="btn" @click="formAbierto = false">Cancel</button>
      <button class="btn btn-primario" type="submit" form="form-plantilla">Create template</button>
    </template>
  </Modal>
</template>
