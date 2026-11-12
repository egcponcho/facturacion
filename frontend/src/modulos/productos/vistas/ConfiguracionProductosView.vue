<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import PortadaConfig from '@/componentes/PortadaConfig.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// Portada de la configuración de productos (como en el ERP): cada apartado dice
// para qué sirve y cuántos registros tiene, agrupados en el orden en que conviene
// configurarlos. Los catálogos se abren en Datos maestros, ya dentro del módulo.
const cuentas = reactive({})
// La marca es un catálogo más: su tarjeta aparece si algún atributo la usa o ya hay marcas
const usaMarcas = ref(false)
async function cargar() {
  try {
    const [meta, grupos, atr, res] = await Promise.all([api.get('/catalogos'), api.get('/grupos-producto').catch(() => []),
      api.get('/catalogos/atributos', { size: 200 }).catch(() => ({ items: [] })), api.get('/productos/resumen').catch(() => null)])
    for (const c of meta) cuentas[c.tipo] = c.total
    cuentas.grupos_producto = (grupos || []).length
    // Los packs y kits son artículos: su cuenta viene del resumen de productos
    if (res?.configuracion) cuentas.compuestos = res.configuracion.compuestos
    usaMarcas.value = (atr.items || []).some((a) => a.catalogo === 'marcas') || cuentas.marcas > 0
  } catch {
    /* las cuentas son solo informativas */
  }
}
onMounted(cargar)

// Código de las variantes sin escala de valores: la regla de la empresa (solo administración la cambia)
const admin = puede('admin')
const codigo = reactive({ regla: '', factor: null, longitud: 3 })
const reglas = ref([])
const guardando = ref(false)
async function cargarCodigo() {
  if (!admin) return
  try {
    const o = await api.get('/organizacion')
    Object.assign(codigo, o.productos?.codigo_variante || {})
    reglas.value = o.reglas_codigo || []
  } catch {
    /* sin acceso, el panel no se muestra */
  }
}
onMounted(cargarCodigo)
// Cómo queda el código de dos valores de ejemplo con la regla elegida
const ejemplo = computed(() => {
  const largo = Number(codigo.longitud) || 0
  const pad = (n) => String(n).padStart(largo, '0')
  if (codigo.regla === 'MULTIPLICAR') {
    const f = Number(codigo.factor) || 1
    return [['7.5', pad(7.5 * f)], ['10', pad(10 * f)]].filter(([, c]) => !c.includes('.'))
  }
  if (codigo.regla === 'VALOR') return [['M', 'M'], ['500 ML', '500ML']]
  return [[t('first value'), pad(1)], [t('second value'), pad(2)]]
})
async function guardarCodigo() {
  guardando.value = true
  try {
    const o = await api.put('/organizacion', { productos: { codigo_variante: { ...codigo } } })
    Object.assign(codigo, o.productos?.codigo_variante || {})
    avisar(t('Variant code rule saved.'))
  } catch (e) {
    errorApi(e)
  } finally {
    guardando.value = false
  }
}
alCambiar(cargar, ['/catalogos', '/grupos-producto'])

const cat = (tipo) => `/mantenimiento?catalogo=${tipo}`
const APARTADOS = computed(() => [
  { grupo: t('How a product is built'), items: [
    { a: '/grupos-producto', clave: 'grupos_producto', icono: 'capas', nombre: t('Families and categories'),
      texto: t('The kinds of product. Each family says which data its products need and which attributes tell its variants apart; labels and packing use it.') },
    { a: cat('atributos'), clave: 'atributos', icono: 'lista', nombre: t('Attributes'),
      texto: t('The data your company defines: of the product (brand, model, material…) or of the variant (a measure, a color, a presentation, a concentration…).') },
    { a: cat('escalas'), clave: 'escalas', icono: 'escala', nombre: t('Value scales'),
      texto: t('Reusable lists of values with the code each value gives to the item.') },
    { a: cat('articulos'), clave: 'compuestos', icono: 'caja', nombre: t('Packs and kits'),
      texto: t('Composite items: a pack of variants of one product or a kit of items of any product. They are created in Items with New pack or kit.') },
  ] },
  { grupo: t('Items and commercial data'), items: [
    { a: cat('articulos'), clave: 'articulos', icono: 'etiqueta', nombre: t('Items (variants)'),
      texto: t('Every variant with its item code, barcode and supplier code; bulk upload.') },
    ...(usaMarcas.value ? [{ a: cat('marcas'), clave: 'marcas', icono: 'base', nombre: t('Brands'), texto: t('The brands and which suppliers may sell them.') }] : []),
    { a: cat('listas'), clave: 'listas', icono: 'lista', nombre: t('Value lists'), texto: t('Units and other lists the forms offer.') },
  ] },
  { grupo: t('Trade and compliance'), items: [
    { a: cat('acuerdos'), clave: 'acuerdos', icono: 'ruta', nombre: t('Trade agreements'), texto: t('Agreements by country of origin used on the technical sheet.') },
    { a: cat('dominios'), icono: 'globo', nombre: t('Classification domains'), texto: t('Kinds of goods the classification engine handles.') },
  ] },
].map((g) => ({ ...g, items: g.items.filter((x) => x.clave === 'grupos_producto' ? puede(['catalogos.ver', 'etiquetas.familias']) : puede('catalogos.ver')) }))
  .filter((g) => g.items.length))
</script>

<template>
  <div>
    <header class="pagina-cabeza">
      <div>
        <h1>{{ t('Products setup') }}</h1>
        <p>{{ t('What you set up once so creating products is quick: families and their attributes, value scales, brands and the rest of the catalogs.') }}</p>
      </div>
    </header>
    <PortadaConfig :grupos="APARTADOS" :cuentas="cuentas" />

    <section v-if="admin && codigo.regla" class="panel codigo-variante" aria-labelledby="t-codigo">
      <div class="panel-cabeza"><div>
        <h2 id="t-codigo">{{ t('Variant code without a value scale') }}</h2>
        <p>{{ t('When a variant does not come from a value scale and nobody types its item code, it is the product code plus this code. A value scale uses its own rule.') }}</p>
      </div></div>
      <div class="cv-campos">
        <label class="campo"><span>{{ t('Code rule') }}</span>
          <Seleccion v-model="codigo.regla" class="entrada">
            <option v-for="r in reglas" :key="r.clave" :value="r.clave">{{ tx(r.texto) }}</option>
          </Seleccion></label>
        <label v-if="codigo.regla === 'MULTIPLICAR'" class="campo"><span>{{ t('Factor') }}</span>
          <input v-model.number="codigo.factor" class="entrada" type="number" min="1" /></label>
        <label v-if="codigo.regla !== 'VALOR'" class="campo"><span>{{ t('Code digits') }}</span>
          <input v-model.number="codigo.longitud" class="entrada" type="number" min="1" max="10" /></label>
        <p class="ayuda cv-ejemplo">{{ t('Example') }}: {{ ejemplo.map(([v, c]) => `${v} → ${c}`).join(' · ') }}</p>
        <button class="btn btn-primario" :disabled="guardando" @click="guardarCodigo"><Icono nombre="check" />{{ t('Save') }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.codigo-variante { margin-top: 22px; }
.cv-campos { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; }
.cv-campos .campo { display: flex; flex-direction: column; gap: 4px; min-width: 160px; }
.cv-ejemplo { flex-basis: 100%; margin: 0; }
</style>
