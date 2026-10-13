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

// Genérico: los 8 primeros dígitos del código de artículo (estilo-color). Se
// crea una vez con sus datos maestros; después solo se agregan tallas (los 3
// últimos dígitos) con lo propio de cada una: UPC y SKU del proveedor.
// generico con valor: agregar tallas; con editar: cambiar sus datos maestros
const props = defineProps({ generico: { type: String, default: '' }, editar: Boolean })
const emit = defineEmits(['cerrar', 'listo'])
const agregar = computed(() => !!props.generico && !props.editar)
const g = reactive({ generico: '', estilo: '', color: '', marca_id: '', grupo_id: '', proveedor_id: '', unidad: 'PAR' })
// Peso neto de una unidad de cada talla (kg); el empaque suma su propia tara
const pesoTodas = ref('')
const nuevaFila = (talla = '', sufijo = '') => ({ talla, sufijo, sku: '', upc: '', sku_proveedor: '', peso: pesoTodas.value })
function pesoParaTodas() {
  for (const f of filas.value) f.peso = pesoTodas.value
}
const filas = ref([nuevaFila()])
// Escala de tallas: la base genérica de la que parten las tallas y sus códigos
const escalas = ref([])
const escalaId = ref('')
const escala = ref(null)
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
    if (!props.editar) escalas.value = (await api.get('/catalogos/escalas/opciones')).filter((e) => e.activo !== false)
    if (props.editar && info.value) {
      const i = info.value
      Object.assign(g, { generico: i.generico, estilo: i.estilo, color: i.color, marca_id: i.marca_id, grupo_id: i.grupo_id, proveedor_id: i.proveedor_id, unidad: i.unidad })
    }
  } catch (e) {
    errorApi(e)
  }
})
const opc = (l) => l.map((x) => ({ valor: x.id, texto: x.texto, sub: x.sub }))
// Escalas de la categoría del grupo elegido (y las que no tienen categoría)
const categoriaGrupo = computed(() => op.grupos.find((x) => String(x.id) === String(g.grupo_id))?.categoria)
const escalasValidas = computed(() => escalas.value.filter((e) => !categoriaGrupo.value || !e.categoria || e.categoria === categoriaGrupo.value))
watch(escalaId, async (id) => {
  escala.value = id ? await api.get(`/catalogos/escalas/${id}/tallas`).catch(() => null) : null
  if (!escala.value) return
  // Sus tallas con su código; se pueden quitar las que no lleva este genérico
  const ya = new Set(agregar.value ? (info.value?.tallas || []).map((x) => String(x.talla).toUpperCase()) : [])
  filas.value = escala.value.tallas.filter((x) => !ya.has(x.talla)).map((x) => nuevaFila(x.talla, x.codigo))
})
// Solo las marcas autorizadas al proveedor elegido
const marcasProveedor = computed(() => op.marcas.filter((m) => g.proveedor_id && (m.proveedores || []).map(String).includes(String(g.proveedor_id))))
watch(() => g.proveedor_id, () => {
  if (g.marca_id && !marcasProveedor.value.some((m) => String(m.id) === String(g.marca_id))) g.marca_id = ''
  if (!g.marca_id && marcasProveedor.value.length === 1) g.marca_id = marcasProveedor.value[0].id
})
// Código que tendrá cada talla si no se escribe: el usual de calzado (talla × 10:
// 7 → 070, 7.5 → 075, 10.5 → 105) si está libre; si no, el primer libre desde 001
const convencional = (t) => {
  const x = String(t || '').trim().replace(',', '.')
  if (!/^\d{1,2}(\.\d)?$/.test(x)) return null
  const n = Math.round(Number(x) * 10)
  return n > 0 && n < 1000 && Math.abs(Number(x) * 10 - n) < 1e-9 ? String(n).padStart(3, '0') : null
}
const codigos = computed(() => {
  const gen = agregar.value ? props.generico : g.generico
  const base = gen ? String(gen).trim().toUpperCase() : '…'
  const usados = new Set(agregar.value ? info.value?.usados || [] : [])
  return filas.value.map((f) => {
    if (f.sku) return f.sku.trim().toUpperCase()
    if (f.sufijo) { usados.add(f.sufijo.trim().toUpperCase()); return `${base}${f.sufijo.trim().toUpperCase()}` }
    let s = convencional(f.talla)
    if (!s || usados.has(s)) {
      let n = 1
      while (usados.has(String(n).padStart(3, '0'))) n++
      s = String(n).padStart(3, '0')
    }
    usados.add(s)
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
  filas.value = [...vacias, ...lista.map((talla) => nuevaFila(talla.toUpperCase()))]
  rapido.value = ''
}
async function guardar() {
  errores.value = []
  const tallas = filas.value.filter((f) => f.talla.trim())
    .map(({ peso, ...f }) => ({ ...f, peso_unitario: peso === '' || peso === null ? null : Number(peso) }))
  ocupado.value = true
  try {
    if (props.editar) {
      const r = await api.put(`/catalogos/genericos/${props.generico}`, { ...g, marca_id: Number(g.marca_id), grupo_id: Number(g.grupo_id), proveedor_id: Number(g.proveedor_id) })
      avisar(t('Generic {0} updated in all its sizes.', [props.generico]))
      emit('listo', r)
      return
    }
    const r = agregar.value
      ? await api.post(`/catalogos/genericos/${props.generico}/tallas`, { tallas, escala_id: Number(escalaId.value) || null })
      : await api.post('/catalogos/genericos', { ...g, marca_id: Number(g.marca_id), grupo_id: Number(g.grupo_id), proveedor_id: Number(g.proveedor_id), tallas, escala_id: Number(escalaId.value) || null })
    avisar(agregar.value ? t('{0} sizes added to {1}.', [tallas.length, props.generico]) : t('Generic {0} created with {1} sizes. Complete its technical sheet in Products.', [r.generico, r.tallas.length]))
    emit('listo', r)
  } catch (e) {
    errores.value = [e.message, ...(e.detalle || []).map((d) => d.mensaje)]
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <Modal :titulo="tx(props.editar ? t('Edit generic {0}', [props.generico]) : agregar ? t('Add sizes to generic {0}', [props.generico]) : t('New generic'))" ancho="820px" @cerrar="emit('cerrar')">
    <p class="ayuda">{{ t('The generic groups the sizes of one style and color: they share the technical sheet and the HS code. Codes follow your company\'s own format.') }}</p>
    <div v-if="agregar && info" class="doc-meta" style="margin-top: 6px">
      <span>{{ t('Style') }} <b>{{ tx(info.estilo) }}</b></span><span>{{ t('Color') }} <b>{{ tx(info.color) }}</b></span><span>{{ t('Unit') }} <b>{{ tx(info.unidad) }}</b></span>
      <span>{{ t('Sizes') }} <b>{{ tx(info.tallas.filter((t) => t.tipo === 'SOLIDO').map((t) => t.talla).join(', ') || '—') }}</b></span>
    </div>
    <div v-else-if="!agregar" class="rejilla-campos mt-chico">
      <label class="campo"><span class="req">{{ t('Generic code') }}</span><input v-model="g.generico" class="entrada" maxlength="40" :placeholder="t('e.g. 30095129 or VN0A5KRF-BLK')" :disabled="props.editar" /></label>
      <label class="campo"><span class="req">{{ t('Style') }}</span><input v-model="g.estilo" class="entrada" maxlength="40" /></label>
      <label class="campo"><span class="req">{{ t('Color') }}</span><input v-model="g.color" class="entrada" maxlength="60" /></label>
      <div class="campo"><span class="req">{{ t('Supplier') }}</span><SelectBusqueda v-model="g.proveedor_id" :opciones="opc(op.proveedores)" :etiqueta="t('Supplier')" /></div>
      <div class="campo"><span class="req">{{ t('Brand') }}</span><SelectBusqueda v-model="g.marca_id" :opciones="opc(marcasProveedor)" :etiqueta="t('Brand')" :deshabilitado="!g.proveedor_id"
            :placeholder="tx(g.proveedor_id ? t('Choose…') : t('Choose the supplier first'))" /></div>
      <div class="campo"><span class="req">{{ t('Item group') }}</span><SelectBusqueda v-model="g.grupo_id" :opciones="opc(op.grupos)" :etiqueta="t('Item group')" /></div>
      <label class="campo"><span class="req">{{ t('Unit of its sizes') }}</span><Seleccion v-model="g.unidad" class="entrada"><option v-for="u in unidadesArticulo()" :key="u" :value="u">{{ etiquetaUnidad(u) }}</option></Seleccion></label>
    </div>
    <p v-if="props.editar" class="ayuda mt-chico">{{ t('Changes apply to every size of the generic. Sizes, UPC and supplier SKU are edited per item in the list view.') }}</p>

    <template v-if="!props.editar">
    <h3 class="mt">{{ t('Sizes') }}</h3>
    <div class="rejilla-campos" style="margin: 6px 0">
      <div class="campo"><span>{{ t('Size scale') }}</span>
        <SelectBusqueda v-model="escalaId" :opciones="escalasValidas.map((e) => ({ valor: e.id, texto: e.texto, sub: e.sub }))" :vacio="t('No scale (type the sizes)')" :etiqueta="t('Size scale')" />
        <small class="ayuda">{{ t('Loads its sizes in order with their size codes; remove the ones this generic does not have. Codes can be changed.') }}</small></div>
    </div>
    <div class="fila-flex" style="gap: 6px; margin: 6px 0 4px">
      <input v-model="rapido" class="entrada" style="max-width: 300px" :placeholder="t('Quick: 7-10, 12 · 6.5-9.5 · S-XL')" @keydown.enter.prevent="aplicarRapido" />
      <button type="button" class="btn btn-chico" @click="aplicarRapido">{{ t('Add these sizes') }}</button>
      <input v-model="pesoTodas" class="entrada" type="number" min="0" step="any" style="max-width: 150px; margin-inline-start: auto" :placeholder="t('Unit weight kg')" :aria-label="t('Unit weight for all sizes')" />
      <button type="button" class="btn btn-chico" :disabled="pesoTodas === ''" @click="pesoParaTodas">{{ t('Same weight for all') }}</button>
    </div>
    <p class="ayuda" style="margin: 0 0 8px">{{ t('Combine ranges and single sizes for gaps (e.g. 7-10, 12, 14). Item code: type your own, or leave it empty to use the generic plus a size code.') }}</p>
    <table class="tabla tallas" v-tarjetas>
      <thead><tr><th>{{ t('Size *') }}</th><th>{{ t('Size code') }}</th><th>{{ t('Item code') }}</th><th>{{ t('Unit weight kg') }}</th><th>UPC</th><th>{{ t('Supplier SKU') }}</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(f, i) in filas" :key="i">
          <td><input v-model="f.talla" class="entrada" maxlength="20" :aria-label="t('Size {0}', [i + 1])" /></td>
          <td><input v-model="f.sufijo" class="entrada" maxlength="20" :placeholder="t('Auto')" :aria-label="t('Size code {0}', [i + 1])" :disabled="!!f.sku" /></td>
          <td><input v-model="f.sku" class="entrada" maxlength="40" :placeholder="codigos[i]" :aria-label="t('Item code {0}', [i + 1])" /></td>
          <td><input v-model="f.peso" class="entrada" type="number" min="0" step="any" style="width: 90px" :aria-label="t('Unit weight {0}', [i + 1])" /></td>
          <td><input v-model="f.upc" class="entrada" maxlength="40" :aria-label="tx(t('UPC {0}', [i + 1]))" /></td>
          <td><input v-model="f.sku_proveedor" class="entrada" maxlength="60" :aria-label="t('Supplier SKU {0}', [i + 1])" /></td>
          <td><button type="button" class="btn-icono" :aria-label="t('Remove row {0}', [i + 1])" @click="filas.splice(i, 1)"><Icono nombre="cerrar" :tam="15" /></button></td>
        </tr>
      </tbody>
    </table>
    <button type="button" class="btn btn-chico mt-chico" @click="filas.push(nuevaFila())"><Icono nombre="mas" :tam="14" />{{ t('Add row') }}</button>
    </template>
    <div v-if="errores.length" class="nota error bloque mt-chico"><ul class="lista-mensajes"><li v-for="(e, i) in errores" :key="i">{{ tx(e) }}</li></ul></div>
    <template #pie>
      <button class="btn" @click="emit('cerrar')">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado" @click="guardar"><Icono nombre="check" />{{ tx(props.editar ? t('Save') : agregar ? t('Add sizes') : t('Create generic')) }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.tallas td { padding: 4px 6px; }
.tallas input { width: 100%; min-width: 70px; }
</style>
