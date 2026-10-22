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
import { usePerfil } from '@/modulos/productos/perfil.js'
import { opcionesDe, useVariantes } from '@/modulos/productos/variantes.js'

// Producto (de cualquier tipo) y sus variantes. El producto se crea una vez con
// su código, su nombre y su unidad (lo demás, si la empresa o su familia lo
// exigen: productos/perfil.js); sus variantes se distinguen por los atributos
// de variante de su familia. Las variantes se escriben fila por fila o se
// combinan: todos los valores de un atributo por todos los de otro.
// generico con valor: agregar variantes; con editar: cambiar sus datos maestros
const props = defineProps({ generico: { type: String, default: '' }, editar: Boolean })
const emit = defineEmits(['cerrar', 'listo'])
const agregar = computed(() => !!props.generico && !props.editar)
const g = reactive({ generico: '', nombre: '', estilo: '', color: '', marca_id: '', grupo_id: '', proveedor_id: '', grupo_producto_id: '', unidad: '' })
const op = reactive({ marcas: [], grupos: [], proveedores: [] })
const info = ref(null)
const errores = ref([])
const ocupado = ref(false)
const { familias, escalaId, valores, filas, pesoTodas, cargar, ejes, escalasDe, usarEscala, nuevaFila, totalCombinaciones, combinar,
  pesoParaTodas, paraEnviar } = useVariantes(g, info)

onMounted(async () => {
  try {
    if (props.generico) info.value = await api.get(`/catalogos/genericos/${props.generico}`)
    await cargar()
    if (!agregar.value) {
      const [m, gr, p] = await Promise.all(['marcas', 'grupos', 'proveedores'].map((x) => api.get(`/catalogos/${x}/opciones`)))
      Object.assign(op, { marcas: m, grupos: gr, proveedores: p })
    }
    if (!g.unidad && unidadesArticulo().length === 1) g.unidad = unidadesArticulo()[0]
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

async function guardar() {
  errores.value = []
  const tallas = paraEnviar()
  const maestros = { ...g, marca_id: Number(g.marca_id) || null, grupo_id: Number(g.grupo_id) || null, proveedor_id: Number(g.proveedor_id) || null,
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
      : t('Product {0} created with {1} variants.', [r.generico, r.tallas.length]))
    emit('listo', r)
  } catch (e) {
    errores.value = [e.message, ...(e.detalle || []).map((d) => d.mensaje)]
  } finally {
    ocupado.value = false
  }
}
// Con proveedor, solo sus marcas autorizadas; sin proveedor, todas
const marcasProveedor = computed(() => (g.proveedor_id
  ? op.marcas.filter((m) => (m.proveedores || []).map(String).includes(String(g.proveedor_id))) : op.marcas))
watch(() => g.proveedor_id, () => {
  if (g.marca_id && !marcasProveedor.value.some((m) => String(m.id) === String(g.marca_id))) g.marca_id = ''
  if (g.proveedor_id && !g.marca_id && marcasProveedor.value.length === 1) g.marca_id = marcasProveedor.value[0].id
})
// Lo que la empresa o la familia exigen se marca como obligatorio
const { exige } = usePerfil(() => g.grupo_producto_id)
const variantesActuales = computed(() => (info.value?.tallas || []).filter((x) => x.tipo === 'SOLIDO')
  .map((x) => Object.values(x.valores || {}).join(' · ') || x.sku).join(', '))
</script>

<template>
  <Modal :titulo="tx(props.editar ? t('Edit product {0}', [props.generico]) : agregar ? t('Add variants to {0}', [props.generico]) : t('New product'))" ancho="900px" @cerrar="emit('cerrar')">
    <p class="ayuda">{{ t('A product with its own code, name and unit. Its variants share its data and differ by the variant attributes of its family; the rest of the data is asked only if your company or the family requires it.') }}</p>
    <div v-if="agregar && info" class="doc-meta mt-chico">
      <span>{{ t('Product') }} <b>{{ tx(info.nombre || info.generico) }}</b></span><span>{{ t('Unit') }} <b>{{ tx(info.unidad) }}</b></span>
      <span>{{ t('Variants') }} <b>{{ tx(variantesActuales || '—') }}</b></span>
    </div>
    <div v-else-if="!agregar" class="rejilla-campos mt-chico">
      <label class="campo"><span class="req">{{ t('Product code') }}</span><input v-model="g.generico" class="entrada" maxlength="40" :placeholder="t('Your own format')" :disabled="props.editar" /></label>
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="g.nombre" class="entrada" maxlength="200" /></label>
      <label class="campo"><span class="req">{{ t('Unit of its variants') }}</span><Seleccion v-model="g.unidad" class="entrada"><option value="" disabled>{{ t('Choose…') }}</option><option v-for="u in unidadesArticulo()" :key="u" :value="u">{{ etiquetaUnidad(u) }}</option></Seleccion></label>
      <div class="campo"><span>{{ t('Product family') }}</span>
        <SelectBusqueda v-model="g.grupo_producto_id" :opciones="familias.map((f) => ({ valor: f.id, texto: f.nombre, sub: f.ruta }))" :vacio="t('No family')" :etiqueta="t('Product family')" />
        <small class="ayuda">{{ t('The family says which data its products need and which attributes tell its variants apart.') }}</small></div>
      <div class="campo"><span :class="{ req: exige('proveedor_id') }">{{ t('Supplier') }}</span><SelectBusqueda v-model="g.proveedor_id" :opciones="opc(op.proveedores)" :vacio="t('None')" :etiqueta="t('Supplier')" /></div>
      <div class="campo"><span :class="{ req: exige('marca_id') }">{{ t('Brand') }}</span><SelectBusqueda v-model="g.marca_id" :opciones="opc(marcasProveedor)" :vacio="t('None')" :etiqueta="t('Brand')" /></div>
      <div class="campo"><span :class="{ req: exige('grupo_id') }">{{ t('Item group') }}</span><SelectBusqueda v-model="g.grupo_id" :opciones="opc(op.grupos)" :vacio="t('None')" :etiqueta="t('Item group')" /></div>
      <label class="campo"><span :class="{ req: exige('estilo') }">{{ t('Model') }}</span><input v-model="g.estilo" class="entrada" maxlength="40" :placeholder="t('Optional')" /></label>
      <!-- Un valor fijo de color solo en productos que ya lo tienen (los nuevos fijan un valor eligiendo uno solo en sus variantes) -->
      <label v-if="props.editar && g.color" class="campo"><span>{{ t('Fixed color') }}</span><input v-model="g.color" class="entrada" maxlength="60" /></label>
    </div>
    <p v-if="props.editar" class="ayuda mt-chico">{{ t('Changes apply to every variant of the product. Item codes, barcodes and supplier codes are edited per variant.') }}</p>

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
            <th :class="{ req: exige('peso') }">{{ t('Unit weight kg') }}</th><th :class="{ req: exige('upc') }">{{ t('Barcode') }}</th>
            <th :class="{ req: exige('sku_proveedor') }">{{ t('Supplier code') }}</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(f, i) in filas" :key="i">
              <td v-for="a in ejes" :key="a.codigo"><input v-model="f.valores[a.codigo]" class="entrada" maxlength="60" :list="a.tipo === 'opcion' ? `op-${a.codigo}` : undefined" :aria-label="`${tx(a.nombre)} ${i + 1}`" /></td>
              <td><input v-model="f.sufijo" class="entrada" maxlength="20" :placeholder="t('Auto')" :aria-label="t('Variant code {0}', [i + 1])" :disabled="!!f.sku" /></td>
              <td><input v-model="f.sku" class="entrada" maxlength="40" :placeholder="t('Auto')" :aria-label="t('Item code {0}', [i + 1])" /></td>
              <td><input v-model="f.peso" class="entrada ancho-s" type="number" min="0" step="any" :aria-label="t('Unit weight {0}', [i + 1])" /></td>
              <td><input v-model="f.upc" class="entrada" maxlength="40" :aria-label="t('Barcode {0}', [i + 1])" /></td>
              <td><input v-model="f.sku_proveedor" class="entrada" maxlength="60" :aria-label="t('Supplier code {0}', [i + 1])" /></td>
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
