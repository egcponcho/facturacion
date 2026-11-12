<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { fmtNum } from '@/nucleo/utils'
import { buscarArticulos } from '@/modulos/etiquetado/componentes/buscadores.js'
import { confirmar } from '@/stores/confirmar'
import { avisar, errorApi } from '@/stores/ui'

// Constructor de una receta de empaque: niveles del más externo (arriba) al más
// interno (abajo). Cada nivel es un tipo del catálogo y cuántas unidades del
// nivel de abajo lleva; el más interno, cuántas unidades del artículo. Los
// totales (unidades, volumen y, con un artículo, pesos) los calcula el servidor
// mientras se edita, con las mismas reglas con que se guarda.
const props = defineProps({
  receta: { type: Object, default: null }, // null: receta nueva
  tipos: { type: Array, default: () => [] },
  editable: { type: Boolean, default: true },
})
const emit = defineEmits(['guardada', 'eliminada'])

const nivelVacio = (tipo = '') => ({ tipo_empaque_id: tipo, cantidad: 1, opcional: false, largo: '', ancho: '', alto: '', tara: '', medidas: false })
const form = reactive({ id: null, codigo: '', nombre: '', descripcion: '', version: null, activa: true, niveles: [] })
function cargar(r) {
  Object.assign(form, {
    id: r?.id || null, codigo: r?.codigo || '', nombre: r?.nombre || '', descripcion: r?.descripcion || '', version: r?.version ?? null,
    activa: r?.activa ?? true,
    niveles: r?.niveles?.length
      ? r.niveles.map((n) => ({ ...nivelVacio(n.tipo_empaque_id), cantidad: n.cantidad, opcional: n.opcional,
        ...Object.fromEntries(['largo', 'ancho', 'alto', 'tara'].map((c) => [c, n[c] ?? ''])) }))
      : [nivelVacio((props.tipos.find((x) => x.contiene_productos && x.cuenta_como === 'BULTO') || props.tipos.find((x) => x.contiene_productos))?.id || '')],
  })
  errores.value = []
}
const errores = ref([])
watch(() => props.receta, cargar, { immediate: true })

const tipo = (id) => props.tipos.find((x) => x.id === Number(id))
// Tipos que pueden ir en el nivel i: el primero lleva el artículo; los demás contienen al de abajo
function tiposPara(i) {
  const abajo = i > 0 ? Number(form.niveles[i - 1]?.tipo_empaque_id) : null
  return props.tipos.filter((x) => (i === 0 ? x.contiene_productos : (x.contiene || []).includes(abajo))
    || x.id === Number(form.niveles[i]?.tipo_empaque_id))
}
const arriba = computed(() => [...form.niveles.keys()].reverse()) // índices, del más externo al más interno
function agregarArriba() {
  const i = form.niveles.length
  form.niveles.push(nivelVacio(''))
  form.niveles[i].tipo_empaque_id = tiposPara(i)[0]?.id || ''
}
function agregarAbajo() {
  const dentro = tipo(form.niveles[0]?.tipo_empaque_id)?.contiene || []
  const t0 = props.tipos.find((x) => x.contiene_productos && dentro.includes(x.id))
  form.niveles.unshift(nivelVacio(t0?.id || ''))
}
const quitar = (i) => form.niveles.splice(i, 1)
// Solo se ofrece agregar un nivel si algún tipo del catálogo cabe ahí
const puedeArriba = computed(() => props.tipos.some((x) => (x.contiene || []).includes(Number(form.niveles.at(-1)?.tipo_empaque_id))))
const puedeAbajo = computed(() => props.tipos.some((x) => x.contiene_productos
  && (tipo(form.niveles[0]?.tipo_empaque_id)?.contiene || []).includes(x.id)))

// Totales en vivo
const articulo = ref('')
const calc = ref({ niveles: [], avisos: [] })
let espera = null
function cuerpoNiveles() {
  return form.niveles.map((n) => ({
    tipo_empaque_id: Number(n.tipo_empaque_id) || null, cantidad: n.cantidad === '' ? null : n.cantidad, opcional: n.opcional,
    ...Object.fromEntries(['largo', 'ancho', 'alto', 'tara'].map((c) => [c, n[c] === '' || n[c] == null ? null : Number(n[c])])),
  }))
}
watch([() => JSON.stringify(cuerpoNiveles()), articulo], () => {
  clearTimeout(espera)
  espera = setTimeout(async () => {
    try {
      calc.value = await api.post('/recetas-empaque/calcular', { niveles: cuerpoNiveles(), articulo_id: Number(articulo.value) || null })
    } catch { /* los errores se muestran al guardar */ }
  }, 300)
}, { immediate: true })
const total = (i) => calc.value.niveles?.[i] || {}
const unidadesArriba = computed(() => total(form.niveles.length - 1).unidades)

const ocupado = ref(false)
async function guardar() {
  ocupado.value = true
  errores.value = []
  const cuerpo = { codigo: form.codigo, nombre: form.nombre, descripcion: form.descripcion || null, niveles: cuerpoNiveles() }
  try {
    const r = form.id
      ? await api.patch(`/recetas-empaque/${form.id}`, { ...cuerpo, version: form.version })
      : await api.post('/recetas-empaque', cuerpo)
    avisar(t('Recipe “{0}” saved.', [r.nombre]))
    emit('guardada', r)
  } catch (e) {
    errores.value = (e.detalle || []).map((d) => d.mensaje)
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function eliminar() {
  const usos = props.receta?.usos || {}
  const enUso = usos.reglas || usos.posiciones
  const ok = await confirmar(enUso
    ? t('The recipe is in use ({0} rules, {1} PO lines): it will be deactivated, not deleted. Lines that use it keep it.', [usos.reglas || 0, usos.posiciones || 0])
    : t('Delete the recipe “{0}”?', [form.nombre]), { titulo: t('Delete recipe'), boton: enUso ? t('Deactivate') : t('Delete'), peligro: true })
  if (!ok) return
  try {
    await api.del(`/recetas-empaque/${form.id}`)
    emit('eliminada')
  } catch (e) {
    errorApi(e)
  }
}
async function reactivar() {
  try {
    emit('guardada', await api.patch(`/recetas-empaque/${form.id}`, { activa: true, version: form.version }))
  } catch (e) {
    errorApi(e)
  }
}
const textoCantidad = (i) => (i === 0
  ? t('units of the item')
  : t('× {0}', [tx(tipo(form.niveles[i - 1]?.tipo_empaque_id)?.nombre || t('level below'))]))
</script>

<template>
  <form class="constructor" @submit.prevent="guardar">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Code') }}</span><input v-model="form.codigo" maxlength="30" required :disabled="!editable" /></label>
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="form.nombre" maxlength="100" required :disabled="!editable" /></label>
      <label class="campo ancho"><span>{{ t('Description') }}</span><input v-model="form.descripcion" maxlength="300" :disabled="!editable" /></label>
    </div>

    <h3 class="titulo-niveles">{{ t('Levels, from the outside in') }}</h3>
    <button v-if="editable" type="button" class="btn btn-chico agregar" :disabled="!puedeArriba" :title="puedeArriba ? '' : t('No packaging type can contain the outermost level (set “Can contain” in Packaging types).')" @click="agregarArriba"><Icono nombre="arriba" :tam="14" />{{ t('Add level above') }}</button>
    <ol class="niveles">
      <li v-for="(i, k) in arriba" :key="i" class="nivel" :style="{ '--sangria': `${k * 22}px` }">
        <div class="nivel-fila">
          <Icono nombre="caja" :tam="18" class="icono-nivel" />
          <Seleccion v-model="form.niveles[i].tipo_empaque_id" class="tipo" :aria-label="t('Packaging type of level {0}', [i + 1])" :disabled="!editable">
            <option value="">{{ t('Choose…') }}</option>
            <option v-for="x in tiposPara(i)" :key="x.id" :value="x.id">{{ tx(x.nombre) }}</option>
          </Seleccion>
          <input v-model.number="form.niveles[i].cantidad" class="cantidad" type="number" min="1" step="1" :disabled="!editable"
                 :aria-label="t('How many per {0}', [tx(tipo(form.niveles[i].tipo_empaque_id)?.nombre || '')])" />
          <span class="ayuda">{{ textoCantidad(i) }}</span>
          <span class="total" :title="t('Per unit of this level')">
            → <b>{{ fmtNum(total(i).unidades) }}</b> {{ t('units') }}<template v-if="total(i).volumen"> · {{ fmtNum(total(i).volumen, 3) }} m³</template>
            <template v-if="total(i).bruto != null"> · {{ fmtNum(total(i).bruto, 2) }} kg</template>
          </span>
          <label class="check"><input v-model="form.niveles[i].opcional" type="checkbox" :disabled="!editable" /> {{ t('Optional') }}</label>
          <button type="button" class="btn-icono" :aria-expanded="form.niveles[i].medidas" :aria-label="t('Dimensions and tare of level {0}', [i + 1])"
                  :title="t('Dimensions and tare')" @click="form.niveles[i].medidas = !form.niveles[i].medidas"><Icono nombre="escala" :tam="15" /></button>
          <button v-if="editable && form.niveles.length > 1" type="button" class="btn-icono" :aria-label="t('Remove level {0}', [i + 1])"
                  @click="quitar(i)"><Icono nombre="basura" :tam="15" /></button>
        </div>
        <div v-if="form.niveles[i].medidas" class="medidas">
          <label v-for="c in ['largo', 'ancho', 'alto']" :key="c" class="campo"><span>{{ { largo: t('Length cm'), ancho: t('Width cm'), alto: t('Height cm') }[c] }}</span>
            <input v-model="form.niveles[i][c]" type="number" min="0" step="any" :placeholder="tipo(form.niveles[i].tipo_empaque_id)?.[c] ?? ''" :disabled="!editable" /></label>
          <label class="campo"><span>{{ t('Tare kg') }}</span>
            <input v-model="form.niveles[i].tara" type="number" min="0" step="any" :placeholder="tipo(form.niveles[i].tipo_empaque_id)?.tara ?? ''" :disabled="!editable" /></label>
          <small class="ayuda">{{ t('Empty: those of the packaging type.') }}</small>
        </div>
      </li>
    </ol>
    <button v-if="editable" type="button" class="btn btn-chico agregar" :disabled="!puedeAbajo" :title="puedeAbajo ? '' : t('The innermost level cannot contain another packaging that holds products.')" @click="agregarAbajo"><Icono nombre="abajo" :tam="14" />{{ t('Add level below') }}</button>

    <div class="prueba">
      <label class="campo"><span>{{ t('Weights with an item') }}</span>
        <SelectBusqueda v-model="articulo" :buscar="buscarArticulos" :etiqueta="t('Item')" :prefijo="false" :vacio="t('None')" /></label>
      <p v-if="unidadesArriba" class="ayuda">{{ t('One {0} holds {1} units of the item.', [tx(tipo(form.niveles.at(-1)?.tipo_empaque_id)?.nombre || ''), fmtNum(unidadesArriba)]) }}
        <template v-if="articulo && calc.peso_articulo == null"> {{ t('The item has no unit weight: weights cannot be calculated.') }}</template></p>
    </div>
    <ul v-if="calc.avisos?.length" class="avisos" role="status">
      <li v-for="a in calc.avisos" :key="a"><Icono nombre="alerta" :tam="14" />{{ tx(a) }}</li>
    </ul>
    <ul v-if="errores.length" class="nota error lista-errores" role="alert"><li v-for="e in errores" :key="e">{{ tx(e) }}</li></ul>
    <p v-if="receta?.usos" class="ayuda">{{ t('Used in {0} rules and {1} open PO lines. Lines that already use it keep their copy: a change applies to what comes next.', [receta.usos.reglas, receta.usos.posiciones_abiertas]) }}</p>

    <div v-if="editable" class="acciones">
      <button v-if="form.id && receta?.activa" type="button" class="btn btn-peligro" @click="eliminar"><Icono nombre="basura" :tam="15" />{{ t('Delete') }}</button>
      <button v-if="form.id && receta && !receta.activa" type="button" class="btn" @click="reactivar">{{ t('Activate') }}</button>
      <button type="submit" class="btn btn-primario separar" :disabled="ocupado">{{ form.id ? t('Save changes') : t('Create recipe') }}</button>
    </div>
  </form>
</template>

<style scoped>
.constructor { display: flex; flex-direction: column; gap: 10px; }
.campo.ancho { grid-column: 1 / -1; }
.titulo-niveles { margin: 8px 0 0; font-size: var(--t-md); }
.agregar { align-self: flex-start; }
.niveles { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.nivel { margin-inline-start: var(--sangria); border-inline-start: 2px solid var(--linea); padding-inline-start: 8px; }
.nivel-fila { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.icono-nivel { color: var(--acento); }
.tipo { min-width: 150px; }
.cantidad { width: 80px; }
.total { color: var(--tinta-3); font-size: var(--t-sm); }
.medidas { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin: 6px 0 2px; align-items: end; }
.prueba { display: grid; grid-template-columns: minmax(0, 320px) 1fr; gap: 10px; align-items: end; }
.avisos { list-style: none; padding: 0; margin: 0; color: var(--aviso); display: flex; flex-direction: column; gap: 2px; }
.avisos li { display: flex; gap: 6px; align-items: center; }
.lista-errores { margin: 0; padding-inline-start: 22px; }
.acciones { display: flex; gap: 8px; align-items: center; }
@media (max-width: 700px) {
  .nivel { margin-inline-start: calc(var(--sangria) / 2); }
  .prueba { grid-template-columns: 1fr; }
}
</style>
