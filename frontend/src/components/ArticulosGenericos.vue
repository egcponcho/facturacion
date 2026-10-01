<script setup>
import { t, tx } from '../i18n/index.js'
import { puede } from '../stores/sesion'
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { plural } from '../utils'
import { errorApi } from '../stores/ui'
import EstadoBadge from './EstadoBadge.vue'
import GenericoModal from './GenericoModal.vue'
import Icono from './Icono.vue'
import Paginacion from './Paginacion.vue'
import ThOrden from './ThOrden.vue'
import { siguienteOrden } from '../composables/useTabla'
import { filasDefecto } from '../stores/preferencias'

// Vista compacta de artículos: un renglón por genérico (estilo-color) con sus
// datos maestros; al desplegarlo se ven sus tallas y prepacks, como las líneas
// de una orden. La vista de listado (un renglón por artículo) sigue en Master data.
const props = defineProps({ q: { type: String, default: '' }, extra: { type: Object, default: () => ({}) }, recarga: { type: Number, default: 0 } })
const emit = defineEmits(['editar-articulo', 'eliminar-articulo', 'desglose', 'cambio'])
const datos = ref({ items: [], total: 0 })
const f = reactive({ orden: '', page: 1, size: filasDefecto() })
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
    <table class="tabla" v-tarjetas>
      <thead>
        <tr>
          <th style="width: 36px"></th>
          <ThOrden campo="generico" :orden="f.orden" @ordenar="ordenar">{{ t('Generic') }}</ThOrden>
          <ThOrden campo="estilo" :orden="f.orden" @ordenar="ordenar">{{ t('Style') }}</ThOrden>
          <ThOrden campo="color" :orden="f.orden" @ordenar="ordenar">{{ t('Color') }}</ThOrden>
          <th>{{ t('Brand') }}</th>
          <th>{{ t('Group') }}</th>
          <th>{{ t('Supplier') }}</th>
          <th>{{ t('Sizes') }}</th>
          <th :title="t('Invoice and packing list description')">{{ t('Description · HS code') }}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="g in datos.items" :key="g.generico">
          <tr :class="{ seleccionada: abiertas.has(g.generico) }">
            <td>
              <button class="btn-icono" type="button" :aria-expanded="abiertas.has(g.generico)" :aria-label="t('See the items of generic {0}', [g.generico])" @click="alternar(g.generico)">
                <Icono :nombre="abiertas.has(g.generico) ? 'abajo' : 'derecha'" :tam="16" />
              </button>
            </td>
            <td><strong class="codigo">{{ tx(g.generico) }}</strong><span class="sub">{{ tx(g.unidad) }}</span></td>
            <td class="fuerte">{{ tx(g.estilo) }}</td>
            <td>{{ tx(g.color) }}</td>
            <td>{{ tx(g.marca) }}</td>
            <td class="codigo">{{ tx(g.grupo) }}</td>
            <td>{{ tx(g.proveedor) }}</td>
            <td>
              <span class="fuerte">{{ tx(g.rango_tallas || '—') }}</span>
              <span class="sub">{{ plural(g.n_tallas, t('size'), t('sizes')) }}<template v-if="g.n_prepacks"> · {{ plural(g.n_prepacks, t('prepack'), t('prepacks')) }}</template></span>
            </td>
            <td>
              <span>{{ tx(g.descripcion_comercial || '—') }}</span>
              <router-link :to="`/productos/${g.producto_id}`" class="sub enlace" :title="t('Technical sheet of {0}', [g.generico])">
                <span v-if="g.codigo" class="codigo-sac">{{ tx(g.codigo) }}</span><EstadoBadge v-else :estado="g.estado" />
              </router-link>
            </td>
            <td class="num" style="white-space: nowrap">
              <button v-if="puede('catalogos.crear')" class="btn btn-chico" :title="t('Add sizes to this generic')" @click="modal = { generico: g.generico }"><Icono nombre="mas" :tam="13" />{{ t('Sizes') }}</button>
              <button v-if="puede('catalogos.editar')" class="btn-icono" :aria-label="t('Edit generic {0}', [g.generico])" :title="t('Edit the generic (applies to all its sizes)')" @click="modal = { generico: g.generico, editar: true }"><Icono nombre="editar" :tam="16" /></button>
            </td>
          </tr>
          <tr v-if="abiertas.has(g.generico)" class="fila-hija">
            <td colspan="10">
              <div class="subtabla">
                <div class="tabla-marco">
                  <table class="tabla" v-tarjetas>
                    <thead>
                      <tr><th>{{ t('Item code') }}</th><th>{{ t('Size code') }}</th><th>{{ t('Type') }}</th><th>{{ t('Size') }}</th><th>UPC</th><th>{{ t('Supplier SKU') }}</th><th>{{ t('Active') }}</th><th></th></tr>
                    </thead>
                    <tbody>
                      <tr v-if="!detalles[g.generico]"><td colspan="8" class="vacio">{{ t('Loading…') }}</td></tr>
                      <tr v-for="a in detalles[g.generico] || []" :key="a.id">
                        <td class="codigo fuerte">{{ tx(a.sku) }}</td>
                        <td class="codigo">{{ tx(a.sku.slice(8)) }}</td>
                        <td><span class="etiqueta" :class="{ acento: a.tipo === 'PREPACK' }">{{ tx(a.tipo === 'PREPACK' ? t('Prepack') : t('Solid')) }}</span></td>
                        <td>{{ tx(a.talla) }}</td>
                        <td class="codigo">{{ tx(a.upc || '—') }}</td>
                        <td class="codigo">{{ tx(a.sku_proveedor || '—') }}</td>
                        <td><span class="etiqueta" :class="a.activo ? 'ok' : ''">{{ tx(a.activo ? t('Yes') : t('No')) }}</span></td>
                        <td class="num" style="white-space: nowrap">
                          <button v-if="a.tipo === 'PREPACK'" class="btn btn-chico" :title="t('See the breakdown')" @click="emit('desglose', a)"><Icono nombre="lupa" :tam="13" />{{ t('Breakdown') }}</button>
                          <button v-if="puede('catalogos.editar')" class="btn-icono" :aria-label="t('Edit item {0}', [a.sku])" :title="t('Edit')" @click="emit('editar-articulo', a)"><Icono nombre="editar" :tam="15" /></button>
                          <button v-if="puede('catalogos.eliminar')" class="btn-icono" style="color: var(--error)" :aria-label="t('Delete item {0}', [a.sku])" :title="t('Delete')" @click="emit('eliminar-articulo', a)"><Icono nombre="basura" :tam="15" /></button>
                        </td>
                      </tr>
                      <tr v-if="detalles[g.generico] && !detalles[g.generico].length"><td colspan="8" class="vacio">{{ t('This generic has no sizes yet.') }}</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="!datos.items.length"><td colspan="10" class="vacio">{{ t('No generics match these filters.') }}</td></tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="f.page" :size="f.size" :total="datos.total" @cambiar="(p) => { f.page = p; cargar() }" @tamano="(t) => (f.size = t)" />
  <GenericoModal v-if="modal" :generico="modal.generico" :editar="!!modal.editar" @cerrar="modal = null" @listo="listo" />
</template>
