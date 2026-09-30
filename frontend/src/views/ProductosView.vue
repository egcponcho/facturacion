<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import Paginacion from '../components/Paginacion.vue'
import ThOrden from '../components/ThOrden.vue'
import { clasificarVarios, M } from '../clasificacion/useClasificacion'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, puede, sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { useSeleccion } from '../utils'

// Un producto es un estilo-color de un proveedor: su ficha técnica y su
// clasificación arancelaria valen para todas sus tallas (SKU) y prepacks.
const route = useRoute()
const router = useRouter()
const interno = esInterno()
const filtros = reactive({
  estado: route.query.estado ?? (interno ? 'sugerida' : 'pendientes'),
  q: route.query.q || '',
  marca_id: '',
  orden: '',
  page: 1,
  size: 25,
})
const datos = ref({ items: [], total: 0, kpis: {} })
const opciones = ref({ marcas: [] })
const cargando = ref(false)
const ocupado = ref(false)
const sel = useSeleccion()

// Pocas vistas, en el orden en que se trabaja
const VISTAS = computed(() => {
  const k = datos.value.kpis || {}
  return [
    ['pendientes', interno ? 'To classify' : 'To complete', k.pendientes],
    ...(interno ? [['sugerida', 'Ready to approve', k.sugerida]] : []),
    ['observado', interno ? 'Returned' : 'Returned to you', k.observado],
    ['aprobados', 'Approved', k.aprobados],
    ['', 'All', k.total],
  ]
})

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/productos', { ...filtros, proveedor_id: sesion.proveedorId })
    sel.podar(datos.value.items.map((p) => p.id))
    router.replace({ query: { estado: filtros.estado, ...(filtros.q && { q: filtros.q }) } })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
}
function recargar() {
  filtros.page = 1
  cargar()
}
function ordenar(campo) {
  filtros.orden = siguienteOrden(filtros.orden, campo)
  recargar()
}

const ids = computed(() => datos.value.items.map((p) => p.id))
const elegidos = computed(() => datos.value.items.filter((p) => sel.tiene(p.id)))
const porAprobar = computed(() => elegidos.value.filter((p) => p.estado === 'sugerida' && p.ficha_completa))

async function clasificar() {
  ocupado.value = true
  try {
    const r = await clasificarVarios(elegidos.value.filter((p) => !['aprobado', 'corregido'].includes(p.estado)).map((p) => p.id))
    avisar(`${r.clasificados} ${r.clasificados === 1 ? 'product' : 'products'} classified.`)
    sel.limpiar()
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function aprobar() {
  ocupado.value = true
  try {
    const r = await api.post('/productos/aprobar', { ids: porAprobar.value.map((p) => p.id) })
    if (r.errores.length) avisar(`${r.aprobados} approved; ${r.errores.length} need attention.`, 'error', r.errores.map((e) => e.mensaje))
    else avisar(`${r.aprobados} ${r.aprobados === 1 ? 'product' : 'products'} approved.`)
    sel.limpiar()
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function exportar(formato) {
  try {
    await api.descargar('/productos/exportar', `products.${formato}`, { ...filtros, page: undefined, size: undefined, formato, proveedor_id: sesion.proveedorId })
  } catch (e) {
    errorApi(e)
  }
}

const codigoDe = (p) => p.codigo || p.sugerido
const descCorta = (c) => {
  const d = M.descDe(c)
  return d && d.length > 60 ? `${d.slice(0, 58)}…` : d
}

onMounted(async () => {
  cargar()
  try {
    opciones.value = await api.get('/productos/opciones')
  } catch {
    /* los filtros extra son opcionales */
  }
})
watch(() => sesion.proveedorId, recargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>Products</h1>
      <p v-if="interno">Technical sheets and tariff classification. Approved HS codes flow to purchase orders and invoices for each destination country.</p>
      <p v-else>Complete the technical sheet of each product. Customs uses it to classify it; the approved code appears on your orders and invoices.</p>
    </div>
    <div class="acciones">
      <button class="btn btn-fantasma" @click="exportar('xlsx')"><Icono nombre="descargar" />Excel</button>
      <button class="btn btn-fantasma" @click="exportar('pdf')"><Icono nombre="descargar" />PDF</button>
    </div>
  </div>

  <div class="filtros">
    <div class="segmentos" role="group" aria-label="View">
      <button v-for="[v, t, n] in VISTAS" :key="v" class="segmento" type="button" :aria-pressed="filtros.estado === v"
              @click="filtros.estado = v; recargar()">{{ t }}<span v-if="n !== undefined" class="cuenta">{{ n }}</span></button>
    </div>
  </div>
  <div class="filtros">
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" placeholder="Style, color, name, SKU, UPC or HS code" aria-label="Search" @input="buscar" />
    </label>
    <select v-model="filtros.marca_id" aria-label="Brand" @change="recargar">
      <option value="">All brands</option>
      <option v-for="m in opciones.marcas" :key="m.id" :value="m.id">{{ m.nombre }}</option>
    </select>
    <span class="ayuda separar">{{ datos.total }} products</span>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <th class="check"><input type="checkbox" aria-label="Select all" :checked="sel.todos(ids)" @change="sel.alternarTodos(ids)" /></th>
          <ThOrden campo="estilo" :orden="filtros.orden" @ordenar="ordenar">Product</ThOrden>
          <th v-if="!sesion.proveedorId && interno">Supplier</th>
          <ThOrden campo="codigo" :orden="filtros.orden" @ordenar="ordenar">HS code</ThOrden>
          <th>Countries</th>
          <ThOrden campo="estado" :orden="filtros.orden" @ordenar="ordenar">Status</ThOrden>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in datos.items" :key="p.id" class="clicable" @click="router.push(`/productos/${p.id}`)">
          <td class="check" @click.stop><input type="checkbox" :aria-label="`Select ${p.estilo}`" :checked="sel.tiene(p.id)" @change="sel.alternar(p.id)" /></td>
          <td>
            <div class="producto-celda">
              <span class="miniatura">
                <img v-if="p.foto_id" :src="`/api/productos/fotos/${p.foto_id}`" alt="" loading="lazy" />
                <Icono v-else nombre="caja" :tam="18" />
              </span>
              <span>
                <router-link :to="`/productos/${p.id}`" class="fuerte" @click.stop>{{ p.estilo }} · {{ p.color }}</router-link>
                <span class="sub">{{ p.nombre || '—' }} · {{ p.marca_nombre || p.marca }}<template v-if="p.tipo"> · {{ M.TIPO_CORTO[p.tipo] || p.tipo }}</template> · {{ p.skus }} SKU</span>
              </span>
            </div>
          </td>
          <td v-if="!sesion.proveedorId && interno">{{ p.proveedor }}</td>
          <td>
            <template v-if="codigoDe(p)">
              <span class="codigo-sac" :class="{ tentativo: !p.codigo }">{{ codigoDe(p) }}</span>
              <span class="sub" :title="M.descDe(codigoDe(p))">{{ p.codigo ? descCorta(p.codigo) : 'Suggested, not approved' }}</span>
            </template>
            <span v-else class="apagado">Not classified</span>
          </td>
          <td>
            <span v-if="p.paises_ok === p.paises_total" class="etiqueta ok"><Icono nombre="check" :tam="12" />{{ p.paises_ok }}/{{ p.paises_total }}</span>
            <span v-else-if="p.paises_ok" class="etiqueta aviso">{{ p.paises_ok }}/{{ p.paises_total }}</span>
            <span v-else class="apagado">—</span>
          </td>
          <td>
            <EstadoBadge :estado="p.estado" />
            <span v-if="!p.ficha_completa && !['aprobado', 'corregido'].includes(p.estado)" class="sub recortar" :title="p.faltan.join(', ')">{{ p.faltan.length ? `Missing: ${p.faltan[0]}` : 'Sheet incomplete' }}</span>
          </td>
          <td class="num"><Icono nombre="derecha" :tam="16" /></td>
        </tr>
        <tr v-if="!datos.items.length && !cargando">
          <td colspan="7" class="vacio">
            <template v-if="filtros.estado === 'pendientes' || filtros.estado === 'sugerida'"><Icono nombre="check" /> Nothing pending here.</template>
            <template v-else>No products match these filters.</template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />

  <BarraSeleccion :cantidad="sel.ids.size" singular="product" plural="products" @limpiar="sel.limpiar()">
    <template #resumen>
      <template v-if="interno && porAprobar.length">{{ porAprobar.length }} ready to approve</template>
    </template>
    <button class="btn" :disabled="ocupado" title="Run the classification engine on the saved technical sheets" @click="clasificar"><Icono nombre="varita" />Classify</button>
    <button v-if="puede('producto.clasificar')" class="btn btn-primario" :disabled="ocupado || !porAprobar.length"
            title="Approve the suggested code of the complete sheets" @click="aprobar"><Icono nombre="check" />Approve {{ porAprobar.length || '' }}</button>
  </BarraSeleccion>
</template>

<style scoped>
.producto-celda { display: flex; align-items: center; gap: 10px; }
.miniatura { width: 38px; height: 38px; border-radius: 8px; background: var(--superficie-2); border: 1px solid var(--linea); display: grid; place-items: center; color: var(--tinta-3); overflow: hidden; flex: none; }
.recortar { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.miniatura img { width: 100%; height: 100%; object-fit: cover; }
</style>
