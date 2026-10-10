<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import { fmtFecha, fmtFechaHora, fmtNum } from '@/nucleo/utils'
import { esInterno } from '@/stores/sesion'
import { confirmar } from '@/stores/confirmar'
import { avisar, errorApi } from '@/stores/ui'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'

// Reportes: los operativos (una fila por registro, para el trabajo del día) y
// los analíticos (totales por grupo) se listan aparte. El editor arma la
// definición con las fuentes y los campos que ofrece el servidor; la vista
// previa y los archivos se calculan siempre en el servidor, con el alcance de
// datos de quien los pide.
const route = useRoute()
const router = useRouter()
const tab = ref(['operativos', 'analiticos', 'editor'].includes(route.query.tab) ? route.query.tab : 'operativos')
const lista = ref({ operativos: [], analiticos: [], sistema: [] })
const fuentes = ref([])
const editando = ref(null) // reporte guardado que se edita (id, nombre…)
const modo = ref('operativo')
const def = reactive({ fuente: '', columnas: [], agrupar: [], medidas: [{ campo: '*', funcion: 'contar' }], filtros: [], orden: null })
const resultado = ref(null)
const errores = ref([])
const cargando = ref(false)
const guardar = ref(null) // { nombre, descripcion, compartido }
let editandoCarga = false // al abrir uno guardado, sus datos no cuentan como cambios

const OPS = {
  contiene: t('contains'), igual: t('is'), distinto: t('is not'), empieza: t('starts with'), vacio: t('is empty'), no_vacio: t('is not empty'),
  en: t('is one of'), mayor: t('greater than'), menor: t('less than'), entre: t('between'), desde: t('from'), hasta: t('until'),
  ultimos_dias: t('in the last days'),
}
const OPS_TIPO = {
  texto: ['contiene', 'igual', 'distinto', 'empieza', 'vacio', 'no_vacio'],
  estado: ['igual', 'distinto', 'en', 'vacio', 'no_vacio'],
  numero: ['igual', 'distinto', 'mayor', 'menor', 'entre', 'vacio', 'no_vacio'],
  moneda: ['igual', 'distinto', 'mayor', 'menor', 'entre', 'vacio', 'no_vacio'],
  fecha: ['ultimos_dias', 'desde', 'hasta', 'entre', 'igual', 'vacio', 'no_vacio'],
}
const FUNCIONES = [['contar', t('Count')], ['suma', t('Sum')], ['promedio', t('Average')], ['minimo', t('Minimum')], ['maximo', t('Maximum')]]

async function cargarLista() {
  try {
    lista.value = await api.get('/reportes')
  } catch (e) {
    errorApi(e)
  }
}
onMounted(async () => {
  try {
    fuentes.value = await api.get('/reportes/fuentes')
  } catch (e) {
    errorApi(e)
  }
  await cargarLista()
  if (route.query.id) abrir(Number(route.query.id))
})
watch(tab, (v) => router.replace({ query: { ...route.query, tab: v } }))

// ---- Editor -------------------------------------------------------------------------
const fuente = computed(() => fuentes.value.find((f) => f.clave === def.fuente))
const campos = computed(() => fuente.value?.campos || [])
const campo = (clave) => campos.value.find((c) => c.clave === clave)
const opcionesCampos = (filtro = () => true) => campos.value.filter(filtro).map((c) => ({ valor: c.clave, texto: c.titulo }))
const agrupables = computed(() => opcionesCampos((c) => !['numero', 'moneda'].includes(c.tipo)))
const medibles = (funcion) => opcionesCampos((c) => ['numero', 'moneda'].includes(c.tipo) || (['minimo', 'maximo'].includes(funcion) && c.tipo === 'fecha'))

function nuevo() {
  editando.value = null
  Object.assign(def, { fuente: fuentes.value[0]?.clave || '', columnas: [], agrupar: [], medidas: [{ campo: '*', funcion: 'contar' }], filtros: [], orden: null })
  modo.value = 'operativo'
  resultado.value = null
  errores.value = []
  if (fuente.value) def.columnas = fuente.value.campos.slice(0, 4).map((c) => c.clave)
  tab.value = 'editor'
}
watch(() => def.fuente, (_, antes) => {
  if (!antes || editandoCarga) return
  // Otra fuente: sus campos son otros
  Object.assign(def, { columnas: fuente.value ? fuente.value.campos.slice(0, 4).map((c) => c.clave) : [], agrupar: [],
    medidas: [{ campo: '*', funcion: 'contar' }], filtros: [], orden: null })
})
async function abrir(id) {
  try {
    const r = await api.get(`/reportes/${id}`)
    editandoCarga = true
    editando.value = { id: r.id, nombre: r.nombre, descripcion: r.descripcion, compartido: r.compartido, puede_editar: r.puede_editar }
    const d = r.definicion
    Object.assign(def, { fuente: d.fuente, columnas: d.columnas || [], agrupar: d.agrupar || [],
      medidas: d.medidas?.length ? d.medidas : [{ campo: '*', funcion: 'contar' }], filtros: (d.filtros || []).map((f) => ({ ...f })), orden: d.orden })
    modo.value = d.tipo
    resultado.value = r.resultado
    tab.value = 'editor'
    setTimeout(() => { editandoCarga = false }, 0)
  } catch (e) {
    errorApi(e)
  }
}
const definicion = () => ({
  fuente: def.fuente, filtros: def.filtros.filter((f) => f.campo && f.op), orden: def.orden,
  ...(modo.value === 'analitico' ? { agrupar: def.agrupar, medidas: def.medidas } : { columnas: def.columnas }),
})

// Vista previa: se recalcula sola al cambiar la definición
let reloj = null
watch([def, modo], () => {
  if (tab.value !== 'editor' || !def.fuente || editandoCarga) return
  clearTimeout(reloj)
  reloj = setTimeout(previa, 450)
}, { deep: true })
async function previa() {
  cargando.value = true
  try {
    resultado.value = await api.post('/reportes/vista', { definicion: definicion() })
    errores.value = []
  } catch (e) {
    errores.value = e.detalle?.length ? e.detalle.map((d) => d.mensaje) : [e.message]
  } finally {
    cargando.value = false
  }
}
function agregarFiltro() {
  def.filtros.push({ campo: '', op: '', valor: '' })
}
function elegirCampoFiltro(f) {
  const c = campo(f.campo)
  f.op = c ? OPS_TIPO[c.tipo][0] : ''
  f.valor = c?.tipo === 'fecha' && f.op === 'ultimos_dias' ? 30 : ''
}
function elegirOp(f) {
  f.valor = f.op === 'entre' ? ['', ''] : f.op === 'en' ? [] : f.op === 'ultimos_dias' ? 30 : ''
}
const sinValor = (f) => ['vacio', 'no_vacio'].includes(f.op)
const salidas = computed(() => (modo.value === 'analitico'
  ? [...def.agrupar.map((k) => ({ valor: k, texto: campo(k)?.titulo || k })),
    ...def.medidas.map((m) => ({ valor: `${m.funcion}_${m.campo === '*' ? 'todo' : m.campo}`,
      texto: m.campo === '*' ? t('Count') : `${tx(FUNCIONES.find((x) => x[0] === m.funcion)?.[1])}: ${tx(campo(m.campo)?.titulo || '')}` }))]
  : def.columnas.map((k) => ({ valor: k, texto: campo(k)?.titulo || k }))))
const ordenCampo = computed({
  get: () => def.orden?.campo || '',
  set: (v) => { def.orden = v ? { campo: v, dir: def.orden?.dir || 'asc' } : null },
})

function celda(col, v) {
  if (v === null || v === undefined || v === '') return '—'
  const nombres = resultado.value?.opciones?.[col.clave]
  if (nombres) return nombres[v] || v
  if (col.tipo === 'moneda') return fmtNum(v, 2)
  if (col.tipo === 'numero') return fmtNum(v)
  if (col.tipo === 'fecha') return fmtFecha(v)
  return v
}

async function exportar(formato, id = null) {
  try {
    if (id) await api.descargar(`/reportes/${id}/exportar`, `report.${formato}`, { formato })
    else await api.descargar('/reportes/exportar', `report.${formato}`, { formato }, { definicion: definicion(), titulo: editando.value?.nombre || fuente.value?.titulo })
  } catch (e) {
    errorApi(e)
  }
}
function abrirGuardar() {
  guardar.value = { nombre: editando.value?.nombre || '', descripcion: editando.value?.descripcion || '', compartido: !!editando.value?.compartido, nuevo: false }
}
async function confirmarGuardar() {
  try {
    const { nuevo, ...datos } = guardar.value
    const cuerpo = { ...datos, definicion: definicion() }
    const r = editando.value?.puede_editar && !nuevo ? await api.patch(`/reportes/${editando.value.id}`, cuerpo) : await api.post('/reportes', cuerpo)
    editando.value = { id: r.id, nombre: r.nombre, descripcion: r.descripcion, compartido: r.compartido, puede_editar: true }
    guardar.value = null
    avisar(t('Report {0} saved.', [r.nombre]))
    router.replace({ query: { ...route.query, id: r.id } })
    cargarLista()
  } catch (e) {
    errorApi(e)
  }
}
async function borrar(r) {
  if (!(await confirmar(t('Delete the report {0}?', [r.nombre]), { boton: t('Delete'), peligro: true }))) return
  try {
    await api.del(`/reportes/${r.id}`)
    avisar(t('Report deleted.'))
    if (editando.value?.id === r.id) editando.value = null
    cargarLista()
  } catch (e) {
    errorApi(e)
  }
}
const nombreFuente = (clave) => fuentes.value.find((f) => f.clave === clave)?.titulo || clave
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Reports') }}</h1>
      <p>{{ t('Operational reports list records for the daily work; analytical reports total them by group. Every report is calculated when you open it, with the data you are allowed to see.') }}</p>
    </div>
    <button type="button" class="btn btn-primario" @click="nuevo"><Icono nombre="mas" />{{ t('New report') }}</button>
  </div>

  <nav class="pestanas" role="tablist" :aria-label="t('Reports')">
    <button type="button" class="pestana" role="tab" :aria-selected="tab === 'operativos'" @click="tab = 'operativos'">
      <Icono nombre="lista" :tam="16" />{{ t('Operational') }}<span class="cuenta">{{ tx(lista.operativos.length + lista.sistema.length) }}</span></button>
    <button type="button" class="pestana" role="tab" :aria-selected="tab === 'analiticos'" @click="tab = 'analiticos'">
      <Icono nombre="grafica" :tam="16" />{{ t('Analytical') }}<span class="cuenta">{{ tx(lista.analiticos.length) }}</span></button>
    <button type="button" class="pestana" role="tab" :aria-selected="tab === 'editor'" @click="tab === 'editor' || (def.fuente ? (tab = 'editor') : nuevo())">
      <Icono nombre="editar" :tam="16" />{{ tx(editando ? editando.nombre : t('Report builder')) }}</button>
  </nav>

  <!-- Listas -->
  <template v-if="tab !== 'editor'">
    <section v-if="tab === 'operativos' && lista.sistema.length" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('System reports') }}</h2><p>{{ t('Fixed tracking reports, with the filters of the Tracking screen; they export to PDF and Excel there.') }}</p></div></div>
      <ul class="sistema">
        <li v-for="s in lista.sistema" :key="s.clave"><router-link :to="s.ruta"><b>{{ tx(s.titulo) }}</b></router-link><span class="ayuda">{{ tx(s.descripcion) }}</span></li>
      </ul>
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ tab === 'operativos' ? t('Saved operational reports') : t('Saved analytical reports') }}</h2></div></div>
      <div v-if="(tab === 'operativos' ? lista.operativos : lista.analiticos).length" class="tabla-marco sin-sombra">
        <table class="tabla" v-tarjetas>
          <thead><tr><th>{{ t('Name') }}</th><th>{{ t('Source') }}</th><th>{{ t('Shared') }}</th><th>{{ t('Updated') }}</th><th class="num"><span class="oculto-visual">{{ t('Actions') }}</span></th></tr></thead>
          <tbody>
            <tr v-for="r in (tab === 'operativos' ? lista.operativos : lista.analiticos)" :key="r.id">
              <td><button type="button" class="enlace fuerte" @click="abrir(r.id)">{{ tx(r.nombre) }}</button><span v-if="r.descripcion" class="sub">{{ tx(r.descripcion) }}</span></td>
              <td>{{ tx(nombreFuente(r.fuente)) }}</td>
              <td>{{ tx(r.compartido ? (r.propio ? t('Yes') : t('By {0}', [r.autor])) : t('No')) }}</td>
              <td>{{ fmtFechaHora(r.actualizado_en) }}</td>
              <td class="num nowrap">
                <button type="button" class="btn btn-chico" @click="exportar('csv', r.id)">CSV</button>
                <button type="button" class="btn btn-chico" @click="exportar('xlsx', r.id)">{{ t('Excel') }}</button>
                <button type="button" class="btn btn-chico" @click="exportar('pdf', r.id)">PDF</button>
                <button v-if="r.puede_editar" type="button" class="btn-icono texto-error" :aria-label="t('Delete {0}', [r.nombre])" @click="borrar(r)"><Icono nombre="basura" :tam="16" /></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <EstadoVacio v-else :icono="tab === 'operativos' ? 'lista' : 'grafica'" :titulo="t('No saved reports yet')"
                   :texto="tab === 'operativos' ? t('Build a list with the columns and filters you use every day and save it.') : t('Group by supplier, status or month and add counts and totals.')">
        <button type="button" class="btn btn-primario" @click="nuevo">{{ t('New report') }}</button>
      </EstadoVacio>
    </section>
  </template>

  <!-- Editor -->
  <template v-else>
    <section class="panel">
      <div class="editor">
        <div class="campo"><span class="req">{{ t('Data source') }}</span>
          <Seleccion v-model="def.fuente" class="entrada"><option v-for="f in fuentes" :key="f.clave" :value="f.clave">{{ tx(f.titulo) }}</option></Seleccion>
          <small v-if="fuente" class="ayuda">{{ tx(fuente.descripcion) }}</small></div>
        <div class="campo"><span>{{ t('Kind of report') }}</span>
          <div class="segmentos" role="group" :aria-label="t('Kind of report')">
            <button type="button" class="segmento" :aria-pressed="modo === 'operativo'" @click="modo = 'operativo'">{{ t('List of records') }}</button>
            <button type="button" class="segmento" :aria-pressed="modo === 'analitico'" @click="modo = 'analitico'">{{ t('Totals by group') }}</button>
          </div></div>
        <div v-if="modo === 'operativo'" class="campo col-completa"><span class="req">{{ t('Columns') }}</span>
          <SelectBusqueda v-model="def.columnas" :opciones="opcionesCampos()" multiple :etiqueta="t('Columns')" :placeholder="t('Choose the columns…')" /></div>
        <template v-else>
          <div class="campo"><span class="req">{{ t('Group by') }}</span>
            <SelectBusqueda v-model="def.agrupar" :opciones="agrupables" multiple :etiqueta="t('Group by')" :placeholder="t('Up to 3 fields…')" /></div>
          <div class="campo col-completa"><span>{{ t('Measures') }}</span>
            <div v-for="(m, i) in def.medidas" :key="i" class="fila-flex medida">
              <Seleccion v-model="m.funcion" class="entrada" :aria-label="t('Measure')" @change="m.campo = m.funcion === 'contar' ? '*' : ''">
                <option v-for="[v, txt] in FUNCIONES" :key="v" :value="v">{{ tx(txt) }}</option></Seleccion>
              <SelectBusqueda v-if="m.funcion !== 'contar'" v-model="m.campo" :opciones="medibles(m.funcion)" :etiqueta="t('Field')" :prefijo="false" class="medida-campo" />
              <button type="button" class="btn-icono" :aria-label="t('Remove')" :disabled="def.medidas.length === 1" @click="def.medidas.splice(i, 1)"><Icono nombre="cerrar" :tam="15" /></button>
            </div>
            <button type="button" class="btn btn-chico btn-fantasma" :disabled="def.medidas.length >= 6" @click="def.medidas.push({ campo: '', funcion: 'suma' })"><Icono nombre="mas" :tam="14" />{{ t('Add measure') }}</button>
          </div>
        </template>
        <div class="campo col-completa"><span>{{ t('Filters') }}</span>
          <div v-for="(f, i) in def.filtros" :key="i" class="fila-flex filtro-fila">
            <SelectBusqueda v-model="f.campo" :opciones="opcionesCampos()" :etiqueta="t('Field')" :prefijo="false" class="filtro-campo" @change="elegirCampoFiltro(f)" />
            <Seleccion v-if="campo(f.campo)" v-model="f.op" class="entrada filtro-op" :aria-label="t('Condition')" @change="elegirOp(f)">
              <option v-for="o in OPS_TIPO[campo(f.campo).tipo]" :key="o" :value="o">{{ tx(OPS[o]) }}</option></Seleccion>
            <template v-if="campo(f.campo) && !sinValor(f)">
              <template v-if="f.op === 'entre'">
                <CampoFecha v-if="campo(f.campo).tipo === 'fecha'" v-model="f.valor[0]" /><input v-else v-model="f.valor[0]" class="entrada filtro-valor" type="number" step="any" :aria-label="t('From')" />
                <span>{{ t('and') }}</span>
                <CampoFecha v-if="campo(f.campo).tipo === 'fecha'" v-model="f.valor[1]" /><input v-else v-model="f.valor[1]" class="entrada filtro-valor" type="number" step="any" :aria-label="t('To')" />
              </template>
              <input v-else-if="f.op === 'ultimos_dias'" v-model.number="f.valor" class="entrada filtro-valor" type="number" min="1" max="3650" :aria-label="t('Days')" />
              <CampoFecha v-else-if="campo(f.campo).tipo === 'fecha'" v-model="f.valor" />
              <SelectBusqueda v-else-if="f.op === 'en'" v-model="f.valor" :opciones="campo(f.campo).opciones.map(([v, txt]) => ({ valor: v, texto: txt }))" multiple :etiqueta="t('Values')" class="filtro-campo" />
              <Seleccion v-else-if="campo(f.campo).tipo === 'estado'" v-model="f.valor" class="entrada" :aria-label="t('Value')">
                <option value="">{{ t('Choose…') }}</option><option v-for="[v, txt] in campo(f.campo).opciones" :key="v" :value="v">{{ tx(txt) }}</option></Seleccion>
              <input v-else v-model="f.valor" class="entrada filtro-valor" :type="['numero', 'moneda'].includes(campo(f.campo).tipo) ? 'number' : 'text'" step="any" :aria-label="t('Value')" />
            </template>
            <button type="button" class="btn-icono" :aria-label="t('Remove filter')" @click="def.filtros.splice(i, 1)"><Icono nombre="cerrar" :tam="15" /></button>
          </div>
          <button type="button" class="btn btn-chico btn-fantasma" :disabled="def.filtros.length >= 15" @click="agregarFiltro"><Icono nombre="filtro" :tam="14" />{{ t('Add filter') }}</button>
        </div>
        <div class="campo"><span>{{ t('Sort by') }}</span>
          <div class="fila-flex">
            <SelectBusqueda v-model="ordenCampo" :opciones="salidas" :vacio="t('No order')" :etiqueta="t('Sort by')" :prefijo="false" class="filtro-campo" />
            <button v-if="def.orden" type="button" class="btn btn-chico" @click="def.orden.dir = def.orden.dir === 'asc' ? 'desc' : 'asc'">
              <Icono :nombre="def.orden.dir === 'asc' ? 'arriba' : 'abajo'" :tam="14" />{{ tx(def.orden.dir === 'asc' ? t('Ascending') : t('Descending')) }}</button>
          </div></div>
      </div>
      <div class="fila-flex acciones-editor">
        <span class="ayuda">{{ tx(cargando ? t('Calculating…') : resultado ? t('{0} rows', [fmtNum(resultado.total)]) : '') }}<template v-if="resultado?.truncado"> · {{ t('the preview shows the first {0}', [resultado.filas.length]) }}</template></span>
        <span class="separar"></span>
        <button type="button" class="btn" :disabled="!resultado || errores.length" @click="exportar('csv')">CSV</button>
        <button type="button" class="btn" :disabled="!resultado || errores.length" @click="exportar('xlsx')">{{ t('Excel') }}</button>
        <button type="button" class="btn" :disabled="!resultado || errores.length" @click="exportar('pdf')">PDF</button>
        <button type="button" class="btn btn-primario" :disabled="!resultado || errores.length" @click="abrirGuardar"><Icono nombre="check" :tam="15" />{{ t('Save report') }}</button>
      </div>
    </section>

    <div v-if="errores.length" class="nota error bloque" role="alert"><ul class="lista-mensajes"><li v-for="(m, i) in errores" :key="i">{{ tx(m) }}</li></ul></div>
    <div v-else-if="resultado" class="tabla-marco tabla-fija resultado">
      <table class="tabla" v-tarjetas :aria-busy="cargando">
        <thead><tr><th v-for="c in resultado.columnas" :key="c.clave" :class="{ num: ['numero', 'moneda'].includes(c.tipo) }">{{ tx(c.titulo) }}<template v-if="c.titulo_campo">: {{ tx(c.titulo_campo) }}</template></th></tr></thead>
        <tbody>
          <tr v-for="(fila, i) in resultado.filas" :key="i">
            <td v-for="(c, j) in resultado.columnas" :key="c.clave" :class="{ num: ['numero', 'moneda'].includes(c.tipo) }">{{ tx(celda(c, fila[j])) }}</td>
          </tr>
          <tr v-if="!resultado.filas.length"><td :colspan="resultado.columnas.length" class="vacio">{{ t('No records match these filters.') }}</td></tr>
        </tbody>
      </table>
    </div>
  </template>

  <Modal v-if="guardar" :titulo="tx(editando?.puede_editar ? t('Save changes') : t('Save report'))" @cerrar="guardar = null">
    <form id="form-reporte" class="rejilla-campos" @submit.prevent="confirmarGuardar">
      <label class="campo col-completa"><span class="req">{{ t('Name') }}</span><input v-model="guardar.nombre" class="entrada" maxlength="120" required /></label>
      <label class="campo col-completa"><span>{{ t('Description') }}</span><input v-model="guardar.descripcion" class="entrada" maxlength="300" /></label>
      <label v-if="esInterno()" class="check col-completa"><input v-model="guardar.compartido" type="checkbox" />{{ t('Share with my organization (everyone who can see this data)') }}</label>
      <label v-if="editando?.puede_editar" class="check col-completa"><input v-model="guardar.nuevo" type="checkbox" />{{ t('Save as a new report (keep {0} as it is)', [editando.nombre]) }}</label>
    </form>
    <template #pie>
      <button type="button" class="btn" @click="guardar = null">{{ t('Cancel') }}</button>
      <button type="submit" form="form-reporte" class="btn btn-primario">{{ t('Save') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.sistema { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.sistema li { display: flex; flex-direction: column; gap: 2px; }
.editor { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 20px; }
.medida, .filtro-fila { margin-bottom: 6px; flex-wrap: wrap; align-items: center; }
/* En una fila: dato, condición y valor (la regla global da 100 % de ancho a las listas dentro de .campo) */
.medida .sb, .filtro-fila .sb { width: auto; flex: 1 1 200px; max-width: 360px; }
.medida .sb:first-child, .filtro-fila .sb.filtro-op { flex: 0 0 170px; }
.filtro-valor { width: 160px; flex: 0 0 auto; }
.filtro-fila .campo-fecha { width: 170px; flex: 0 0 auto; }
.acciones-editor { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--linea-suave); }
.resultado { margin-top: 16px; max-height: 60vh; overflow: auto; }
.enlace { border: 0; background: none; padding: 0; color: var(--acento-texto); cursor: pointer; font: inherit; text-align: start; }
.enlace:hover { text-decoration: underline; }
@media (max-width: 720px) { .editor { grid-template-columns: 1fr; } }
</style>
