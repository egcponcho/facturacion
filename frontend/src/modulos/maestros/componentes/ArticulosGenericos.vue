<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import { plural, textoVariante } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import GenericoModal from './GenericoModal.vue'
import Icono from '@/componentes/Icono.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { estado as leerEstado } from '@/nucleo/estados.js'

// Vista compacta de artículos: un renglón por genérico (estilo-color) con sus
// datos maestros; al desplegarlo se ven sus tallas y prepacks, como las líneas
// de una orden. La vista de listado (un renglón por artículo) sigue en Master data.
// Tabla común en modo servidor: cada columna filtra por sus valores (/catalogos/genericos/valores).
//   q: búsqueda de la pantalla; iniciales: filtros de columna con los que abre
//   nombre(clave, id): nombre de una marca, grupo o proveedor por su id
//   acciones: lo que el usuario puede hacer en el catálogo de artículos (permisos y responsables)
const props = defineProps({ q: { type: String, default: '' }, iniciales: { type: Object, default: () => ({}) }, recarga: { type: Number, default: 0 },
  acciones: { type: Object, default: () => ({}) }, nombre: { type: Function, default: (_k, v) => v } })
const puede = (p) => !!props.acciones[p.replace('catalogos.', '')]
const emit = defineEmits(['editar-articulo', 'eliminar-articulo', 'desglose', 'cambio', 'consulta'])
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)
const tabla = ref(null)
const detalles = reactive({})
const modal = ref(null) // { generico, editar }

const ESTADOS = ['borrador', 'sugerida', 'revision', 'observado', 'aprobado'].map((c) => [c, leerEstado(c, 'producto')[0]])
const columnas = computed(() => [
  { clave: 'generico', texto: t('Product code'), fija: true, prioridad: 1 },
  { clave: 'estilo', texto: t('Model'), prioridad: 3, inicial: false },
  { clave: 'color', texto: t('Fixed color'), prioridad: 3, inicial: false },
  { clave: 'marca_id', texto: t('Brand'), prioridad: 2, textoValor: (v) => props.nombre('marca_id', v) },
  { clave: 'grupo_id', texto: t('Group'), prioridad: 3, textoValor: (v) => props.nombre('grupo_id', v) },
  { clave: 'proveedor_id', texto: t('Supplier'), prioridad: 2, textoValor: (v) => props.nombre('proveedor_id', v) },
  { clave: 'unidad', texto: t('Unit'), prioridad: 3, inicial: false },
  { clave: 'tallas', texto: t('Variants'), prioridad: 2, ordenable: false },
  { clave: 'descripcion_comercial', texto: t('Description · HS code'), prioridad: 3 },
  { clave: 'estado', texto: t('Sheet status'), prioridad: 3, inicial: false, opciones: ESTADOS },
])
// El código de la variante: lo que sigue al código del producto en su código de artículo
const sufijo = (a) => (a.generico && a.sku.startsWith(a.generico) ? a.sku.slice(a.generico.length) : '')
const columnasTallas = [
  { clave: 'sku', texto: t('Item code'), fija: true, prioridad: 1 },
  { clave: 'codigo_talla', texto: t('Variant code'), prioridad: 3, valor: (a) => sufijo(a) },
  { clave: 'tipo', texto: t('Type'), prioridad: 2, opciones: [['SOLIDO', t('Simple')], ['PREPACK', t('Pack or kit')]] },
  { clave: 'variante', texto: t('Variant'), valor: (x) => textoVariante(x), prioridad: 1 },
  { clave: 'upc', texto: t('Barcode'), prioridad: 3, textoValor: (v) => v || '—' },
  { clave: 'sku_proveedor', texto: t('Supplier code'), prioridad: 3, textoValor: (v) => v || '—' },
  { clave: 'activo', texto: t('Active'), prioridad: 2, opciones: [[true, t('Yes')], [false, t('No')]] },
]

let ultima = null
async function cargar(c = ultima) {
  if (!c) return
  ultima = c
  emit('consulta', c)
  cargando.value = true
  try {
    datos.value = await api.get('/catalogos/genericos', { q: props.q || undefined, orden: c.orden || undefined, page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const valores = (columna, buscar, otros) => api.get('/catalogos/genericos/valores', { columna, buscar, f: JSON.stringify(otros), q: props.q || undefined })
async function cargarTallas(gen) {
  try {
    detalles[gen] = (await api.get('/catalogos/articulos', { q: gen, size: 200, orden: 'sku:asc' })).items.filter((a) => a.sku.startsWith(gen))
  } catch (e) {
    errorApi(e)
  }
}
function listo() {
  const gen = modal.value.generico
  modal.value = null
  if (gen) delete detalles[gen]
  emit('cambio')
  cargar()
}

// La vista madre avisa con "recarga" cuando cambia la búsqueda (ya con espera) o los datos
watch(() => props.recarga, () => {
  for (const g of Object.keys(detalles)) delete detalles[g]
  if (tabla.value && tabla.value.pagina !== 1) tabla.value.pagina = 1
  else cargar()
})
</script>

<template>
  <TablaDatos ref="tabla" tabla="catalogo_genericos" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              clave-fila="generico" :valores="valores" :filtros-iniciales="iniciales" expandible :externos="{ q }" :etiqueta="t('Products')"
              @consulta="cargar" @expandir="(g) => !detalles[g.generico] && cargarTallas(g.generico)">
    <template #barra><slot name="barra" /></template>
    <template #filtros><slot name="filtros" /></template>
    <template #celda-generico="{ fila: g }"><strong class="codigo">{{ tx(g.generico) }}</strong><span class="sub">{{ tx(g.unidad) }}</span></template>
    <template #celda-estilo="{ fila: g }">{{ tx(g.estilo || '—') }}</template>
    <template #celda-marca_id="{ fila: g }">{{ tx(g.marca || '—') }}</template>
    <template #celda-grupo_id="{ fila: g }"><span class="codigo">{{ tx(g.grupo || '—') }}</span></template>
    <template #celda-proveedor_id="{ fila: g }">{{ tx(g.proveedor || '—') }}</template>
    <template #celda-tallas="{ fila: g }">
      <span class="fuerte">{{ tx(g.resumen_variantes || '—') }}</span>
      <span class="sub">{{ plural(g.n_tallas, t('variant'), t('variants')) }}<template v-if="g.n_prepacks"> · {{ plural(g.n_prepacks, t('pack'), t('packs')) }}</template></span>
    </template>
    <template #celda-descripcion_comercial="{ fila: g }">
      <span>{{ tx(g.descripcion_comercial || '—') }}</span>
      <router-link :to="`/productos/${g.producto_id}`" class="sub enlace" :title="t('Technical sheet of {0}', [g.generico])">
        <span v-if="g.codigo" class="codigo-sac">{{ tx(g.codigo) }}</span><EstadoBadge v-else :estado="g.estado" tipo="producto" />
      </router-link>
    </template>
    <template #celda-estado="{ fila: g }"><EstadoBadge :estado="g.estado" tipo="producto" /></template>
    <template #acciones="{ fila: g }">
      <span class="nowrap">
        <button v-if="puede('catalogos.crear')" type="button" class="btn btn-chico" :title="t('Add variants to this product')" @click="modal = { generico: g.generico }"><Icono nombre="mas" :tam="13" />{{ t('Variants') }}</button>
        <button v-if="puede('catalogos.editar')" type="button" class="btn-icono" :aria-label="t('Edit product {0}', [g.generico])" :title="t('Edit the product (applies to all its variants)')" @click="modal = { generico: g.generico, editar: true }"><Icono nombre="editar" :tam="16" /></button>
      </span>
    </template>
    <template #detalle="{ fila: g }">
      <p v-if="!detalles[g.generico]" class="ayuda">{{ t('Loading…') }}</p>
      <TablaDatos v-else :tabla="'catalogo_genericos_tallas'" :columnas="columnasTallas" :filas="detalles[g.generico]" :vistas-guardadas="false" :etiqueta="t('Variants of product {0}', [g.generico])">
        <template #celda-sku="{ fila: a }"><span class="codigo fuerte">{{ tx(a.sku) }}</span></template>
        <template #celda-codigo_talla="{ fila: a }"><span class="codigo">{{ tx(sufijo(a) || '—') }}</span></template>
        <template #celda-tipo="{ fila: a }"><span class="etiqueta ms-0" :class="{ acento: a.tipo === 'PREPACK' }">{{ tx(a.tipo === 'PREPACK' ? t('Pack or kit') : t('Simple')) }}</span></template>
        <template #celda-activo="{ fila: a }"><span class="etiqueta ms-0" :class="a.activo ? 'ok' : ''">{{ tx(a.activo ? t('Yes') : t('No')) }}</span></template>
        <template #acciones="{ fila: a }">
          <span class="nowrap">
            <button v-if="a.tipo === 'PREPACK'" type="button" class="btn btn-chico" :title="t('See the breakdown')" @click="emit('desglose', a)"><Icono nombre="lupa" :tam="13" />{{ t('Breakdown') }}</button>
            <button v-if="puede('catalogos.editar')" type="button" class="btn-icono" :aria-label="t('Edit item {0}', [a.sku])" :title="t('Edit')" @click="emit('editar-articulo', a)"><Icono nombre="editar" :tam="15" /></button>
            <button v-if="puede('catalogos.eliminar')" type="button" class="btn-icono texto-error" :aria-label="t('Delete item {0}', [a.sku])" :title="t('Delete')" @click="emit('eliminar-articulo', a)"><Icono nombre="basura" :tam="15" /></button>
          </span>
        </template>
        <template #vacio>{{ t('This product has no variants yet.') }}</template>
      </TablaDatos>
    </template>
    <template #vacio>{{ t('No products match these filters.') }}</template>
  </TablaDatos>
  <GenericoModal v-if="modal" :generico="modal.generico" :editar="!!modal.editar" @cerrar="modal = null" @listo="listo" />
</template>
