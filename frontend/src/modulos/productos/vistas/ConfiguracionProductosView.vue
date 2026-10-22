<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t } from '@/i18n/index.js'
import { computed, onMounted, reactive } from 'vue'
import { api } from '@/nucleo/api'
import PortadaConfig from '@/componentes/PortadaConfig.vue'
import { puede } from '@/stores/sesion'

// Portada de la configuración de productos (como en el ERP): cada apartado dice
// para qué sirve y cuántos registros tiene, agrupados en el orden en que conviene
// configurarlos. Los catálogos se abren en Datos maestros, ya dentro del módulo.
const cuentas = reactive({})
async function cargar() {
  try {
    const [meta, grupos] = await Promise.all([api.get('/catalogos'), api.get('/grupos-producto').catch(() => [])])
    for (const c of meta) cuentas[c.tipo] = c.total
    cuentas.grupos_producto = (grupos || []).length
  } catch {
    /* las cuentas son solo informativas */
  }
}
onMounted(cargar)
alCambiar(cargar, ['/catalogos', '/grupos-producto'])

const cat = (tipo) => `/mantenimiento?catalogo=${tipo}`
const APARTADOS = computed(() => [
  { grupo: t('How a product is built'), items: [
    { a: '/grupos-producto', clave: 'grupos_producto', icono: 'capas', nombre: t('Families and categories'),
      texto: t('The kinds of product. Each family says which data its products need and which attributes tell its variants apart; labels and packing use it.') },
    { a: cat('atributos_variante'), clave: 'atributos_variante', icono: 'lista', nombre: t('Variant attributes'),
      texto: t('Whatever tells one variant from another: a measure, a color, a presentation, a concentration…') },
    { a: cat('escalas'), clave: 'escalas', icono: 'escala', nombre: t('Value scales'),
      texto: t('Reusable lists of values with the code each value gives to the item.') },
    { a: cat('prepacks'), clave: 'prepacks', icono: 'caja', nombre: t('Packs and kits'),
      texto: t('Composite items: a pack of variants of one product or a kit of items of any product.') },
  ] },
  { grupo: t('Items and commercial data'), items: [
    { a: cat('articulos'), clave: 'articulos', icono: 'etiqueta', nombre: t('Items (variants)'),
      texto: t('Every variant with its item code, barcode and supplier code; bulk upload.') },
    { a: cat('marcas'), clave: 'marcas', icono: 'base', nombre: t('Brands'), texto: t('The brands and which suppliers may sell them.') },
    { a: cat('grupos'), clave: 'grupos', icono: 'cuadricula', nombre: t('Item groups'), texto: t('Commercial grouping used in orders, reports and filters.') },
    { a: cat('categorias'), clave: 'categorias', icono: 'filtro', nombre: t('Item categories'), texto: t('Categories of the items for reports and rules.') },
    { a: cat('listas'), clave: 'listas', icono: 'lista', nombre: t('Value lists'), texto: t('Units and other lists the forms offer.') },
  ] },
  { grupo: t('Trade and compliance'), items: [
    { a: cat('acuerdos'), clave: 'acuerdos', icono: 'ruta', nombre: t('Trade agreements'), texto: t('Agreements by country of origin used on the technical sheet.') },
    { a: cat('dominios'), clave: 'dominios', icono: 'globo', nombre: t('Classification domains'), texto: t('Kinds of goods the classification engine handles.') },
  ] },
].map((g) => ({ ...g, items: g.items.filter((x) => x.clave === 'grupos_producto' ? puede(['catalogos.ver', 'etiquetas.familias']) : puede('catalogos.ver')) }))
  .filter((g) => g.items.length))
</script>

<template>
  <div>
    <header class="pagina-cabeza">
      <div>
        <h1>{{ t('Products setup') }}</h1>
        <p>{{ t('What you set up once so creating products is quick: families, variant attributes, scales, brands and the rest of the catalogs.') }}</p>
      </div>
    </header>
    <PortadaConfig :grupos="APARTADOS" :cuentas="cuentas" />
  </div>
</template>
