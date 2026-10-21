<script setup>
import { etiquetaUnidad, unidadesArticulo } from '@/nucleo/unidades.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Asistente from '@/componentes/Asistente.vue'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { enfocarUltimo } from '@/nucleo/utils'
import { avisar, errorApi } from '@/stores/ui'
import { ejesDeFamilia, opcionesDe, useVariantes } from '@/modulos/productos/variantes.js'

// Nuevo producto, paso a paso (como en el ERP): qué tipo de producto es (su
// familia dice con qué atributos se distinguen sus variantes), sus datos
// generales, sus variantes (escritas o combinadas) y una revisión antes de
// crearlo. Sirve para cualquier rubro: calzado, químicos, materias primas,
// alimentos… El borrador se guarda en el servidor y se retoma al volver.
const router = useRouter()
const BORRADOR = 'producto-nuevo'
const g = reactive({ generico: '', nombre: '', estilo: '', color: '', marca_id: '', grupo_id: '', proveedor_id: '', grupo_producto_id: '', unidad: '' })
const op = reactive({ marcas: [], grupos: [], proveedores: [] })
const { atributos, familias, escalaId, valores, filas, pesoTodas, cargar, ejes, escalasDe, usarEscala, nuevaFila, totalCombinaciones, combinar,
  pesoParaTodas, vacia, paraEnviar } = useVariantes(g)
const actual = ref(0)
const ocupado = ref(false)
const cargado = ref(false)
const errores = ref([])
const guardado = ref('')
const intentados = reactive(new Set())

onMounted(async () => {
  try {
    await cargar()
    const [m, gr, p, b] = await Promise.all([...['marcas', 'grupos', 'proveedores'].map((x) => api.get(`/catalogos/${x}/opciones`)),
      api.get('/perfil/borradores', { prefijo: BORRADOR }).catch(() => [])])
    Object.assign(op, { marcas: m, grupos: gr, proveedores: p })
    g.unidad = unidadesArticulo()[0] || ''
    const previo = (b || []).find((x) => x.clave === BORRADOR)
    if (previo?.datos) {
      Object.assign(g, previo.datos.g || {})
      Object.assign(valores, previo.datos.valores || {})
      filas.value = previo.datos.filas || []
      actual.value = previo.datos.actual || 0
      guardado.value = t('Draft resumed')
    }
  } catch (e) {
    errorApi(e)
  } finally {
    cargado.value = true
  }
})

// Familias en árbol (con su ruta) y los atributos que distinguen sus variantes
const nombreAtributo = (c) => tx(atributos.value.find((a) => a.codigo === c)?.nombre || c)
// (los heredados de la antecesora más cercana que los tenga; si ninguna, todos los activos)
const familiasVista = computed(() => familias.value.map((f) => {
  const ejes = ejesDeFamilia(familias.value, f.id)
  return { ...f, ejesTexto: ejes.map(nombreAtributo).join(' · '), heredados: !f.ejes_variante?.length && ejes.length > 0 }
}))
const familia = computed(() => familias.value.find((f) => String(f.id) === String(g.grupo_producto_id)) || null)
const opc = (l) => l.map((x) => ({ valor: x.id, texto: x.texto, sub: x.sub }))
// Solo las marcas autorizadas al proveedor elegido
const marcasProveedor = computed(() => op.marcas.filter((m) => g.proveedor_id && (m.proveedores || []).map(String).includes(String(g.proveedor_id))))
watch(() => g.proveedor_id, () => {
  if (g.marca_id && !marcasProveedor.value.some((m) => String(m.id) === String(g.marca_id))) g.marca_id = ''
  if (!g.marca_id && marcasProveedor.value.length === 1) g.marca_id = marcasProveedor.value[0].id
})

// Lo que falta en cada paso (se muestra al intentar avanzar)
const faltan = computed(() => ({
  tipo: [],
  general: [
    !g.generico.trim() && t('Write the product code.'),
    !g.proveedor_id && t('Choose the supplier.'),
    !g.marca_id && t('Choose the brand.'),
    !g.grupo_id && t('Choose the item group.'),
    !g.unidad && t('Choose the unit.'),
  ].filter(Boolean),
  variantes: [],
  revisar: [],
}))
const variantes = computed(() => filas.value.filter((f) => !vacia(f)))
const PASOS = () => [
  { clave: 'tipo', titulo: t('Type of product') },
  { clave: 'general', titulo: t('General data') },
  { clave: 'variantes', titulo: t('Variants') },
  { clave: 'revisar', titulo: t('Review and create') },
]
const pasos = computed(() => PASOS().map((p) => ({
  ...p, errores: intentados.has(p.clave) ? faltan.value[p.clave].length : 0,
  completo: p.clave === 'tipo' ? cargado.value && actual.value > 0 : p.clave === 'general' ? !faltan.value.general.length && !!g.generico
    : p.clave === 'variantes' ? variantes.value.length > 0 : false,
})))
const clave = computed(() => PASOS()[actual.value].clave)
function siguiente() {
  intentados.add(clave.value)
  if (faltan.value[clave.value].length) return
  actual.value++
  guardarBorrador(true)
}
function ir(i) {
  // Se puede volver siempre; avanzar solo si lo anterior está completo
  if (i > actual.value && faltan.value.general.length && i > 1) {
    intentados.add('general')
    actual.value = Math.min(i, 1)
    return
  }
  actual.value = i
}

async function guardarBorrador(silencioso = false) {
  try {
    await api.put(`/perfil/borradores/${BORRADOR}`, { titulo: g.generico || t('New product'),
      datos: JSON.parse(JSON.stringify({ g, valores, filas: filas.value, actual: actual.value })) })
    guardado.value = t('Draft saved')
    if (silencioso !== true) avisar(t('Draft saved. Continue it later from New product.'))
  } catch (e) {
    if (silencioso !== true) errorApi(e)
  }
}
async function crear() {
  intentados.add('general')
  if (faltan.value.general.length) {
    actual.value = 1
    return
  }
  errores.value = []
  ocupado.value = true
  try {
    const r = await api.post('/catalogos/genericos', {
      ...g, marca_id: Number(g.marca_id), grupo_id: Number(g.grupo_id), proveedor_id: Number(g.proveedor_id),
      grupo_producto_id: Number(g.grupo_producto_id) || null, estilo: g.estilo || null, color: g.color || null, nombre: g.nombre || null,
      tallas: paraEnviar(), escala_id: Number(escalaId.value) || null,
    })
    await api.del(`/perfil/borradores/${BORRADOR}`).catch(() => {})
    avisar(t('Product {0} created with {1} variants. Now complete its technical sheet.', [r.generico, r.tallas.length]))
    router.push(`/productos/${r.producto_id}`)
  } catch (e) {
    errores.value = [e.message, ...(e.detalle || []).map((d) => d.mensaje)]
  } finally {
    ocupado.value = false
  }
}
async function cerrar() {
  router.push('/productos/catalogo')
}
async function descartar() {
  await api.del(`/perfil/borradores/${BORRADOR}`).catch(() => {})
  Object.assign(g, { generico: '', nombre: '', estilo: '', color: '', marca_id: '', grupo_id: '', proveedor_id: '', grupo_producto_id: '' })
  filas.value = []
  for (const k of Object.keys(valores)) valores[k] = ''
  actual.value = 0
  guardado.value = ''
  intentados.clear()
}
const nombreDe = (lista, id) => tx(lista.find((x) => String(x.id) === String(id))?.texto || '—')
</script>

<template>
  <Asistente v-if="cargado" :documento="g.generico ? t('New product {0}', [g.generico]) : t('New product')" :pasos="pasos" :actual="actual"
             :ocupado="ocupado" :guardado="guardado" :texto-final="t('Create product')" @ir="ir" @anterior="actual--" @siguiente="siguiente"
             @guardar="guardarBorrador" @finalizar="crear" @cerrar="cerrar">
    <div v-if="intentados.has(clave) && faltan[clave].length" class="nota error bloque" role="alert">
      <ul class="lista-mensajes"><li v-for="(m, i) in faltan[clave]" :key="i">{{ m }}</li></ul>
    </div>

    <!-- 1. Tipo de producto: su familia -->
    <section v-if="clave === 'tipo'" class="np-paso">
      <p class="ayuda">{{ t('The family is the kind of product (footwear, chemicals, raw materials, food…). It says which attributes tell its variants apart and which labels, packing and classification rules it uses. Choose one or continue without a family.') }}</p>
      <div class="np-familias" role="radiogroup" :aria-label="t('Product family')">
        <label class="np-familia" :class="{ elegida: !g.grupo_producto_id }">
          <input v-model="g.grupo_producto_id" type="radio" value="" class="oculto-visual" />
          <span class="np-familia-nombre">{{ t('Without family') }}</span>
          <span class="ayuda">{{ t('Its variants use every active variant attribute.') }}</span>
        </label>
        <label v-for="f in familiasVista" :key="f.id" class="np-familia" :class="{ elegida: String(g.grupo_producto_id) === String(f.id) }">
          <input v-model="g.grupo_producto_id" type="radio" :value="f.id" class="oculto-visual" />
          <span class="np-familia-nombre">{{ tx(f.nombre) }}</span>
          <span v-if="f.ruta && f.ruta !== f.nombre" class="ayuda">{{ tx(f.ruta) }}</span>
          <span class="np-ejes"><Icono nombre="capas" :tam="13" />{{ f.ejesTexto ? t('Variants by {0}', [f.ejesTexto]) : t('Its variants use every active variant attribute.') }}<template v-if="f.heredados"> ({{ t('from its parent') }})</template></span>
        </label>
      </div>
      <router-link to="/grupos-producto" class="enlace np-crear"><Icono nombre="mas" :tam="14" />{{ t('Create or change families') }}</router-link>
    </section>

    <!-- 2. Datos generales -->
    <section v-else-if="clave === 'general'" class="np-paso">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Product code') }}</span>
          <input v-model="g.generico" class="entrada" maxlength="40" :placeholder="t('e.g. 30095129, QUIM-001 or VN0A5KRF-BLK')" />
          <small class="ayuda">{{ t('Your own code; each variant gets its item code from it.') }}</small></label>
        <label class="campo"><span>{{ t('Name') }}</span><input v-model="g.nombre" class="entrada" maxlength="200" /></label>
        <div class="campo"><span class="req">{{ t('Supplier') }}</span><SelectBusqueda v-model="g.proveedor_id" :opciones="opc(op.proveedores)" :etiqueta="t('Supplier')" /></div>
        <div class="campo"><span class="req">{{ t('Brand') }}</span><SelectBusqueda v-model="g.marca_id" :opciones="opc(marcasProveedor)" :etiqueta="t('Brand')" :deshabilitado="!g.proveedor_id"
              :placeholder="tx(g.proveedor_id ? t('Choose…') : t('Choose the supplier first'))" /></div>
        <div class="campo"><span class="req">{{ t('Item group') }}</span><SelectBusqueda v-model="g.grupo_id" :opciones="opc(op.grupos)" :etiqueta="t('Item group')" /></div>
        <label class="campo"><span class="req">{{ t('Unit of its variants') }}</span><Seleccion v-model="g.unidad" class="entrada"><option v-for="u in unidadesArticulo()" :key="u" :value="u">{{ etiquetaUnidad(u) }}</option></Seleccion></label>
        <label class="campo"><span>{{ t('Style / model') }}</span><input v-model="g.estilo" class="entrada" maxlength="40" :placeholder="t('Optional')" /></label>
        <label class="campo"><span>{{ t('Fixed color') }}</span><input v-model="g.color" class="entrada" maxlength="60" :placeholder="t('Optional: if every variant has the same color')" /></label>
      </div>
    </section>

    <!-- 3. Variantes -->
    <section v-else-if="clave === 'variantes'" class="np-paso">
      <p v-if="!ejes.length" class="ayuda">{{ t('There are no variant attributes: each row is one item without variants.') }}</p>
      <template v-else>
        <p class="ayuda">{{ t('Write the values of each attribute (commas and ranges: 7-10, 6.5-9.5, S-XL) or take them from a scale, then create every combination. You can also add rows one by one.') }}</p>
        <div class="np-ejes-captura">
          <div v-for="a in ejes" :key="a.codigo" class="campo">
            <span>{{ tx(a.nombre) }}<small v-if="a.unidad" class="ayuda"> ({{ a.unidad }})</small></span>
            <div class="fila-flex gap-2">
              <input v-model="valores[a.codigo]" class="entrada" :list="`np-op-${a.codigo}`" :aria-label="t('Values of {0}', [tx(a.nombre)])"
                     :placeholder="a.tipo === 'opcion' ? opcionesDe(a).join(', ') : t('e.g. 7-10, 12 · S-XL · 250 ml, 1 L')" />
              <Seleccion v-if="escalasDe(a).length" class="entrada max-s" :model-value="''" :aria-label="t('Value scale')" @update:model-value="usarEscala(a, $event)">
                <option value="">{{ t('From a scale…') }}</option>
                <option v-for="e in escalasDe(a)" :key="e.id" :value="e.id">{{ tx(e.nombre) }}</option>
              </Seleccion>
            </div>
            <datalist v-if="a.tipo === 'opcion'" :id="`np-op-${a.codigo}`"><option v-for="o in opcionesDe(a)" :key="o" :value="o" /></datalist>
          </div>
        </div>
        <button type="button" class="btn" :disabled="!totalCombinaciones" @click="combinar">
          <Icono nombre="mas" :tam="15" />{{ t('Create the {0} combinations', [totalCombinaciones]) }}</button>
      </template>
      <div class="fila-flex gap-2 np-acciones">
        <button type="button" class="btn btn-chico" @click="filas.push(nuevaFila()); enfocarUltimo('.np-tabla tbody tr')"><Icono nombre="mas" :tam="14" />{{ t('Add row') }}</button>
        <input v-model="pesoTodas" class="entrada max-xs empuja-fin" type="number" min="0" step="any" :placeholder="t('Unit weight kg')" :aria-label="t('Unit weight for all variants')" />
        <button type="button" class="btn btn-chico" :disabled="pesoTodas === ''" @click="pesoParaTodas">{{ t('Same weight for all') }}</button>
      </div>
      <div class="tabla-marco tabla-captura">
        <table class="tabla np-tabla" v-tarjetas>
          <thead><tr><th v-for="a in ejes" :key="a.codigo">{{ tx(a.nombre) }}</th><th>{{ t('Item code') }}</th>
            <th>{{ t('Unit weight kg') }}</th><th>UPC</th><th>{{ t('Supplier SKU') }}</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(f, i) in filas" :key="i">
              <td v-for="a in ejes" :key="a.codigo"><input v-model="f.valores[a.codigo]" class="entrada" maxlength="60" :list="a.tipo === 'opcion' ? `np-op-${a.codigo}` : undefined" :aria-label="`${tx(a.nombre)} ${i + 1}`" /></td>
              <td><input v-model="f.sku" class="entrada" maxlength="40" :placeholder="t('Auto')" :aria-label="t('Item code {0}', [i + 1])" /></td>
              <td><input v-model="f.peso" class="entrada ancho-s" type="number" min="0" step="any" :aria-label="t('Unit weight {0}', [i + 1])" /></td>
              <td><input v-model="f.upc" class="entrada" maxlength="40" :aria-label="tx(t('UPC {0}', [i + 1]))" /></td>
              <td><input v-model="f.sku_proveedor" class="entrada" maxlength="60" :aria-label="t('Supplier SKU {0}', [i + 1])" /></td>
              <td><button type="button" class="btn-icono" :aria-label="t('Remove row {0}', [i + 1])" @click="filas.splice(i, 1)"><Icono nombre="cerrar" :tam="15" /></button></td>
            </tr>
            <tr v-if="!filas.length"><td :colspan="ejes.length + 5" class="ayuda">{{ t('No variants yet. You can also create the product now and add its variants later from its page.') }}</td></tr>
          </tbody>
        </table>
      </div>
      <p class="ayuda">{{ t('Item code: type your own, or leave it empty to use the product code plus a variant code (from the value scale, if one was used).') }}</p>
    </section>

    <!-- 4. Revisar -->
    <section v-else class="np-paso">
      <div class="np-resumen">
        <div><span>{{ t('Product code') }}</span><b>{{ g.generico || '—' }}</b></div>
        <div><span>{{ t('Name') }}</span><b>{{ g.nombre || '—' }}</b></div>
        <div><span>{{ t('Product family') }}</span><b>{{ familia ? tx(familia.nombre) : t('Without family') }}</b></div>
        <div><span>{{ t('Supplier') }}</span><b>{{ nombreDe(op.proveedores, g.proveedor_id) }}</b></div>
        <div><span>{{ t('Brand') }}</span><b>{{ nombreDe(op.marcas, g.marca_id) }}</b></div>
        <div><span>{{ t('Item group') }}</span><b>{{ nombreDe(op.grupos, g.grupo_id) }}</b></div>
        <div><span>{{ t('Unit') }}</span><b>{{ etiquetaUnidad(g.unidad) }}</b></div>
        <div><span>{{ t('Variants') }}</span><b>{{ variantes.length }}</b></div>
      </div>
      <p v-if="variantes.length" class="ayuda">{{ variantes.slice(0, 40).map((f) => Object.values(f.valores).filter(Boolean).join(' · ')).join(', ') }}<template v-if="variantes.length > 40"> …</template></p>
      <p class="nota info"><Icono nombre="info" :tam="16" />{{ t('After creating it, its page opens: complete the technical sheet there; the classification, the labels and the packing use it.') }}</p>
      <div v-if="errores.length" class="nota error bloque mt-chico" role="alert"><ul class="lista-mensajes"><li v-for="(e, i) in errores" :key="i">{{ tx(e) }}</li></ul></div>
      <button v-if="guardado" type="button" class="btn btn-fantasma btn-chico" @click="descartar">{{ t('Discard draft and start over') }}</button>
    </section>
  </Asistente>
  <div v-else class="vacio">{{ t('Loading…') }}</div>
</template>

<style scoped>
.np-paso { display: flex; flex-direction: column; gap: 14px; }
.np-familias { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }
.np-familia { display: flex; flex-direction: column; gap: 4px; border: 1px solid var(--linea); border-radius: var(--radio-panel); padding: 12px 14px;
  background: var(--superficie); cursor: pointer; transition: border-color var(--rapido, 150ms), background var(--rapido, 150ms); }
.np-familia:hover { border-color: var(--borde-hover); }
.np-familia.elegida { border-color: var(--acento); background: var(--acento-claro); box-shadow: 0 0 0 1px var(--acento); }
.np-familia:focus-within { outline: 2px solid var(--acento); outline-offset: 2px; }
.np-familia-nombre { font-weight: 650; }
.np-ejes { display: inline-flex; gap: 5px; align-items: center; font-size: 0.82rem; color: var(--tinta-2); }
.np-crear { align-self: flex-start; display: inline-flex; gap: 5px; align-items: center; }
.np-ejes-captura { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
.np-acciones { margin-top: 4px; }
.np-tabla td { padding: 4px 6px; }
.np-tabla input { width: 100%; min-width: 70px; }
.np-resumen { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px 18px; border: 1px solid var(--linea);
  border-radius: var(--radio-panel); padding: 14px 16px; background: var(--superficie); }
.np-resumen div { display: flex; flex-direction: column; gap: 2px; }
.np-resumen span { font-size: 0.78rem; color: var(--tinta-3); }
</style>
