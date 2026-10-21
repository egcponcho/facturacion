<script setup>
import { etiquetaUnidad, unidadesArticulo } from '@/nucleo/unidades.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { api } from '@/nucleo/api'
import { avisar, errorApi } from '@/stores/ui'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { enfocarUltimo } from '@/nucleo/utils'

// Producto (de cualquier tipo) y sus variantes. El producto se crea una vez con
// su código y sus datos maestros; sus variantes se distinguen por los atributos
// de variante de su familia (talla y color, sabor y presentación, concentración
// y envase…). Las variantes se escriben fila por fila o se combinan: todos los
// valores de un atributo por todos los de otro.
// generico con valor: agregar variantes; con editar: cambiar sus datos maestros
const props = defineProps({ generico: { type: String, default: '' }, editar: Boolean })
const emit = defineEmits(['cerrar', 'listo'])
const agregar = computed(() => !!props.generico && !props.editar)
const g = reactive({ generico: '', nombre: '', estilo: '', color: '', marca_id: '', grupo_id: '', proveedor_id: '', grupo_producto_id: '', unidad: '' })
const pesoTodas = ref('')
const op = reactive({ marcas: [], grupos: [], proveedores: [], familias: [] })
const atributos = ref([]) // atributos de variante activos (código, nombre, tipo, opciones, columna)
const escalas = ref([])
const escalaId = ref('')
const info = ref(null)
const errores = ref([])
const ocupado = ref(false)
// Valores a combinar por atributo (texto con tramos: 7-10, 12 · S-XL · 250 ml, 500 ml)
const valores = reactive({})
const filas = ref([])

onMounted(async () => {
  try {
    if (props.generico) info.value = await api.get(`/catalogos/genericos/${props.generico}`)
    const pedidos = [api.get('/catalogos/atributos_variante', { size: 200 }), api.get('/grupos-producto').catch(() => [])]
    if (!agregar.value) pedidos.push(...['marcas', 'grupos', 'proveedores'].map((x) => api.get(`/catalogos/${x}/opciones`)))
    const [atr, grupos, m, gr, p] = await Promise.all(pedidos)
    atributos.value = (atr.items || []).filter((a) => a.activo !== false).sort((a, b) => (a.orden || 0) - (b.orden || 0))
    op.familias = (grupos || []).filter((x) => x.clase === 'FAMILIA' && x.activa !== false)
    if (!agregar.value) Object.assign(op, { marcas: m, grupos: gr, proveedores: p })
    if (!props.editar) escalas.value = ((await api.get('/catalogos/escalas', { size: 200 })).items || []).filter((e) => e.activo !== false)
    if (!g.unidad) g.unidad = unidadesArticulo()[0] || ''
    if (info.value) {
      const i = info.value
      Object.assign(g, { generico: i.generico, nombre: i.nombre || '', estilo: i.estilo || '', color: i.color || '', marca_id: i.marca_id, grupo_id: i.grupo_id,
        proveedor_id: i.proveedor_id, grupo_producto_id: i.grupo_producto_id || '', unidad: i.unidad })
    }
  } catch (e) {
    errorApi(e)
  }
})
const opc = (l) => l.map((x) => ({ valor: x.id, texto: x.texto, sub: x.sub }))

// Los atributos de las variantes: los de la familia (o de su antecesora más cercana que los tenga); sin
// familia ni ejes, todos los activos. Un color fijo del producto no es un atributo de sus variantes.
function ejesDe(id) {
  const porId = Object.fromEntries(op.familias.map((f) => [String(f.id), f]))
  let f = porId[String(id)]
  const vistos = new Set()
  while (f && !vistos.has(f.id)) {
    vistos.add(f.id)
    if (f.ejes_variante?.length) return f.ejes_variante
    f = porId[String(f.padre_id)]
  }
  return []
}
const ejes = computed(() => {
  const codigos = ejesDe(g.grupo_producto_id)
  const lista = codigos.length ? codigos.map((c) => atributos.value.find((a) => a.codigo === c)).filter(Boolean) : atributos.value
  return lista.filter((a) => !(g.color && a.columna === 'color'))
})
watch(ejes, (lista) => {
  for (const a of lista) if (!(a.codigo in valores)) valores[a.codigo] = ''
}, { immediate: true })
const opcionesDe = (a) => (a.opciones || '').split(',').map((x) => x.trim()).filter(Boolean)
const escalasDe = (a) => escalas.value.filter((e) => (e.atributo || 'TALLA') === a.codigo)
function usarEscala(a, id) {
  const e = escalas.value.find((x) => String(x.id) === String(id))
  if (!e) return
  valores[a.codigo] = String(e.tallas || '').split(',').map((x) => x.split('=')[0].trim()).filter(Boolean).join(', ')
  escalaId.value = e.id // sus códigos arman los códigos de artículo
}

// "7-10, 12", "6.5-9.5", "S-XL" o "S, M, XL": tramos y valores sueltos
const LETRAS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
function expandir(texto) {
  const lista = []
  for (const tramo of String(texto || '').split(/[,;]+/).map((x) => x.trim()).filter(Boolean)) {
    const m = tramo.match(/^(\S+)\s*(?:-|to|a)\s*(\S+)$/i)
    const [a, b] = m ? [m[1].toUpperCase(), m[2].toUpperCase()] : []
    if (m && /^\d+(\.5)?$/.test(a) && /^\d+(\.5)?$/.test(b)) {
      const paso = tramo.includes('.5') ? 0.5 : 1
      for (let x = Number(a); x <= Number(b) + 1e-9; x += paso) lista.push(String(x))
    } else if (m && LETRAS.includes(a) && LETRAS.includes(b)) lista.push(...LETRAS.slice(LETRAS.indexOf(a), LETRAS.indexOf(b) + 1))
    else lista.push(tramo)
  }
  return [...new Set(lista)]
}
const nuevaFila = (vals = {}) => ({ valores: { ...vals }, sufijo: '', sku: '', upc: '', sku_proveedor: '', peso: pesoTodas.value })
const existentes = computed(() => new Set((info.value?.tallas || []).filter((x) => x.tipo === 'SOLIDO')
  .map((x) => ejes.value.map((a) => String(x.valores?.[a.codigo] ?? '').toUpperCase()).join('|'))))
const totalCombinaciones = computed(() => {
  const listas = ejes.value.map((a) => expandir(valores[a.codigo])).filter((l) => l.length)
  return listas.length ? listas.reduce((n, l) => n * l.length, 1) : 0
})
// Todas las combinaciones de los valores escritos (sin las variantes que el producto ya tiene)
function combinar() {
  const listas = ejes.value.map((a) => [a.codigo, expandir(valores[a.codigo])]).filter(([, l]) => l.length)
  if (!listas.length) return
  if (totalCombinaciones.value > 500) {
    avisar(t('That is {0} variants: at most {1} at a time.', [totalCombinaciones.value, 500]), 'error')
    return
  }
  let combos = [{}]
  for (const [codigo, lista] of listas) combos = combos.flatMap((c) => lista.map((v) => ({ ...c, [codigo]: v })))
  const ya = new Set(filas.value.map((f) => ejes.value.map((a) => String(f.valores[a.codigo] ?? '').toUpperCase()).join('|')))
  for (const c of combos) {
    const clave = ejes.value.map((a) => String(c[a.codigo] ?? '').toUpperCase()).join('|')
    if (!ya.has(clave) && !existentes.value.has(clave)) filas.value.push(nuevaFila(c))
  }
}
function pesoParaTodas() {
  for (const f of filas.value) f.peso = pesoTodas.value
}
const vacia = (f) => !Object.values(f.valores).some((v) => String(v || '').trim())

async function guardar() {
  errores.value = []
  const tallas = filas.value.filter((f) => !vacia(f)).map(({ peso, valores: v, ...f }) => ({
    ...f, valores: Object.fromEntries(Object.entries(v).filter(([, x]) => String(x || '').trim())),
    peso_unitario: peso === '' || peso === null ? null : Number(peso),
  }))
  const maestros = { ...g, marca_id: Number(g.marca_id), grupo_id: Number(g.grupo_id), proveedor_id: Number(g.proveedor_id),
    grupo_producto_id: Number(g.grupo_producto_id) || null, estilo: g.estilo || null, color: g.color || null, nombre: g.nombre || null }
  ocupado.value = true
  try {
    if (props.editar) {
      const r = await api.put(`/catalogos/genericos/${props.generico}`, maestros)
      avisar(t('Product {0} updated in all its variants.', [props.generico]))
      emit('listo', r)
      return
    }
    const r = agregar.value
      ? await api.post(`/catalogos/genericos/${props.generico}/tallas`, { tallas, escala_id: Number(escalaId.value) || null })
      : await api.post('/catalogos/genericos', { ...maestros, tallas, escala_id: Number(escalaId.value) || null })
    avisar(agregar.value ? t('{0} variants added to {1}.', [tallas.length, props.generico])
      : t('Product {0} created with {1} variants. Complete its technical sheet in Products.', [r.generico, r.tallas.length]))
    emit('listo', r)
  } catch (e) {
    errores.value = [e.message, ...(e.detalle || []).map((d) => d.mensaje)]
  } finally {
    ocupado.value = false
  }
}
// Solo las marcas autorizadas al proveedor elegido
const marcasProveedor = computed(() => op.marcas.filter((m) => g.proveedor_id && (m.proveedores || []).map(String).includes(String(g.proveedor_id))))
watch(() => g.proveedor_id, () => {
  if (g.marca_id && !marcasProveedor.value.some((m) => String(m.id) === String(g.marca_id))) g.marca_id = ''
  if (!g.marca_id && marcasProveedor.value.length === 1) g.marca_id = marcasProveedor.value[0].id
})
const variantesActuales = computed(() => (info.value?.tallas || []).filter((x) => x.tipo === 'SOLIDO')
  .map((x) => Object.values(x.valores || {}).join(' · ') || x.sku).join(', '))
</script>

<template>
  <Modal :titulo="tx(props.editar ? t('Edit product {0}', [props.generico]) : agregar ? t('Add variants to {0}', [props.generico]) : t('New product'))" ancho="900px" @cerrar="emit('cerrar')">
    <p class="ayuda">{{ t('A product of any kind (a chemical, a shoe, a raw material, an appliance, a food…) with its own code. Its variants share the technical sheet and the HS code and differ by the variant attributes of its family.') }}</p>
    <div v-if="agregar && info" class="doc-meta mt-chico">
      <span>{{ t('Product') }} <b>{{ tx(info.nombre || info.generico) }}</b></span><span>{{ t('Unit') }} <b>{{ tx(info.unidad) }}</b></span>
      <span>{{ t('Variants') }} <b>{{ tx(variantesActuales || '—') }}</b></span>
    </div>
    <div v-else-if="!agregar" class="rejilla-campos mt-chico">
      <label class="campo"><span class="req">{{ t('Product code') }}</span><input v-model="g.generico" class="entrada" maxlength="40" :placeholder="t('e.g. 30095129, QUIM-001 or VN0A5KRF-BLK')" :disabled="props.editar" /></label>
      <label class="campo"><span>{{ t('Name') }}</span><input v-model="g.nombre" class="entrada" maxlength="200" /></label>
      <div class="campo"><span>{{ t('Product family') }}</span>
        <SelectBusqueda v-model="g.grupo_producto_id" :opciones="op.familias.map((f) => ({ valor: f.id, texto: f.nombre, sub: f.ruta }))" :vacio="t('No family')" :etiqueta="t('Product family')" />
        <small class="ayuda">{{ t('The family says which attributes tell its variants apart.') }}</small></div>
      <div class="campo"><span class="req">{{ t('Supplier') }}</span><SelectBusqueda v-model="g.proveedor_id" :opciones="opc(op.proveedores)" :etiqueta="t('Supplier')" /></div>
      <div class="campo"><span class="req">{{ t('Brand') }}</span><SelectBusqueda v-model="g.marca_id" :opciones="opc(marcasProveedor)" :etiqueta="t('Brand')" :deshabilitado="!g.proveedor_id"
            :placeholder="tx(g.proveedor_id ? t('Choose…') : t('Choose the supplier first'))" /></div>
      <div class="campo"><span class="req">{{ t('Item group') }}</span><SelectBusqueda v-model="g.grupo_id" :opciones="opc(op.grupos)" :etiqueta="t('Item group')" /></div>
      <label class="campo"><span class="req">{{ t('Unit of its variants') }}</span><Seleccion v-model="g.unidad" class="entrada"><option v-for="u in unidadesArticulo()" :key="u" :value="u">{{ etiquetaUnidad(u) }}</option></Seleccion></label>
      <label class="campo"><span>{{ t('Style / model') }}</span><input v-model="g.estilo" class="entrada" maxlength="40" :placeholder="t('Optional')" /></label>
      <label class="campo"><span>{{ t('Fixed color') }}</span><input v-model="g.color" class="entrada" maxlength="60" :placeholder="t('Optional: if every variant has the same color')" /></label>
    </div>
    <p v-if="props.editar" class="ayuda mt-chico">{{ t('Changes apply to every variant of the product. Codes, UPC and supplier SKU are edited per item in the list view.') }}</p>

    <template v-if="!props.editar">
      <h3 class="mt">{{ t('Variants') }}</h3>
      <p v-if="!ejes.length" class="ayuda">{{ t('There are no variant attributes: each row is one item without variants.') }}</p>
      <div v-else class="combinar">
        <div v-for="a in ejes" :key="a.codigo" class="campo">
          <span>{{ tx(a.nombre) }}<small v-if="a.unidad" class="ayuda"> ({{ a.unidad }})</small></span>
          <div class="fila-flex gap-2">
            <input v-model="valores[a.codigo]" class="entrada" :list="`op-${a.codigo}`" :aria-label="t('Values of {0}', [tx(a.nombre)])"
                   :placeholder="a.tipo === 'opcion' ? opcionesDe(a).join(', ') : t('e.g. 7-10, 12 · S-XL · 250 ml, 1 L')" />
            <Seleccion v-if="escalasDe(a).length" class="entrada max-s" :model-value="''" :aria-label="t('Value scale')" @update:model-value="usarEscala(a, $event)">
              <option value="">{{ t('From a scale…') }}</option>
              <option v-for="e in escalasDe(a)" :key="e.id" :value="e.id">{{ tx(e.nombre) }}</option>
            </Seleccion>
          </div>
          <datalist v-if="a.tipo === 'opcion'" :id="`op-${a.codigo}`"><option v-for="o in opcionesDe(a)" :key="o" :value="o" /></datalist>
        </div>
        <div class="fila-flex gap-2">
          <button type="button" class="btn btn-chico" :disabled="!totalCombinaciones" @click="combinar">
            <Icono nombre="mas" :tam="14" />{{ t('Create the {0} combinations', [totalCombinaciones]) }}</button>
          <small class="ayuda">{{ t('Separate values with commas; ranges allowed (7-10, 6.5-9.5, S-XL).') }}</small>
        </div>
      </div>
      <div class="fila-flex gap-2" style="margin: 10px 0 4px">
        <button type="button" class="btn btn-chico" @click="filas.push(nuevaFila()); enfocarUltimo('.variantes tbody tr')"><Icono nombre="mas" :tam="14" />{{ t('Add row') }}</button>
        <input v-model="pesoTodas" class="entrada max-xs empuja-fin" type="number" min="0" step="any" :placeholder="t('Unit weight kg')" :aria-label="t('Unit weight for all variants')" />
        <button type="button" class="btn btn-chico" :disabled="pesoTodas === ''" @click="pesoParaTodas">{{ t('Same weight for all') }}</button>
      </div>
      <p class="ayuda mt-0 mb-2">{{ t('Item code: type your own, or leave it empty to use the product code plus a variant code (from the value scale, if one was used).') }}</p>
      <div class="tabla-marco tabla-captura">
        <table class="tabla variantes" v-tarjetas>
          <thead><tr><th v-for="a in ejes" :key="a.codigo">{{ tx(a.nombre) }}</th><th>{{ t('Variant code') }}</th><th>{{ t('Item code') }}</th>
            <th>{{ t('Unit weight kg') }}</th><th>UPC</th><th>{{ t('Supplier SKU') }}</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(f, i) in filas" :key="i">
              <td v-for="a in ejes" :key="a.codigo"><input v-model="f.valores[a.codigo]" class="entrada" maxlength="60" :list="a.tipo === 'opcion' ? `op-${a.codigo}` : undefined" :aria-label="`${tx(a.nombre)} ${i + 1}`" /></td>
              <td><input v-model="f.sufijo" class="entrada" maxlength="20" :placeholder="t('Auto')" :aria-label="t('Variant code {0}', [i + 1])" :disabled="!!f.sku" /></td>
              <td><input v-model="f.sku" class="entrada" maxlength="40" :placeholder="t('Auto')" :aria-label="t('Item code {0}', [i + 1])" /></td>
              <td><input v-model="f.peso" class="entrada ancho-s" type="number" min="0" step="any" :aria-label="t('Unit weight {0}', [i + 1])" /></td>
              <td><input v-model="f.upc" class="entrada" maxlength="40" :aria-label="tx(t('UPC {0}', [i + 1]))" /></td>
              <td><input v-model="f.sku_proveedor" class="entrada" maxlength="60" :aria-label="t('Supplier SKU {0}', [i + 1])" /></td>
              <td><button type="button" class="btn-icono" :aria-label="t('Remove row {0}', [i + 1])" @click="filas.splice(i, 1)"><Icono nombre="cerrar" :tam="15" /></button></td>
            </tr>
            <tr v-if="!filas.length"><td :colspan="ejes.length + 6" class="ayuda">{{ t('Write the values above and create the combinations, or add rows one by one.') }}</td></tr>
          </tbody>
        </table>
      </div>
    </template>
    <div v-if="errores.length" class="nota error bloque mt-chico"><ul class="lista-mensajes"><li v-for="(e, i) in errores" :key="i">{{ tx(e) }}</li></ul></div>
    <template #pie>
      <button class="btn" @click="emit('cerrar')">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="guardar"><Icono nombre="check" />{{ tx(props.editar ? t('Save') : agregar ? t('Add variants') : t('Create product')) }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.variantes td { padding: 4px 6px; }
.variantes input { width: 100%; min-width: 70px; }
.combinar { display: grid; gap: 10px; }
</style>
