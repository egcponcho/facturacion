<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import CeldaEditable from '../components/CeldaEditable.vue'
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
    avisar(t.activa ? 'Plantilla desactivada; ya no aparecerá al empacar.' : 'Plantilla activada.')
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
    avisar(`Plantilla “${nueva.nombre}” creada.`)
    Object.assign(nueva, vacia())
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
      <h1>Plantillas de caja</h1>
      <p>Sirven para llenar rápido cantidad por caja, medidas y pesos. No son obligatorias y cambiarlas no modifica las cajas ya creadas.</p>
    </div>
  </div>

  <p v-if="esInterno() && !sesion.proveedorId" class="nota">Elige un proveedor arriba para ver y editar sus plantillas.</p>

  <template v-else>
    <section class="panel">
      <div class="panel-cabeza"><h2>Nueva plantilla{{ esInterno() ? ` para ${nombreProveedor(sesion.proveedorId)}` : '' }}</h2></div>
      <form class="rejilla-campos" @submit.prevent="crear">
        <label class="campo"><span class="req">Nombre</span><input v-model="nueva.nombre" required /></label>
        <label class="campo"><span class="req">Cantidad por caja</span><input v-model="nueva.cantidad_por_caja" type="number" min="1" required /></label>
        <label class="campo"><span class="req">Unidad</span>
          <select v-model="nueva.unidad"><option value="PAR">Pares</option><option value="UN">Unidades</option><option value="CJ">Cajas prepack (curvas)</option></select>
        </label>
        <label class="campo"><span>Largo cm</span><input v-model="nueva.largo" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Ancho cm</span><input v-model="nueva.ancho" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Alto cm</span><input v-model="nueva.alto" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Peso neto kg</span><input v-model="nueva.peso_neto" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Peso bruto kg</span><input v-model="nueva.peso_bruto" type="number" min="0" step="any" /></label>
        <label class="campo"><span>Tara (caja vacía) kg</span><input v-model="nueva.tara" type="number" min="0" step="any" /></label>
        <div class="campo" style="justify-content: flex-end"><button class="btn btn-primario" type="submit">Crear plantilla</button></div>
      </form>
      <p class="ayuda mt">La tara ayuda a estimar mejor el peso bruto de las cajas parciales.</p>
    </section>

    <div class="filtros mt">
      <label class="check"><input v-model="incluirInactivas" type="checkbox" /> Mostrar inactivas</label>
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla">
        <thead>
          <tr>
            <ThOrden campo="nombre" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Nombre</ThOrden>
            <ThOrden campo="cantidad_por_caja" :orden="tabla.estado.orden" num @ordenar="tabla.ordenar">Por caja</ThOrden>
            <ThOrden campo="unidad" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Unidad</ThOrden>
            <th class="num">Largo</th>
            <th class="num">Ancho</th>
            <th class="num">Alto</th>
            <th class="num">Neto kg</th>
            <th class="num">Bruto kg</th>
            <th class="num">Tara kg</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in tabla.filas.value" :key="t.id" :class="{ apagado: !t.activa }">
            <td style="min-width: 200px"><CeldaEditable :valor="t.nombre" :guardar="guardarCampo(t, 'nombre')" etiqueta="Nombre" /></td>
            <td class="num" style="width: 90px"><CeldaEditable tipo="number" :min="1" paso="1" :valor="t.cantidad_por_caja" :guardar="guardarCampo(t, 'cantidad_por_caja')" etiqueta="Cantidad por caja" /></td>
            <td>
              <select class="celda" :value="t.unidad" aria-label="Unidad" @change="guardarCampo(t, 'unidad')($event.target.value).catch(() => {})">
                <option value="PAR">Pares</option><option value="UN">Unidades</option><option value="CJ">Cajas prepack</option>
              </select>
            </td>
            <td v-for="c in ['largo', 'ancho', 'alto', 'peso_neto', 'peso_bruto', 'tara']" :key="c" class="num" style="width: 88px">
              <CeldaEditable tipo="number" :min="0" :valor="t[c]" :guardar="guardarCampo(t, c)" :etiqueta="c" />
            </td>
            <td><button class="btn btn-chico" @click="alternarActiva(t)">{{ t.activa ? 'Desactivar' : 'Activar' }}</button></td>
          </tr>
          <tr v-if="!lista.length"><td colspan="10" class="vacio">No hay plantillas. Crea la primera arriba o guárdala desde una caja en un packing list.</td></tr>
        </tbody>
      </table>
    </div>
    <Paginacion :page="tabla.estado.pagina" :size="tabla.estado.porPagina" :total="tabla.total.value"
                @cambiar="(p) => (tabla.estado.pagina = p)" @tamano="(t) => (tabla.estado.porPagina = t)" />
  </template>
</template>
