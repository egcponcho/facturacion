<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { avisar, errorApi } from '../stores/ui'
import Icono from './Icono.vue'
import Modal from './Modal.vue'
import SelectBusqueda from './SelectBusqueda.vue'

// Genérico: los 8 primeros dígitos del código de artículo (estilo-color). Se
// crea una vez con sus datos maestros; después solo se agregan tallas (los 3
// últimos dígitos) con lo propio de cada una: UPC y SKU del proveedor.
// generico con valor: agregar tallas; con editar: cambiar sus datos maestros
const props = defineProps({ generico: { type: String, default: '' }, editar: Boolean })
const emit = defineEmits(['cerrar', 'listo'])
const agregar = computed(() => !!props.generico && !props.editar)
const g = reactive({ generico: '', estilo: '', color: '', marca_id: '', grupo_id: '', proveedor_id: '', unidad: 'PAR' })
const filas = ref([{ talla: '', sufijo: '', upc: '', sku_proveedor: '' }])
const rapido = ref('')
const op = reactive({ marcas: [], grupos: [], proveedores: [] })
const info = ref(null)
const errores = ref([])
const ocupado = ref(false)

onMounted(async () => {
  try {
    if (props.generico) info.value = await api.get(`/catalogos/genericos/${props.generico}`)
    if (!agregar.value) {
      const [m, gr, p] = await Promise.all(['marcas', 'grupos', 'proveedores'].map((t) => api.get(`/catalogos/${t}/opciones`)))
      Object.assign(op, { marcas: m, grupos: gr, proveedores: p })
    }
    if (props.editar && info.value) {
      const i = info.value
      Object.assign(g, { generico: i.generico, estilo: i.estilo, color: i.color, marca_id: i.marca_id, grupo_id: i.grupo_id, proveedor_id: i.proveedor_id, unidad: i.unidad })
    }
  } catch (e) {
    errorApi(e)
  }
})
const opc = (l) => l.map((x) => ({ valor: x.id, texto: x.texto }))
// Código que tendrá cada talla (el siguiente libre si no se escribe)
const codigos = computed(() => {
  const gen = agregar.value ? props.generico : g.generico
  let n = agregar.value ? Number(info.value?.siguiente || 1) : 1
  const usados = new Set(filas.value.map((f) => f.sufijo).filter(Boolean))
  return filas.value.map((f) => {
    const base = gen && /^\d{8}$/.test(gen) ? gen : '········'
    if (f.sufijo) return `${base}${f.sufijo}`
    while (usados.has(String(n).padStart(3, '0'))) n++
    const s = String(n++).padStart(3, '0')
    return `${base}${s}`
  })
})
// "7-10, 12", "6.5-9.5", "S-XL" o "S, M, XL" arman las filas de tallas: se
// pueden combinar tramos y tallas sueltas para los saltos
const LETRAS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
function expandir(t) {
  const lista = []
  for (const tramo of t.split(/[,;]+/).map((x) => x.trim()).filter(Boolean)) {
    const m = tramo.match(/^(\S+)\s*(?:-|to|a)\s*(\S+)$/i)
    const [a, b] = m ? [m[1].toUpperCase(), m[2].toUpperCase()] : []
    if (m && /^\d+(\.5)?$/.test(a) && /^\d+(\.5)?$/.test(b)) {
      const paso = tramo.includes('.5') ? 0.5 : 1
      for (let x = Number(a); x <= Number(b) + 1e-9; x += paso) lista.push(String(x))
    } else if (m && LETRAS.includes(a) && LETRAS.includes(b)) lista.push(...LETRAS.slice(LETRAS.indexOf(a), LETRAS.indexOf(b) + 1))
    else lista.push(...tramo.split(/\s+/))
  }
  return [...new Set(lista)]
}
function aplicarRapido() {
  const t = rapido.value.trim()
  if (!t) return
  const lista = expandir(t)
  const vacias = filas.value.filter((f) => f.talla || f.upc || f.sku_proveedor)
  filas.value = [...vacias, ...lista.map((talla) => ({ talla: talla.toUpperCase(), sufijo: '', upc: '', sku_proveedor: '' }))]
  rapido.value = ''
}
async function guardar() {
  errores.value = []
  const tallas = filas.value.filter((f) => f.talla.trim())
  ocupado.value = true
  try {
    if (props.editar) {
      const r = await api.put(`/catalogos/genericos/${props.generico}`, { ...g, marca_id: Number(g.marca_id), grupo_id: Number(g.grupo_id), proveedor_id: Number(g.proveedor_id) })
      avisar(`Generic ${props.generico} updated in all its sizes.`)
      emit('listo', r)
      return
    }
    const r = agregar.value
      ? await api.post(`/catalogos/genericos/${props.generico}/tallas`, { tallas })
      : await api.post('/catalogos/genericos', { ...g, marca_id: Number(g.marca_id), grupo_id: Number(g.grupo_id), proveedor_id: Number(g.proveedor_id), tallas })
    avisar(agregar.value ? `${tallas.length} sizes added to ${props.generico}.` : `Generic ${r.generico} created with ${r.tallas.length} sizes. Complete its technical sheet in Products.`)
    emit('listo', r)
  } catch (e) {
    errores.value = [e.message, ...(e.detalle || []).map((d) => d.mensaje)]
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <Modal :titulo="props.editar ? `Edit generic ${props.generico}` : agregar ? `Add sizes to generic ${props.generico}` : 'New generic'" ancho="820px" @cerrar="emit('cerrar')">
    <p class="ayuda">The item code has 11 digits: the first 8 are the generic (style-color) and the last 3 the size. The technical sheet and the HS code belong to the generic.</p>
    <div v-if="agregar && info" class="doc-meta" style="margin-top: 6px">
      <span>Style <b>{{ info.estilo }}</b></span><span>Color <b>{{ info.color }}</b></span><span>Unit <b>{{ info.unidad }}</b></span>
      <span>Sizes <b>{{ info.tallas.filter((t) => t.tipo === 'SOLIDO').map((t) => t.talla).join(', ') || '—' }}</b></span>
    </div>
    <div v-else-if="!agregar" class="rejilla-campos mt-chico">
      <label class="campo"><span class="req">Generic code (8 digits)</span><input v-model="g.generico" class="entrada" maxlength="8" inputmode="numeric" placeholder="30095129" :disabled="props.editar" /></label>
      <label class="campo"><span class="req">Style</span><input v-model="g.estilo" class="entrada" maxlength="40" /></label>
      <label class="campo"><span class="req">Color</span><input v-model="g.color" class="entrada" maxlength="60" /></label>
      <div class="campo"><span class="req">Supplier</span><SelectBusqueda v-model="g.proveedor_id" :opciones="opc(op.proveedores)" etiqueta="Supplier" /></div>
      <div class="campo"><span class="req">Brand</span><SelectBusqueda v-model="g.marca_id" :opciones="opc(op.marcas)" etiqueta="Brand" /></div>
      <div class="campo"><span class="req">Item group</span><SelectBusqueda v-model="g.grupo_id" :opciones="opc(op.grupos)" etiqueta="Item group" /></div>
      <label class="campo"><span class="req">Unit of its sizes</span><select v-model="g.unidad" class="entrada"><option value="PAR">Pairs (PAR)</option><option value="UN">Units (UN)</option></select></label>
    </div>
    <p v-if="props.editar" class="ayuda mt-chico">Changes apply to every size of the generic. Sizes, UPC and supplier SKU are edited per item in the list view.</p>

    <template v-if="!props.editar">
    <h3 class="mt">Sizes</h3>
    <div class="fila-flex" style="gap: 6px; margin: 6px 0 4px">
      <input v-model="rapido" class="entrada" style="max-width: 300px" placeholder="Quick: 7-10, 12 · 6.5-9.5 · S-XL" @keydown.enter.prevent="aplicarRapido" />
      <button type="button" class="btn btn-chico" @click="aplicarRapido">Add these sizes</button>
    </div>
    <p class="ayuda" style="margin: 0 0 8px">Combine ranges and single sizes for gaps (e.g. 7-10, 12, 14). Size code: leave it empty and it is generated (next free: {{ agregar ? info?.siguiente || '001' : '001' }}), or type your own 3 digits.</p>
    <table class="tabla tallas">
      <thead><tr><th>Item code</th><th>Size *</th><th>Size code</th><th>UPC</th><th>Supplier SKU</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(f, i) in filas" :key="i">
          <td class="codigo-sac">{{ codigos[i] }}</td>
          <td><input v-model="f.talla" class="entrada" maxlength="20" :aria-label="`Size ${i + 1}`" /></td>
          <td><input v-model="f.sufijo" class="entrada" maxlength="3" inputmode="numeric" placeholder="auto" :aria-label="`Size code ${i + 1}`" /></td>
          <td><input v-model="f.upc" class="entrada" maxlength="40" :aria-label="`UPC ${i + 1}`" /></td>
          <td><input v-model="f.sku_proveedor" class="entrada" maxlength="60" :aria-label="`Supplier SKU ${i + 1}`" /></td>
          <td><button type="button" class="btn-icono" :aria-label="`Remove row ${i + 1}`" @click="filas.splice(i, 1)"><Icono nombre="cerrar" :tam="15" /></button></td>
        </tr>
      </tbody>
    </table>
    <button type="button" class="btn btn-chico mt-chico" @click="filas.push({ talla: '', sufijo: '', upc: '', sku_proveedor: '' })"><Icono nombre="mas" :tam="14" />Add row</button>
    </template>
    <div v-if="errores.length" class="nota error bloque mt-chico"><ul class="lista-mensajes"><li v-for="(e, i) in errores" :key="i">{{ e }}</li></ul></div>
    <template #pie>
      <button class="btn" @click="emit('cerrar')">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="guardar"><Icono nombre="check" />{{ props.editar ? 'Save' : agregar ? 'Add sizes' : 'Create generic' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.tallas td { padding: 4px 6px; }
.tallas input { width: 100%; min-width: 70px; }
</style>
