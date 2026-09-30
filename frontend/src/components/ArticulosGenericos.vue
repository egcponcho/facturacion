<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { errorApi } from '../stores/ui'
import EstadoBadge from './EstadoBadge.vue'
import GenericoModal from './GenericoModal.vue'
import Icono from './Icono.vue'
import Paginacion from './Paginacion.vue'
import ThOrden from './ThOrden.vue'
import { siguienteOrden } from '../composables/useTabla'

// Vista compacta de artículos: un renglón por genérico (estilo-color) con sus
// datos maestros; al desplegarlo se ven sus tallas y prepacks, como las líneas
// de una orden. La vista de listado (un renglón por artículo) sigue en Master data.
const props = defineProps({ q: { type: String, default: '' }, extra: { type: Object, default: () => ({}) }, recarga: { type: Number, default: 0 } })
const emit = defineEmits(['editar-articulo', 'eliminar-articulo', 'desglose', 'cambio'])
const datos = ref({ items: [], total: 0 })
const f = reactive({ orden: '', page: 1, size: 15 })
const abiertas = reactive(new Set())
const detalles = reactive({})
const modal = ref(null) // { generico, editar }

async function cargar() {
  const { marca_id, grupo_id, proveedor_id, unidad } = props.extra
  try {
    datos.value = await api.get('/catalogos/genericos', { q: props.q, marca_id, grupo_id, proveedor_id, unidad, orden: f.orden, page: f.page, size: f.size })
    for (const g of [...abiertas]) if (datos.value.items.some((x) => x.generico === g)) cargarTallas(g)
    else abiertas.delete(g)
  } catch (e) {
    errorApi(e)
  }
}
async function cargarTallas(gen) {
  try {
    detalles[gen] = (await api.get('/catalogos/articulos', { q: gen, size: 200, orden: 'sku:asc' })).items.filter((a) => a.sku.startsWith(gen))
  } catch (e) {
    errorApi(e)
  }
}
async function alternar(gen) {
  if (abiertas.has(gen)) return abiertas.delete(gen)
  abiertas.add(gen)
  if (!detalles[gen]) await cargarTallas(gen)
}
function ordenar(campo) {
  f.orden = siguienteOrden(f.orden, campo)
  f.page = 1
  cargar()
}
function listo() {
  const gen = modal.value.generico
  modal.value = null
  if (gen) {
    delete detalles[gen]
    abiertas.add(gen)
  }
  emit('cambio')
  cargar()
}

// La vista madre avisa con "recarga" cuando cambian los filtros (ya con espera) o los datos
watch(() => [props.q, JSON.stringify(props.extra)], () => { f.page = 1 })
watch(() => props.recarga, () => { for (const g of Object.keys(detalles)) delete detalles[g]; cargar() })
watch(() => f.size, () => { f.page = 1; cargar() })
cargar()
</script>

<template>
  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <th style="width: 36px"></th>
          <ThOrden campo="generico" :orden="f.orden" @ordenar="ordenar">Generic</ThOrden>
          <ThOrden campo="estilo" :orden="f.orden" @ordenar="ordenar">Style</ThOrden>
          <ThOrden campo="color" :orden="f.orden" @ordenar="ordenar">Color</ThOrden>
          <th>Brand</th>
          <th>Group</th>
          <th>Supplier</th>
          <th>Sizes</th>
          <th title="Invoice and packing list description">Description · HS code</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="g in datos.items" :key="g.generico">
          <tr :class="{ seleccionada: abiertas.has(g.generico) }">
            <td>
              <button class="btn-icono" type="button" :aria-expanded="abiertas.has(g.generico)" :aria-label="`See the items of generic ${g.generico}`" @click="alternar(g.generico)">
                <Icono :nombre="abiertas.has(g.generico) ? 'abajo' : 'derecha'" :tam="16" />
              </button>
            </td>
            <td><strong class="codigo">{{ g.generico }}</strong><span class="sub">{{ g.unidad }}</span></td>
            <td class="fuerte">{{ g.estilo }}</td>
            <td>{{ g.color }}</td>
            <td>{{ g.marca }}</td>
            <td class="codigo">{{ g.grupo }}</td>
            <td>{{ g.proveedor }}</td>
            <td>
              <span class="fuerte">{{ g.rango_tallas || '—' }}</span>
              <span class="sub">{{ g.n_tallas }} {{ g.n_tallas === 1 ? 'size' : 'sizes' }}<template v-if="g.n_prepacks"> · {{ g.n_prepacks }} {{ g.n_prepacks === 1 ? 'prepack' : 'prepacks' }}</template></span>
            </td>
            <td>
              <span>{{ g.descripcion_comercial || '—' }}</span>
              <router-link :to="`/productos/${g.producto_id}`" class="sub enlace" :title="`Technical sheet of ${g.generico}`">
                <span v-if="g.codigo" class="codigo-sac">{{ g.codigo }}</span><EstadoBadge v-else :estado="g.estado" />
              </router-link>
            </td>
            <td class="num" style="white-space: nowrap">
              <button class="btn btn-chico" title="Add sizes to this generic" @click="modal = { generico: g.generico }"><Icono nombre="mas" :tam="13" />Sizes</button>
              <button class="btn-icono" :aria-label="`Edit generic ${g.generico}`" title="Edit the generic (applies to all its sizes)" @click="modal = { generico: g.generico, editar: true }"><Icono nombre="editar" :tam="16" /></button>
            </td>
          </tr>
          <tr v-if="abiertas.has(g.generico)" class="fila-hija">
            <td colspan="10">
              <div class="subtabla">
                <div class="tabla-marco">
                  <table class="tabla">
                    <thead>
                      <tr><th>Item code</th><th>Size code</th><th>Type</th><th>Size</th><th>UPC</th><th>Supplier SKU</th><th>Active</th><th></th></tr>
                    </thead>
                    <tbody>
                      <tr v-if="!detalles[g.generico]"><td colspan="8" class="vacio">Loading…</td></tr>
                      <tr v-for="a in detalles[g.generico] || []" :key="a.id">
                        <td class="codigo fuerte">{{ a.sku }}</td>
                        <td class="codigo">{{ a.sku.slice(8) }}</td>
                        <td><span class="etiqueta" :class="{ acento: a.tipo === 'PREPACK' }">{{ a.tipo === 'PREPACK' ? 'Prepack' : 'Solid' }}</span></td>
                        <td>{{ a.talla }}</td>
                        <td class="codigo">{{ a.upc || '—' }}</td>
                        <td class="codigo">{{ a.sku_proveedor || '—' }}</td>
                        <td><span class="etiqueta" :class="a.activo ? 'ok' : ''">{{ a.activo ? 'Yes' : 'No' }}</span></td>
                        <td class="num" style="white-space: nowrap">
                          <button v-if="a.tipo === 'PREPACK'" class="btn btn-chico" title="See the breakdown" @click="emit('desglose', a)"><Icono nombre="lupa" :tam="13" />Breakdown</button>
                          <button class="btn-icono" :aria-label="`Edit item ${a.sku}`" title="Edit" @click="emit('editar-articulo', a)"><Icono nombre="editar" :tam="15" /></button>
                          <button class="btn-icono" style="color: var(--error)" :aria-label="`Delete item ${a.sku}`" title="Delete" @click="emit('eliminar-articulo', a)"><Icono nombre="basura" :tam="15" /></button>
                        </td>
                      </tr>
                      <tr v-if="detalles[g.generico] && !detalles[g.generico].length"><td colspan="8" class="vacio">This generic has no sizes yet.</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="!datos.items.length"><td colspan="10" class="vacio">No generics match these filters.</td></tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="f.page" :size="f.size" :total="datos.total" @cambiar="(p) => { f.page = p; cargar() }" @tamano="(t) => (f.size = t)" />
  <GenericoModal v-if="modal" :generico="modal.generico" :editar="!!modal.editar" @cerrar="modal = null" @listo="listo" />
</template>
