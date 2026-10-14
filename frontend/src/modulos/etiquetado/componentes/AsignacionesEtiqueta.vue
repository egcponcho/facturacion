<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { AMBITOS, MODALIDADES, textoModalidad } from '@/modulos/etiquetado/etiquetas.js'
import { buscarArticulos, buscarOrdenes, buscarProductos } from '@/modulos/etiquetado/componentes/buscadores.js'

// Dónde se aplica cada diseño y en qué orden se elige: excepción de la OC →
// artículo → producto → familia → general. «Predeterminada» desempata entre
// varias del mismo nivel; sin ella, quien genera elige.
const lista = ref([])
const plantillas = ref([])
const familias = ref([])
const cargando = ref(false)
const soloActivas = ref(true)
const editable = computed(() => puede('etiquetas.asignar'))

async function cargar() {
  cargando.value = true
  try {
    lista.value = await api.get('/etiquetas/asignaciones', { activas: soloActivas.value ? true : undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(() => {
  cargar()
  api.get('/etiquetas/plantillas', { size: 200 }).then((r) => (plantillas.value = r.items)).catch(() => {})
  api.get('/etiquetas/familias').then((r) => (familias.value = r)).catch(() => {})
})
watch(soloActivas, cargar)

const NIVEL = { OC: 1, ARTICULO: 2, PRODUCTO: 3, FAMILIA: 4, GENERAL: 5 }
const columnas = computed(() => [
  { clave: 'ambito', texto: t('Applies to'), prioridad: 1, opciones: Object.entries(AMBITOS()), textoValor: (v) => tx(AMBITOS()[v]) },
  { clave: 'destino', texto: t('Which one'), prioridad: 1 },
  { clave: 'plantilla', texto: t('Design'), fija: true, prioridad: 1 },
  { clave: 'modalidad', texto: t('Data'), prioridad: 2, textoValor: (v) => tx(textoModalidad(v)) },
  { clave: 'version_vigente', texto: t('Version in use'), prioridad: 2 },
  { clave: 'predeterminada', texto: t('Default'), prioridad: 2, opciones: [[true, t('Yes')], [false, t('No')]] },
  { clave: 'motivo', texto: t('Reason'), prioridad: 3 },
])
const ordenadas = computed(() => [...lista.value].sort((a, b) => NIVEL[a.ambito] - NIVEL[b.ambito] || a.plantilla.localeCompare(b.plantilla)))

// Nueva asignación
const nueva = ref(null)
const plantillaNueva = computed(() => plantillas.value.find((p) => p.id === Number(nueva.value?.plantilla_id)))
const ambitosValidos = computed(() => {
  const m = plantillaNueva.value?.modalidad
  if (!m) return []
  return Object.keys(AMBITOS()).filter((a) => a === 'GENERAL' || (a === 'OC' ? m !== 'ARTICULO' : m !== 'OC'))
})
function abrirNueva() {
  nueva.value = { plantilla_id: '', ambito: 'GENERAL', familia_id: '', producto_id: '', articulo_id: '', oc_id: '', predeterminada: false, motivo: '' }
}
async function crear() {
  const n = nueva.value
  const cuerpo = { plantilla_id: Number(n.plantilla_id), ambito: n.ambito, predeterminada: n.predeterminada, motivo: n.motivo || undefined }
  const col = { FAMILIA: 'familia_id', PRODUCTO: 'producto_id', ARTICULO: 'articulo_id', OC: 'oc_id' }[n.ambito]
  if (col) cuerpo[col] = Number(n[col])
  try {
    await api.post('/etiquetas/asignaciones', cuerpo)
    avisar(t('Design assigned.'))
    nueva.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
async function cambiar(a, datos) {
  try {
    await api.patch(`/etiquetas/asignaciones/${a.id}`, datos)
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
async function quitar(a) {
  try {
    await api.del(`/etiquetas/asignaciones/${a.id}`)
    avisar(t('Assignment removed; the design and generated labels did not change.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

// ¿Qué diseño se usaría?
const prueba = reactive({ modalidad: 'OC_ARTICULO', articulo_id: '', oc_id: '' })
const resultado = ref(null)
async function resolver() {
  try {
    resultado.value = await api.get('/etiquetas/resolver', { modalidad: prueba.modalidad, articulo_id: prueba.articulo_id || undefined,
      oc_id: prueba.oc_id || undefined })
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <div class="dos-columnas-asig">
    <div>
      <TablaDatos tabla="etiquetas_asignaciones" :columnas="columnas" :filas="ordenadas" :cargando="cargando" :etiqueta="t('Assignments')"
                  :clase-fila="(x) => ({ apagada: !x.activa })">
        <template #filtros>
          <label class="check"><input v-model="soloActivas" type="checkbox" /> {{ t('Only active') }}</label>
          <button v-if="editable" type="button" class="btn btn-primario separar" @click="abrirNueva"><Icono nombre="mas" />{{ t('Assign a design') }}</button>
        </template>
        <template #celda-plantilla="{ fila: a }"><router-link :to="`/etiquetas/plantillas/${a.plantilla_id}`" class="enlace">{{ tx(a.plantilla) }}</router-link></template>
        <template #celda-destino="{ fila: a }">{{ a.ambito === 'GENERAL' ? t('Whole organization') : tx(a.destino || '—') }}</template>
        <template #celda-version_vigente="{ fila: a }">
          <span v-if="a.version_vigente" class="etiqueta ok ms-0">v{{ a.version_vigente }}</span>
          <span v-else class="etiqueta aviso ms-0">{{ t('Not approved: it is skipped') }}</span>
        </template>
        <template #celda-predeterminada="{ fila: a }">
          <label v-if="editable" class="check"><input type="checkbox" :checked="a.predeterminada" @change="cambiar(a, { predeterminada: $event.target.checked })" /></label>
          <span v-else>{{ a.predeterminada ? t('Yes') : '—' }}</span>
        </template>
        <template #acciones="{ fila: a }">
          <template v-if="editable">
            <button type="button" class="btn btn-chico" @click="cambiar(a, { activa: !a.activa })">{{ a.activa ? t('Deactivate') : t('Activate') }}</button>
            <button type="button" class="btn-icono" :aria-label="t('Remove')" :title="t('Remove')" @click="quitar(a)"><Icono nombre="basura" :tam="15" /></button>
          </template>
        </template>
        <template #vacio>{{ t('No design is assigned yet. Assign one to the whole organization, a family, a product, an item or a PO.') }}</template>
      </TablaDatos>
    </div>

    <aside class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Which design would be used?') }}</h2>
        <p>{{ t('Priority: PO exception → item → product → family → general.') }}</p></div></div>
      <div class="formulario-asig">
        <label class="campo"><span>{{ t('Data') }}</span>
          <Seleccion v-model="prueba.modalidad"><option v-for="[v, txt] in MODALIDADES()" :key="v" :value="v">{{ tx(txt) }}</option></Seleccion></label>
        <label v-if="prueba.modalidad !== 'OC'" class="campo"><span>{{ t('Item') }}</span>
          <SelectBusqueda v-model="prueba.articulo_id" :buscar="buscarArticulos" :etiqueta="t('Item')" :prefijo="false" :vacio="t('None')" /></label>
        <label v-if="prueba.modalidad !== 'ARTICULO'" class="campo"><span>{{ t('Purchase order') }}</span>
          <SelectBusqueda v-model="prueba.oc_id" :buscar="buscarOrdenes" :etiqueta="t('Purchase order')" :prefijo="false" :vacio="t('None')" /></label>
        <button type="button" class="btn" @click="resolver">{{ t('Check') }}</button>
      </div>
      <div v-if="resultado" class="resultado-asig mt">
        <template v-if="resultado.plantilla">
          <strong>{{ tx(resultado.plantilla) }}</strong> <span class="etiqueta ok">v{{ resultado.version }}</span>
          <p class="ayuda">{{ tx(resultado.motivo) }}</p>
        </template>
        <p v-else-if="resultado.ambigua" class="nota">{{ tx(resultado.motivo) }} {{ resultado.candidatas.map((c) => c.plantilla).join(', ') }}</p>
        <p v-else class="nota">{{ t('No approved design applies.') }}</p>
        <p v-for="a in resultado.avisos" :key="a" class="ayuda aviso-txt">{{ tx(a) }}</p>
        <p v-if="resultado.sin_aprobar.length" class="ayuda">{{ t('Assigned but not approved: {0}', [resultado.sin_aprobar.map((c) => c.plantilla).join(', ')]) }}</p>
      </div>
    </aside>
  </div>

  <PanelLateral v-if="nueva" :titulo="t('Assign a design')" ancho="520px" @cerrar="nueva = null">
    <form id="form-asig" class="formulario-asig" @submit.prevent="crear">
      <label class="campo"><span class="req">{{ t('Design') }}</span>
        <Seleccion v-model="nueva.plantilla_id" required>
          <option value="">{{ t('Choose…') }}</option>
          <option v-for="p in plantillas" :key="p.id" :value="p.id">{{ tx(p.nombre) }} · {{ tx(textoModalidad(p.modalidad)) }}{{ p.vigente ? '' : ` (${t('not approved')})` }}</option>
        </Seleccion></label>
      <label class="campo"><span class="req">{{ t('Applies to') }}</span>
        <Seleccion v-model="nueva.ambito" :disabled="!plantillaNueva"><option v-for="a in ambitosValidos" :key="a" :value="a">{{ tx(AMBITOS()[a]) }}</option></Seleccion></label>
      <label v-if="nueva.ambito === 'FAMILIA'" class="campo"><span class="req">{{ t('Labeling family') }}</span>
        <Seleccion v-model="nueva.familia_id" required><option value="">{{ t('Choose…') }}</option>
          <option v-for="f in familias.filter((x) => x.activa)" :key="f.id" :value="f.id">{{ tx(f.nombre) }}</option></Seleccion></label>
      <label v-if="nueva.ambito === 'PRODUCTO'" class="campo"><span class="req">{{ t('Product') }}</span>
        <SelectBusqueda v-model="nueva.producto_id" :buscar="buscarProductos" :etiqueta="t('Product')" :prefijo="false" requerido /></label>
      <label v-if="nueva.ambito === 'ARTICULO'" class="campo"><span class="req">{{ t('Item') }}</span>
        <SelectBusqueda v-model="nueva.articulo_id" :buscar="buscarArticulos" :etiqueta="t('Item')" :prefijo="false" requerido /></label>
      <label v-if="nueva.ambito === 'OC'" class="campo"><span class="req">{{ t('Purchase order') }}</span>
        <SelectBusqueda v-model="nueva.oc_id" :buscar="buscarOrdenes" :etiqueta="t('Purchase order')" :prefijo="false" requerido /></label>
      <label class="campo"><span :class="{ req: nueva.ambito === 'OC' }">{{ t('Reason') }}</span>
        <input v-model="nueva.motivo" maxlength="300" :required="nueva.ambito === 'OC'" :placeholder="nueva.ambito === 'OC' ? t('Why this PO is an exception') : ''" /></label>
      <label class="check"><input v-model="nueva.predeterminada" type="checkbox" /> {{ t('Default when several designs apply at the same level') }}</label>
      <p class="ayuda">{{ t('Only an approved version is used; while the design has none, this assignment is skipped.') }}</p>
    </form>
    <template #pie>
      <button class="btn separar" type="button" @click="nueva = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-asig">{{ t('Assign') }}</button>
    </template>
  </PanelLateral>
</template>

<style scoped>
.dos-columnas-asig { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 16px; align-items: start; }
@media (max-width: 1100px) { .dos-columnas-asig { grid-template-columns: 1fr; } }
.formulario-asig { display: flex; flex-direction: column; gap: 12px; }
.resultado-asig { border-top: 1px solid var(--linea); padding-top: 12px; display: flex; flex-direction: column; gap: 6px; }
.aviso-txt { color: var(--aviso); }
:deep(tr.apagada > td) { opacity: 0.6; }
</style>
