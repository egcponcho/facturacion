<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import { fmtNum } from '@/nucleo/utils'
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
      texto: t('The kinds of product. Each family says which attributes tell its variants apart; labels and packing use it.') },
    { a: cat('atributos_variante'), clave: 'atributos_variante', icono: 'lista', nombre: t('Variant attributes'),
      texto: t('Size, color, flavor, concentration, packaging… whatever tells one variant from another.') },
    { a: cat('escalas'), clave: 'escalas', icono: 'escala', nombre: t('Value scales'),
      texto: t('Reusable lists of values (a size run, a set of volumes) with the code each value gives to the item.') },
    { a: cat('prepacks'), clave: 'prepacks', icono: 'caja', nombre: t('Packs and kits'),
      texto: t('Composite items: a pack of variants of one product or a kit of items of any product.') },
  ] },
  { grupo: t('Items and commercial data'), items: [
    { a: cat('articulos'), clave: 'articulos', icono: 'etiqueta', nombre: t('Items (variants)'),
      texto: t('Every variant with its item code, UPC and supplier SKU; bulk upload with technical sheets.') },
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
const textoCuenta = (n) => (n === 1 ? t('1 record') : t('{0} records', [fmtNum(n)]))
</script>

<template>
  <div>
    <header class="pagina-cabeza">
      <div>
        <h1>{{ t('Products setup') }}</h1>
        <p>{{ t('What you set up once so creating products is quick: families, variant attributes, scales, brands and the rest of the catalogs.') }}</p>
      </div>
    </header>
    <div class="config-portada">
      <section v-for="g in APARTADOS" :key="g.grupo" :aria-label="g.grupo">
        <h2 class="config-grupo">{{ g.grupo }}</h2>
        <div class="config-tarjetas">
          <router-link v-for="x in g.items" :key="x.a" :to="x.a" class="config-tarjeta">
            <span class="config-icono"><Icono :nombre="x.icono" :tam="20" /></span>
            <span class="config-texto"><b>{{ x.nombre }}</b><small>{{ x.texto }}</small></span>
            <span class="config-cuenta" :class="{ vacia: cuentas[x.clave] === 0 }">
              <span v-if="cuentas[x.clave] === undefined" class="esqueleto" style="width: 28px; height: 14px" />
              <template v-else-if="cuentas[x.clave] === 0">{{ t('No records') }}</template>
              <template v-else>{{ tx(textoCuenta(cuentas[x.clave])) }}</template>
            </span>
          </router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.config-portada { display: flex; flex-direction: column; gap: 22px; }
.config-grupo { font-size: var(--t-xs); text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); font-weight: 650; margin: 0 0 10px; }
.config-tarjetas { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.config-tarjeta {
  display: grid; grid-template-columns: auto minmax(0, 1fr); grid-template-rows: auto auto; gap: 4px 14px; padding: 16px; color: inherit; text-decoration: none;
  background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio-panel); box-shadow: var(--sombra);
  transition: border-color 150ms, box-shadow 150ms;
}
.config-tarjeta:hover { border-color: var(--acento-medio); box-shadow: var(--sombra-media); }
.config-icono { grid-row: span 2; width: 40px; height: 40px; border-radius: 10px; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); }
.config-texto { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.config-texto b { font-size: var(--t-md); }
.config-texto small { color: var(--tinta-3); font-size: var(--t-sm); line-height: 1.45; }
.config-cuenta { font-size: var(--t-xs); font-weight: 650; color: var(--tinta-2); font-variant-numeric: tabular-nums; }
.config-cuenta.vacia { color: var(--aviso); }
@media (max-width: 400px) { .config-tarjetas { grid-template-columns: minmax(0, 1fr); } }
@media (prefers-reduced-motion: reduce) { .config-tarjeta { transition: none; } }
</style>
