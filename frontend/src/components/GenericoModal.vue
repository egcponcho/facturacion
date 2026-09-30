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
const props = defineProps({ generico: { type: String, default: '' } }) // con valor: agregar tallas
const emit = defineEmits(['cerrar', 'listo'])
const agregar = computed(() => !!props.generico)
const g = reactive({ generico: '', estilo: '', color: '', marca_id: '', grupo_id: '', proveedor_id: '', unidad: 'PAR', nombre: '' })
const filas = ref([{ talla: '', sufijo: '', upc: '', sku_proveedor: '' }])
const rapido = ref('')
const op = reactive({ marcas: [], grupos: [], proveedores: [] })
const info = ref(null)
const errores = ref([])
const ocupado = ref(false)

onMounted(async () => {
  try {
    if (agregar.value) info.value = await api.get(`/catalogos/genericos/${props.generico}`)
    else {
      const [m, gr, p] = await Promise.all(['marcas', 'grupos', 'proveedores'].map((t) => api.get(`/catalogos/${t}/opciones`)))
      Object.assign(op, { marcas: m, grupos: gr, proveedores: p })
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
    if (f.sufijo) return `${gen}${f.sufijo}`
    while (usados.has(String(n).padStart(3, '0'))) n++
    const s = String(n++).padStart(3, '0')
    return gen && /^\d{8}$/.test(gen) ? `${gen}${s}` : `········${s}`
  })
})
// "7-12", "S,M,L,XL" o "6.5-9.5" arman las filas de tallas
function aplicarRapido() {
  const t = rapido.value.trim()
  if (!t) return
  let lista = []
  const m = t.match(/^(\d+(?:\.5)?)\s*(?:-|to|a)\s*(\d+(?:\.5)?)$/i)
  if (m) {
    const paso = t.includes('.5') ? 0.5 : 1
    for (let x = Number(m[1]); x <= Number(m[2]) + 1e-9; x += paso) lista.push(String(x))
  } else lista = t.split(/[,\s;]+/).filter(Boolean)
  const vacias = filas.value.filter((f) => f.talla || f.upc || f.sku_proveedor)
  filas.value = [...vacias, ...lista.map((talla) => ({ talla: talla.toUpperCase(), sufijo: '', upc: '', sku_proveedor: '' }))]
  rapido.value = ''
}
async function guardar() {
  errores.value = []
  const tallas = filas.value.filter((f) => f.talla.trim())
  ocupado.value = true
  try {
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
  <Modal :titulo="agregar ? `Add sizes to generic ${props.generico}` : 'New generic'" ancho="820px" @cerrar="emit('cerrar')">
    <p class="ayuda">The item code has 11 digits: the first 8 are the generic (style-color) and the last 3 the size. The technical sheet and the HS code belong to the generic.</p>
    <div v-if="agregar && info" class="doc-meta" style="margin-top: 6px">
      <span>Style <b>{{ info.estilo }}</b></span><span>Color <b>{{ info.color }}</b></span><span>Unit <b>{{ info.unidad }}</b></span>
      <span>Sizes <b>{{ info.tallas.filter((t) => t.tipo === 'SOLIDO').map((t) => t.talla).join(', ') || '—' }}</b></span>
    </div>
    <div v-else-if="!agregar" class="rejilla-campos mt-chico">
      <label class="campo"><span class="req">Generic code (8 digits)</span><input v-model="g.generico" class="entrada" maxlength="8" inputmode="numeric" placeholder="30095129" /></label>
      <label class="campo"><span class="req">Style</span><input v-model="g.estilo" class="entrada" maxlength="40" /></label>
      <label class="campo"><span class="req">Color</span><input v-model="g.color" class="entrada" maxlength="60" /></label>
      <div class="campo"><span class="req">Supplier</span><SelectBusqueda v-model="g.proveedor_id" :opciones="opc(op.proveedores)" etiqueta="Supplier" /></div>
      <div class="campo"><span class="req">Brand</span><SelectBusqueda v-model="g.marca_id" :opciones="opc(op.marcas)" etiqueta="Brand" /></div>
      <div class="campo"><span class="req">Item group</span><SelectBusqueda v-model="g.grupo_id" :opciones="opc(op.grupos)" etiqueta="Item group" /></div>
      <label class="campo"><span class="req">Unit of its sizes</span><select v-model="g.unidad" class="entrada"><option value="PAR">Pairs (PAR)</option><option value="UN">Units (UN)</option></select></label>
      <label class="campo" style="grid-column: span 2"><span>Commercial name</span><input v-model="g.nombre" class="entrada" maxlength="200" placeholder="E.g. Era canvas sneaker" /></label>
    </div>

    <h3 class="mt">Sizes</h3>
    <div class="fila-flex" style="gap: 6px; margin: 6px 0 10px">
      <input v-model="rapido" class="entrada" style="max-width: 280px" placeholder="Quick: 7-12, 6.5-9.5 or S, M, L, XL" @keydown.enter.prevent="aplicarRapido" />
      <button type="button" class="btn btn-chico" @click="aplicarRapido">Add these sizes</button>
    </div>
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
    <div v-if="errores.length" class="nota error bloque mt-chico"><ul class="lista-mensajes"><li v-for="(e, i) in errores" :key="i">{{ e }}</li></ul></div>
    <template #pie>
      <button class="btn" @click="emit('cerrar')">Cancel</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="guardar"><Icono nombre="check" />{{ agregar ? 'Add sizes' : 'Create generic' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.tallas td { padding: 4px 6px; }
.tallas input { width: 100%; min-width: 70px; }
</style>
