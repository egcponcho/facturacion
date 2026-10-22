<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import { fmtNum } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import EditorCondiciones from '@/modulos/etiquetado/componentes/EditorCondiciones.vue'
import { OPERADORES, catalogos, condicionesLimpias, textoSalida } from '@/modulos/etiquetado/etiquetas.js'

// Las categorías de una familia (calzado → sandalias, botas…), como en la
// clasificación pero sin base oficial: la empresa las crea y las reconoce con
// condiciones sobre los datos del artículo y del producto, o las pone a mano en
// el producto. Cada categoría tiene sus etiquetas (reglas más específicas que
// las de la familia). «Probar» dice qué artículos caerían en ella antes de guardar.
const props = defineProps({
  familia: { type: Object, required: true },
  matriz: { type: Object, default: null }, // GET /etiquetas/matriz?sujeto=ARTICULO (filas CATEGORIA)
})
const emit = defineEmits(['celda', 'cambio', 'cargadas'])
const editable = computed(() => puede('etiquetas.familias'))
const categorias = ref([])
const cargando = ref(false)
const campos = ref([])
const operadores = ref([])

async function cargar() {
  cargando.value = true
  try {
    categorias.value = await api.get('/etiquetas/categorias', { familia_id: props.familia.id })
    emit('cargadas', categorias.value)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(() => {
  cargar()
  catalogos().then((c) => (operadores.value = c.operadores_simples)).catch(() => {})
  api.get('/etiquetas/campos', { sujeto: 'ARTICULO' })
    .then((r) => (campos.value = r.campos.filter((c) => /^(articulo|producto)\./.test(c.clave)))).catch(() => {}) // solo datos del artículo y del producto
})
watch(() => props.familia.id, () => {
  formulario.value = null
  cargar()
})
alCambiar(() => cargar(), ['/etiquetas/categorias'])

const filaDe = (c) => (props.matriz?.filas || []).find((f) => f.nivel === 'CATEGORIA' && f.id === c.id)
const nombreCampo = (clave) => tx(campos.value.find((f) => f.clave === clave)?.etiqueta || clave)
const textoCondiciones = (c) => (c.condiciones?.length
  ? c.condiciones.map((x) => `${nombreCampo(x.campo)} ${OPERADORES()[x.op] || x.op} ${Array.isArray(x.valor) ? x.valor.join(', ') : x.valor ?? ''}`.trim()).join(' · ')
  : t('Only set by hand on the product'))

// ---- Crear o cambiar (en la página) ------------------------------------------------------------
const formulario = ref(null)
const prueba = ref(null)
const probando = ref(false)
function nueva() {
  formulario.value = { codigo: '', nombre: '', descripcion: '', condiciones: [{ campo: '', op: 'igual', valor: '' }], activa: true }
  prueba.value = null
}
function editar(c) {
  formulario.value = { ...c, descripcion: c.descripcion || '', condiciones: (c.condiciones || []).map((x) => ({ ...x,
    valor: Array.isArray(x.valor) ? x.valor.join(', ') : x.valor })) }
  prueba.value = null
}
async function probar() {
  probando.value = true
  try {
    prueba.value = await api.post('/etiquetas/categorias/probar', { familia_id: props.familia.id, categoria_id: formulario.value.id || null,
      condiciones: condicionesLimpias(formulario.value.condiciones) })
  } catch (e) {
    errorApi(e)
  } finally {
    probando.value = false
  }
}
// La prueba deja de valer si cambian las condiciones
watch(() => formulario.value && JSON.stringify(formulario.value.condiciones), () => (prueba.value = null))
async function guardar() {
  const f = formulario.value
  const cuerpo = { familia_id: props.familia.id, codigo: f.codigo, nombre: f.nombre, descripcion: f.descripcion || null,
    condiciones: condicionesLimpias(f.condiciones), activa: f.activa }
  try {
    if (f.id) await api.patch(`/etiquetas/categorias/${f.id}`, cuerpo)
    else await api.post('/etiquetas/categorias', cuerpo)
    avisar(f.id ? t('Category saved.') : t('Category “{0}” created: now give it its labels.', [f.nombre]))
    formulario.value = null
    await cargar()
    emit('cambio')
  } catch (e) {
    errorApi(e)
  }
}
async function eliminar(c) {
  if (!(await confirmar(t('The category {0} is deleted. Its items go back to the rules of the family.', [tx(c.nombre)]),
    { titulo: t('Delete category'), boton: t('Delete'), peligro: true }))) return
  try {
    await api.del(`/etiquetas/categorias/${c.id}`)
    avisar(t('Category deleted.'))
    formulario.value = null
    await cargar()
    emit('cambio')
  } catch (e) {
    if (e.status === 409 && await confirmar(t('It has rules or products: deactivate it instead? Its items go back to the rules of the family.'),
      { titulo: t('Deactivate category'), boton: t('Deactivate') })) {
      await api.patch(`/etiquetas/categorias/${c.id}`, { activa: false }).catch(errorApi)
      formulario.value = null
      await cargar()
      emit('cambio')
    } else if (e.status !== 409) errorApi(e)
  }
}
const listo = computed(() => formulario.value && formulario.value.codigo.trim() && formulario.value.nombre.trim())
</script>

<template>
  <section class="cats" :aria-label="t('Categories')">
    <div class="cats-cabeza">
      <p class="cats-titulo">{{ t('Categories') }}</p>
      <button v-if="editable && !formulario" type="button" class="btn btn-chico" @click="nueva"><Icono nombre="mas" :tam="14" />{{ t('New category') }}</button>
    </div>

    <!-- Alta o cambio, arriba de la lista -->
    <form v-if="formulario" class="cats-form" @submit.prevent="guardar">
      <div class="cats-form-fila">
        <label><span class="req">{{ t('Code') }}</span><input v-model="formulario.codigo" maxlength="20" required class="codigo" :placeholder="t('E.g. SANDALS')" /></label>
        <label class="crece"><span class="req">{{ t('Name') }}</span><input v-model="formulario.nombre" maxlength="100" required /></label>
        <label v-if="formulario.id" class="check"><input v-model="formulario.activa" type="checkbox" /> {{ t('Active') }}</label>
      </div>
      <label><span>{{ t('Description') }}</span><input v-model="formulario.descripcion" maxlength="300" /></label>
      <EditorCondiciones :model-value="formulario.condiciones" :campos="campos" :operadores="operadores"
                         :titulo="t('It is recognized when (all must be met)')" />
      <p class="ayuda">{{ t('Without conditions the category is only set by hand on the product. If an item meets several categories, the first in the list wins.') }}</p>
      <div class="cats-prueba">
        <button type="button" class="btn btn-chico" :disabled="probando || !condicionesLimpias(formulario.condiciones).length" @click="probar">
          <Icono nombre="varita" :tam="14" />{{ probando ? t('Testing…') : t('Test with the items of the family') }}</button>
        <template v-if="prueba">
          <span :class="prueba.entran ? 'ok-txt' : 'aviso-txt'">{{ t('{0} of {1} items fall in it', [fmtNum(prueba.entran), fmtNum(prueba.revisados)]) }}</span>
          <span v-if="prueba.en_otra" class="aviso-txt">· {{ t('{0} are already in another category (the first one wins)', [fmtNum(prueba.en_otra)]) }}</span>
        </template>
      </div>
      <ul v-if="prueba?.ejemplos?.length" class="cats-ejemplos">
        <li v-for="a in prueba.ejemplos" :key="a.articulo_id"><strong class="codigo">{{ a.sku }}</strong> {{ a.descripcion }}
          <span v-if="a.categoria_actual" class="etiqueta ms-0">{{ tx(a.categoria_actual) }}</span></li>
      </ul>
      <div class="cats-form-pie">
        <button v-if="formulario.id" type="button" class="btn btn-peligro separar-fin" @click="eliminar(formulario)"><Icono nombre="basura" :tam="14" />{{ t('Delete') }}</button>
        <button type="button" class="btn" @click="formulario = null">{{ t('Cancel') }}</button>
        <button type="submit" class="btn btn-primario" :disabled="!listo">{{ formulario.id ? t('Save') : t('Create category') }}</button>
      </div>
    </form>

    <p v-if="!categorias.length && !cargando && !formulario" class="ayuda">
      {{ t('No categories. Use them when part of the family needs other labels, for example sandals or boots inside footwear.') }}</p>
    <ul v-else class="cats-lista">
      <li v-for="c in categorias" :key="c.id" :class="{ apagada: !c.activa }">
        <div class="cats-dato">
          <strong>{{ tx(c.nombre) }}</strong> <span class="etiqueta ms-0">{{ c.codigo }}</span>
          <span v-if="!c.activa" class="etiqueta aviso ms-0">{{ t('Inactive') }}</span>
          <span class="ayuda">{{ t('{0} items', [fmtNum(c.articulos || 0)]) }}</span>
          <button v-if="editable" type="button" class="btn-icono separar" :aria-label="t('Edit')" :title="t('Edit')" @click="editar(c)"><Icono nombre="editar" :tam="15" /></button>
        </div>
        <p class="ayuda cats-condiciones">{{ textoCondiciones(c) }}</p>
        <div v-if="filaDe(c)" class="cats-etiquetas">
          <button v-for="tp in matriz.tipos" :key="tp.id" type="button" class="cats-etiqueta" :class="{ propia: filaDe(c).celdas[tp.id].normal }"
                  :title="t('Rule of {0} for this category', [tx(tp.nombre)])"
                  @click="emit('celda', { tipo: tp, nivel: 'CATEGORIA', destinoId: c.id, nombre: tx(c.nombre) })">
            <span class="cats-etiqueta-tipo">{{ tx(tp.nombre) }}</span>
            <span v-if="filaDe(c).celdas[tp.id].normal">{{ textoSalida(filaDe(c).celdas[tp.id].normal) }}</span>
            <span v-else-if="filaDe(c).celdas[tp.id].hereda" class="apagado">↳ {{ textoSalida(filaDe(c).celdas[tp.id].hereda) }}</span>
            <span v-else class="apagado">—</span>
            <small v-if="filaDe(c).celdas[tp.id].excepciones" class="ayuda">{{ t('{0} exceptions', [filaDe(c).celdas[tp.id].excepciones]) }}</small>
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.cats { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--linea-suave); padding-top: 10px; }
.cats-cabeza { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.cats-titulo { margin: 0; font-size: var(--t-xs); text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); font-weight: 600; }
.cats-form { display: flex; flex-direction: column; gap: 10px; border: 1px solid var(--acento); border-radius: 10px; padding: 12px; }
.cats-form label { display: flex; flex-direction: column; gap: 3px; font-size: var(--t-sm); }
.cats-form label.check { flex-direction: row; align-items: center; }
.cats-form-fila { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
.cats-form-fila .crece { flex: 1 1 220px; }
.cats-prueba { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: var(--t-sm); }
.cats-ejemplos { margin: 0; padding-inline-start: 18px; font-size: var(--t-sm); max-height: 180px; overflow: auto; }
.cats-form-pie { display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
.separar-fin { margin-inline-end: auto; }
.cats-lista { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.cats-lista > li { border: 1px solid var(--linea); border-radius: 10px; padding: 8px 10px; display: flex; flex-direction: column; gap: 6px; }
.cats-lista > li.apagada { opacity: 0.7; }
.cats-dato { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.cats-dato .separar { margin-inline-start: auto; }
.cats-condiciones { margin: 0; }
.cats-etiquetas { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 6px; }
.cats-etiqueta { display: flex; flex-direction: column; gap: 2px; text-align: start; border: 1px dashed var(--linea); border-radius: 8px; padding: 6px 8px;
  background: none; font: inherit; font-size: var(--t-sm); color: var(--tinta); cursor: pointer; }
.cats-etiqueta.propia { border-style: solid; font-weight: 600; }
.cats-etiqueta:hover { border-color: var(--acento); background: var(--acento-claro); }
.cats-etiqueta-tipo { font-size: var(--t-xs); color: var(--tinta-3); font-weight: 400; }
.ok-txt { color: var(--ok); }
.aviso-txt { color: var(--aviso); }
</style>
