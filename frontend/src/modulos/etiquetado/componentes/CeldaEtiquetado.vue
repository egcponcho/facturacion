<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import { fmtFecha, fmtNum } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import EfectoCambio from '@/modulos/etiquetado/componentes/EfectoCambio.vue'
import ExcepcionFrase from '@/modulos/etiquetado/componentes/ExcepcionFrase.vue'
import SalidaRegla from '@/modulos/etiquetado/componentes/SalidaRegla.vue'
import SelectorDiseno from '@/modulos/etiquetado/componentes/SelectorDiseno.vue'
import { catalogos, condicionesLimpias, textoDonde, textoExcepcion, textoSalida, textoVigencia } from '@/modulos/etiquetado/etiquetas.js'

// Una celda de la matriz (fila × tipo de etiqueta), en la misma página (sin ventana): su diseño
// normal (o heredar), sus excepciones escritas como frase y los productos con
// diseño propio. Antes de guardar se ve qué cambia; se guarda todo junto con la
// firma que se leyó, así no se pisa el cambio de otra persona.
const props = defineProps({
  tipo: { type: Object, required: true },
  nivel: { type: String, required: true },
  destinoId: { type: Number, default: null },
  nombre: { type: String, default: '' }, // nombre de la fila
  otras: { type: Array, default: () => [] }, // otras filas de la columna, para «aplicar también a»
})
const emit = defineEmits(['cerrar', 'guardado'])
const editable = computed(() => puede('etiquetas.configurar'))
const celda = ref(null)
// La regla normal del lugar: un diseño (dónde va, cuántas) o «no lleva»; sin diseño = heredar
const salida = (u) => ({ accion: u?.accion || 'USAR', plantilla_id: u?.plantilla_id || '', alcance: u?.alcance || '', cantidad: u?.cantidad || '',
  prioridad: u?.prioridad || 0 })
const normal = ref(salida(null))
const excepciones = ref([]) // copias editables (con `cambiada`) de las que hay + las nuevas
const quitar = ref([])
const editando = ref(null) // índice en excepciones, o 'nueva'
const nueva = ref(null)
const campos = ref([])
const operadores = ref([])
const ocupado = ref(false)

async function cargar() {
  try {
    const c = await api.get('/etiquetas/celda', { tipo: props.tipo.id, nivel: props.nivel, destino_id: props.destinoId ?? undefined })
    celda.value = c
    normal.value = salida(c.normal)
    excepciones.value = c.excepciones.map((u) => ({ ...u, ...salida(u), condiciones: (u.condiciones || []).map((x) => ({ ...x })), aplicar: [], cambiada: false }))
    quitar.value = []
    editando.value = null
    nueva.value = null
  } catch (e) {
    errorApi(e)
    emit('cerrar')
  }
}
onMounted(() => {
  cargar()
  catalogos().then((c) => (operadores.value = c.operadores_simples)).catch(() => {})
  api.get('/etiquetas/campos', { sujeto: props.tipo.sujeto })
    .then((r) => (campos.value = r.campos.filter((c) => !['etiqueta', 'manual'].includes(c.grupo)))).catch(() => {})
})

const titulo = computed(() => `${props.nombre || textoDonde(props.nivel, celda.value?.destino)} · ${tx(props.tipo.nombre)}`)
const tipoCelda = computed(() => celda.value?.tipo || props.tipo)
const claveSalida = (n) => (n.accion === 'NO_LLEVA' ? 'NO_LLEVA' : n.plantilla_id ? [Number(n.plantilla_id), n.alcance, n.cantidad].join('|') : '')
const normalCambiado = computed(() => celda.value && claveSalida(normal.value) !== claveSalida(salida(celda.value.normal)))
function normalPedido() {
  const n = normal.value
  if (n.accion === 'NO_LLEVA') return { accion: 'NO_LLEVA' }
  return n.plantilla_id ? { accion: 'USAR', plantilla_id: Number(n.plantilla_id), alcance: n.alcance || null, cantidad: n.cantidad || null } : null
}
const visibles = computed(() => excepciones.value.filter((x) => !quitar.value.includes(x.id)))
const cambios = computed(() => normalCambiado.value || quitar.value.length > 0 || excepciones.value.some((x) => x.cambiada || !x.id))

// Lo que se manda (al simular y al guardar): solo lo que cambió
const limpia = (x) => ({ ...(x.id && { id: x.id, version: x.version }), contexto_tipo: x.contexto_tipo, contexto_valores: x.contexto_valores,
  oc_id: x.oc_id || undefined, accion: x.accion || 'USAR', plantilla_id: x.accion === 'NO_LLEVA' ? null : x.plantilla_id,
  alcance: x.alcance || null, cantidad: x.cantidad || null, prioridad: Number(x.prioridad) || 0, condiciones: condicionesLimpias(x.condiciones),
  vigente_desde: x.vigente_desde || null, vigente_hasta: x.vigente_hasta || null, motivo: x.motivo })
function pedido(extra = {}) {
  const enviadas = excepciones.value.filter((x) => (x.cambiada || !x.id) && !quitar.value.includes(x.id))
  return { tipo_etiqueta_id: props.tipo.id, nivel: props.nivel, destino_id: props.destinoId,
    ...(normalCambiado.value && { normal: normalPedido() }),
    excepciones: enviadas.map(limpia), quitar: quitar.value, ...extra }
}

// «Qué cambia al guardar»: se recalcula con cada cambio (espera de 400 ms)
const efecto = ref(null)
const simulando = ref(false)
const coinciden = ref({})
let espera = null
async function simular(datos = pedido(), propio = true) {
  try {
    const r = await api.post('/etiquetas/usos/simular', datos)
    if (propio) efecto.value = r
    return r
  } catch (e) {
    if (propio) efecto.value = null
    if (e.status !== 422) errorApi(e)
    return null
  }
}
watch([normal, excepciones, quitar], () => {
  clearTimeout(espera)
  if (!celda.value || !cambios.value) {
    efecto.value = null
    return
  }
  simulando.value = true
  espera = setTimeout(async () => {
    await simular()
    simulando.value = false
  }, 400)
}, { deep: true })
// Cuántas líneas abiertas cumplen la excepción que se está escribiendo
let esperaFrase = null
watch(nueva, (x) => {
  clearTimeout(esperaFrase)
  if (!x || (!x.plantilla_id && x.accion !== 'NO_LLEVA') || !(x.motivo || '').trim()) return
  esperaFrase = setTimeout(async () => {
    const r = await simular({ tipo_etiqueta_id: props.tipo.id, nivel: props.nivel, destino_id: props.destinoId, excepciones: [limpia(x)] }, false)
    coinciden.value = { ...coinciden.value, nueva: r?.excepciones?.[0]?.coinciden ?? null }
  }, 400)
}, { deep: true })
onBeforeUnmount(() => {
  clearTimeout(espera)
  clearTimeout(esperaFrase)
})

// Dos excepciones iguales en la misma celda no se pueden guardar
function conflicto(x) {
  if (!['PAIS_DESTINO', 'CENTRO_DESTINO', 'SOCIEDAD', 'PROVEEDOR'].includes(x.contexto_tipo)) return ''
  const otra = visibles.value.find((y) => y !== x && y.contexto_tipo === x.contexto_tipo && Number(y.prioridad || 0) === Number(x.prioridad || 0) && !y.vigente_desde && !y.vigente_hasta
    && !x.vigente_desde && !x.vigente_hasta && y.contexto_valores.some((v) => x.contexto_valores.includes(v)))
  return otra ? t('There is already an exception for {0} in this place.', [otra.contexto_valores.filter((v) => x.contexto_valores.includes(v)).join(', ')]) : ''
}

function agregar() {
  nueva.value = { contexto_tipo: 'PAIS_DESTINO', contexto_valores: [], ...salida(null), condiciones: [], vigente_desde: '', vigente_hasta: '',
    motivo: '', aplicar: [] }
  editando.value = 'nueva'
  coinciden.value = { ...coinciden.value, nueva: null }
}
function aceptarNueva() {
  excepciones.value.push({ ...nueva.value, cambiada: true })
  nueva.value = null
  editando.value = null
}
const respaldo = ref(null)
function editar(i) {
  respaldo.value = JSON.parse(JSON.stringify(excepciones.value[i]))
  editando.value = i
}
function aceptarEdicion(i) {
  excepciones.value[i].cambiada = true
  editando.value = null
}
function cancelarEdicion(i) {
  if (respaldo.value) excepciones.value[i] = respaldo.value
  editando.value = null
}
async function quitarExcepcion(x) {
  if (!x.id) {
    excepciones.value = excepciones.value.filter((y) => y !== x)
    return
  }
  const r = await simular({ ...pedido(), quitar: [...quitar.value, x.id] }, false)
  const texto = r && r.sujeto === 'ARTICULO'
    ? t('{0} items go back to the normal design of this place. The exception is removed (it stays in the history).', [fmtNum(r.cambian)])
    : t('The exception is removed (it stays in the history).')
  if (await confirmar(texto, { titulo: t('Remove the exception'), boton: t('Remove'), peligro: true })) quitar.value = [...quitar.value, x.id]
}

async function guardar() {
  ocupado.value = true
  try {
    const nuevasConOtras = excepciones.value.filter((x) => !x.id && x.aplicar.length)
    await api.put('/etiquetas/usos/celda', pedido({ firma: celda.value.firma }))
    for (const x of nuevasConOtras) {
      await api.post('/etiquetas/usos/lote', { tipo_etiqueta_id: props.tipo.id, excepcion: limpia(x),
        celdas: x.aplicar.map((k) => {
          const [nivel, d] = k.split(':')
          return { nivel, destino_id: Number(d) || null }
        }) })
    }
    avisar(t('Saved. The next labels use these designs.'))
    emit('guardado')
  } catch (e) {
    if (e.status === 409) {
      avisar(e.message ? tx(e.message) : t('Someone else changed this place while you had it open: open it again.'), 'aviso')
      await cargar()
    } else errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// Productos y artículos con diseño propio: quitarlo los devuelve a heredar
const verPropios = ref(false)
async function quitarPropio(p) {
  if (!(await confirmar(t('{0} goes back to using the design of this place.', [tx(p.destino)]), { titulo: t('Remove own design'), boton: t('Remove'), peligro: true }))) return
  try {
    await api.post(`/etiquetas/usos/${p.uso_id}/baja`, { motivo: t('Back to the design of {0}', [titulo.value]) })
    await cargar()
    emit('guardado', { cerrar: false })
  } catch (e) {
    errorApi(e)
  }
}
const autor = (x) => [x.creado_por, x.creado_en && fmtFecha(x.creado_en)].filter(Boolean).join(', ')
</script>

<template>
  <section class="panel celda-panel" :aria-label="titulo">
    <header class="celda-titulo">
      <button type="button" class="btn btn-icono" :aria-label="t('Back')" :title="t('Back')" @click="emit('cerrar')"><Icono nombre="atras" /></button>
      <h3>{{ titulo }}</h3>
      <div class="celda-acciones">
        <button type="button" class="btn" @click="emit('cerrar')">{{ editable ? t('Cancel') : t('Close') }}</button>
        <button v-if="editable" type="button" class="btn btn-primario" :disabled="ocupado || !cambios || editando !== null" @click="guardar">{{ t('Save') }}</button>
      </div>
    </header>
    <div v-if="!celda" class="vacio">{{ t('Loading…') }}</div>
    <div v-else class="celda">
      <section>
        <h4>{{ t('Normal rule') }}</h4>
        <SalidaRegla v-if="editable" :key="celda.firma" :model-value="normal" :tipo="tipoCelda">
          <SelectorDiseno v-model="normal.plantilla_id" :tipo-id="tipo.id"
                          :vacio="celda.hereda ? t('Inherit from “{0}” ({1})', [textoDonde(celda.hereda.nivel, celda.hereda.destino), textoSalida(celda.hereda) || t('No design')])
                            : nivel === 'GENERAL' ? t('No design') : t('Inherit (there is no design above: none)')" />
        </SalidaRegla>
        <p v-else>{{ celda.normal ? textoSalida(celda.normal) : celda.hereda ? t('Inherits {0}', [textoSalida(celda.hereda)]) : t('No design') }}</p>
        <p class="ayuda">{{ nivel === 'GENERAL' ? t('{0} items. Families without a design of their own use this one.', [fmtNum(celda.articulos || 0)])
          : celda.articulos != null ? t('{0} items in this place.', [fmtNum(celda.articulos)]) : '' }}</p>
      </section>

      <section>
        <div class="celda-cabeza">
          <h4>{{ t('Exceptions') }} <span class="ayuda">· {{ t('checked in this order: center, country, company, supplier, conditions') }}</span></h4>
          <button v-if="editable && editando === null" type="button" class="btn btn-chico" @click="agregar"><Icono nombre="mas" :tam="14" />{{ t('Add exception') }}</button>
        </div>
        <ol v-if="visibles.length || nueva" class="excepciones">
          <li v-for="x in visibles" :key="x.id || x.motivo">
            <ExcepcionFrase v-if="editando === excepciones.indexOf(x)" :model-value="x" :tipo="tipoCelda" :campos="campos" :operadores="operadores"
                            :conflicto="conflicto(x)" @aceptar="aceptarEdicion(excepciones.indexOf(x))" @cancelar="cancelarEdicion(excepciones.indexOf(x))" />
            <div v-else class="excepcion">
              <div class="excepcion-texto">
                <strong>{{ textoExcepcion(x) }}</strong> → <span :class="{ 'no-lleva': x.accion === 'NO_LLEVA' }">{{ textoSalida(x) || t('chosen design') }}</span>
                <span v-if="textoVigencia(x)" class="etiqueta ms-0">{{ textoVigencia(x) }}</span>
                <span v-if="x.vigente === false" class="etiqueta aviso ms-0">{{ t('Not in force today') }}</span>
                <span v-if="x.contexto_tipo === 'OC'" class="etiqueta info ms-0">{{ t('for one PO') }}</span>
                <span v-if="!x.id || x.cambiada" class="etiqueta ok ms-0">{{ x.id ? t('Changed') : t('New') }}</span>
                <small class="ayuda">«{{ x.motivo }}»<template v-if="autor(x)"> · {{ autor(x) }}</template></small>
              </div>
              <div v-if="editable && editando === null" class="excepcion-acciones">
                <button v-if="x.contexto_tipo !== 'OC'" type="button" class="btn-icono" :aria-label="t('Edit')" :title="t('Edit')" @click="editar(excepciones.indexOf(x))"><Icono nombre="editar" :tam="15" /></button>
                <button type="button" class="btn-icono" :aria-label="t('Remove')" :title="t('Remove')" @click="quitarExcepcion(x)"><Icono nombre="basura" :tam="15" /></button>
              </div>
            </div>
          </li>
          <li v-if="nueva">
            <ExcepcionFrase :model-value="nueva" :tipo="tipoCelda" :campos="campos" :operadores="operadores" :otras="otras"
                            :coinciden="coinciden.nueva" :conflicto="conflicto(nueva)" @aceptar="aceptarNueva" @cancelar="nueva = null; editando = null" />
          </li>
        </ol>
        <p v-else class="ayuda">{{ t('No exceptions: every record of this place uses the normal design.') }}</p>
      </section>

      <section v-if="celda.propios?.length">
        <div class="celda-cabeza">
          <h4>{{ t('Products and items with their own design ({0})', [celda.propios.length]) }}</h4>
          <button type="button" class="btn btn-chico" @click="verPropios = !verPropios">{{ verPropios ? t('Hide') : t('See') }}</button>
        </div>
        <ul v-if="verPropios" class="propios">
          <li v-for="p in celda.propios" :key="p.uso_id">
            <span><strong>{{ tx(p.destino) }}</strong> → {{ tx(p.plantilla) }} <span class="ayuda">{{ p.nivel === 'SKU' ? t('size') : t('product') }}</span></span>
            <button v-if="editable" type="button" class="btn btn-chico" @click="quitarPropio(p)">{{ t('Remove own design (inherit again)') }}</button>
          </li>
        </ul>
      </section>

      <EfectoCambio v-if="editable" :efecto="efecto" :cargando="simulando" :sin-cambios="!cambios" />
    </div>
    <footer v-if="editable && celda" class="celda-pie">
      <button type="button" class="btn" @click="emit('cerrar')">{{ t('Cancel') }}</button>
      <button type="button" class="btn btn-primario" :disabled="ocupado || !cambios || editando !== null" @click="guardar">{{ t('Save') }}</button>
    </footer>
  </section>
</template>

<style scoped>
.celda-panel { display: flex; flex-direction: column; gap: 16px; }
.celda-titulo { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; border-bottom: 1px solid var(--linea); padding-bottom: 12px; }
.celda-titulo h3 { flex: 1; margin: 0; font-size: 1.05rem; min-width: 200px; }
.celda-acciones, .celda-pie { display: flex; gap: 8px; }
.celda-pie { justify-content: flex-end; border-top: 1px solid var(--linea); padding-top: 12px; }
.celda { display: flex; flex-direction: column; gap: 18px; }
.celda h4 { margin: 0 0 8px; font-size: 0.92rem; }
.celda-cabeza { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.celda-cabeza h4 { margin: 0; }
.excepciones { margin: 8px 0 0; padding-inline-start: 22px; display: flex; flex-direction: column; gap: 8px; }
.excepcion { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
.excepcion-texto { display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: baseline; font-size: 0.9rem; }
.excepcion-texto small { flex-basis: 100%; }
.excepcion-acciones { display: flex; gap: 2px; flex: none; }
.no-lleva { color: var(--tinta-3); font-style: italic; }
.propios { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.propios li { display: flex; justify-content: space-between; gap: 10px; align-items: center; flex-wrap: wrap; border: 1px solid var(--linea); border-radius: 8px; padding: 6px 10px; font-size: 0.88rem; }
</style>
