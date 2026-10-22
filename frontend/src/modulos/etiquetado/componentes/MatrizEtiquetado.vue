<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import { fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import CeldaEtiquetado from '@/modulos/etiquetado/componentes/CeldaEtiquetado.vue'
import { ALCANCES, CANTIDADES, SUJETOS_PLURAL, textoDonde } from '@/modulos/etiquetado/etiquetas.js'

// «Qué diseño lleva cada cosa»: la pantalla principal para asignar diseños.
// Filas: toda la empresa, las familias en árbol (con sus categorías) y los artículos sin familia
// (o los tipos de empaque, para las cajas); columnas: los tipos de etiqueta.
// Cada celda (también las heredadas) se abre en la misma página, en lugar de la tabla.
const emit = defineEmits(['familias'])
const sujetos = ref([])
const sujeto = ref('ARTICULO')
const datos = ref(null)
const cargando = ref(false)
const q = ref('')
const soloProblemas = ref(false)

async function cargarSujetos() {
  try {
    const tipos = await api.get('/etiquetas/tipos')
    sujetos.value = ['ARTICULO', 'BULTO', 'DOCUMENTO'].filter((s) => tipos.some((x) => x.sujeto === s))
    if (sujetos.value.length && !sujetos.value.includes(sujeto.value)) sujeto.value = sujetos.value[0]
  } catch (e) {
    errorApi(e)
  }
}
async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/etiquetas/matriz', { sujeto: sujeto.value })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(async () => {
  await cargarSujetos()
  cargar()
})
watch(sujeto, cargar)
alCambiar(() => {
  cargarSujetos()
  cargar()
}, ['/etiquetas/usos', '/etiquetas/tipos', '/etiquetas/plantillas', '/etiquetas/familias', '/etiquetas/categorias'])

const normal = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
const nombreFila = (f) => (f.nivel === 'GENERAL' ? t('Whole company') : f.nivel === 'SIN_FAMILIA' ? t('Without family') : tx(f.nombre))
// Dónde va, si la regla de la celda lo cambia respecto del tipo de etiqueta
const dondeVa = (c, tp) => {
  const a = (c.normal || c.hereda)?.alcance
  return a && a !== tp.alcance_efectivo ? ALCANCES()[a] : ''
}
const conProblema = (f) => Object.values(f.celdas).some((c) => c.falta)
const filas = computed(() => (datos.value?.filas || []).filter((f) => (!q.value || f.nivel === 'GENERAL' || normal(`${f.nombre} ${f.codigo || ''}`).includes(normal(q.value)))
  && (!soloProblemas.value || conProblema(f))))
const cobertura = computed(() => datos.value?.cobertura)
const sinGeneral = computed(() => (datos.value?.tipos || []).filter((x) => cobertura.value?.tipos_sin_general?.includes(x.id) && x.obligatoria))

// La ventana de la celda
const abierta = ref(null)
function abrir(f, tipo) {
  window.scrollTo({ top: 0, behavior: 'smooth' })
  const nivel = f.nivel === 'SIN_FAMILIA' ? 'GENERAL' : f.nivel
  const otras = (datos.value.filas || []).filter((x) => x !== f && !['GENERAL', 'SIN_FAMILIA'].includes(x.nivel))
    .map((x) => ({ nivel: x.nivel, destino_id: x.id, nombre: x.nombre }))
  abierta.value = { tipo, nivel, destinoId: f.nivel === 'SIN_FAMILIA' ? null : f.id, nombre: f.nivel === 'SIN_FAMILIA' ? t('Whole company') : nombreFila(f), otras }
}
function guardado(opciones) {
  if (!opciones || opciones.cerrar !== false) abierta.value = null
  cargar()
}
</script>

<template>
  <CeldaEtiquetado v-if="abierta" :tipo="abierta.tipo" :nivel="abierta.nivel" :destino-id="abierta.destinoId" :nombre="abierta.nombre" :otras="abierta.otras"
                   @cerrar="abierta = null" @guardado="guardado" />
  <template v-else>
  <div class="mz-barra">
    <nav v-if="sujetos.length > 1" class="pestanas-pildora" :aria-label="t('What is labeled')">
      <button v-for="s in sujetos" :key="s" type="button" class="pildora" :aria-pressed="sujeto === s" @click="sujeto = s">{{ SUJETOS_PLURAL()[s] }}</button>
    </nav>
    <label v-if="sujeto === 'ARTICULO'" class="buscador"><Icono nombre="buscar" :tam="16" />
      <input v-model="q" type="search" :placeholder="t('Search family')" :aria-label="t('Search family')" /></label>
    <label class="check"><input v-model="soloProblemas" type="checkbox" /> {{ t('Only with problems') }}</label>
    <button v-if="cobertura" type="button" class="mz-cobertura separar" :class="{ completa: !cobertura.sin_diseno }" @click="soloProblemas = !!cobertura.sin_diseno">
      <Icono :nombre="cobertura.sin_diseno ? 'alerta' : 'check'" :tam="15" />
      {{ t('Coverage: {0} of {1} items have all their required labels', [fmtNum(cobertura.total - cobertura.sin_diseno), fmtNum(cobertura.total)]) }}
    </button>
  </div>
  <p v-for="x in sinGeneral" :key="x.id" class="nota aviso mb-3"><Icono nombre="alerta" :tam="16" />
    {{ t('“{0}” is required and the whole company has no design: families without their own design are left without labels.', [tx(x.nombre)]) }}</p>

  <div v-if="cargando && !datos" class="vacio">{{ t('Loading…') }}</div>
  <EstadoVacio v-else-if="datos && !datos.tipos.length" icono="etiqueta" :titulo="t('There are no label types for this')"
               :texto="t('Create the label types in the Label types tab; each one becomes a column here.')" />
  <div v-else-if="datos" class="mz-marco">
    <table class="mz">
      <thead>
        <tr>
          <th scope="col" class="mz-fila-cab">{{ sujeto === 'BULTO' ? t('Package type') : sujeto === 'DOCUMENTO' ? '' : t('Family') }}</th>
          <th v-for="tp in datos.tipos" :key="tp.id" scope="col">
            <span class="mz-tipo">{{ tx(tp.nombre) }}</span>
            <span class="mz-tipo-sub">{{ CANTIDADES()[tp.cantidad] }}<template v-if="tp.obligatoria"> · {{ t('required') }}</template></span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in filas" :key="`${f.nivel}:${f.id}`" :class="{ 'mz-general': f.nivel === 'GENERAL', 'mz-categoria': f.nivel === 'CATEGORIA' }">
          <th scope="row" class="mz-fila" :style="{ paddingInlineStart: `${10 + Math.max(f.profundidad - 1, 0) * 18}px` }">
            <span v-if="f.profundidad > 1" class="mz-rama" aria-hidden="true">└</span>
            <button v-if="f.nivel === 'SIN_FAMILIA'" type="button" class="enlace mz-nombre" @click="emit('familias', 'sin')">{{ nombreFila(f) }}</button>
            <span v-else class="mz-nombre">{{ nombreFila(f) }}</span>
            <span v-if="f.nivel === 'CATEGORIA'" class="etiqueta ms-1">{{ t('category') }}</span>
            <span v-if="f.articulos != null" class="mz-cuenta">{{ t('{0} items', [fmtNum(f.articulos)]) }}</span>
          </th>
          <td v-for="tp in datos.tipos" :key="tp.id" :data-tipo="tx(tp.nombre)">
            <!-- El tipo no va en este empaque (se elige en el tipo de etiqueta: «Va en») -->
            <span v-if="f.celdas[tp.id].no_aplica" class="mz-celda mz-no-aplica" :title="t('This label does not go on this package type')">{{ t('Does not go here') }}</span>
            <button v-else type="button" class="mz-celda" :class="{ falta: f.celdas[tp.id].falta, propio: f.celdas[tp.id].normal }"
                    :aria-label="`${nombreFila(f)} · ${tx(tp.nombre)}`" @click="abrir(f, tp)">
              <span v-if="f.celdas[tp.id].normal?.accion === 'NO_LLEVA'" class="mz-no-lleva"><Icono nombre="cerrar" :tam="13" />{{ t('Does not carry it') }}</span>
              <template v-else-if="f.celdas[tp.id].normal">
                <span class="mz-diseno"><Icono nombre="etiqueta" :tam="14" />{{ tx(f.celdas[tp.id].normal.plantilla) }}</span>
                <span v-if="!f.celdas[tp.id].normal.version_id" class="etiqueta aviso ms-0">{{ t('Not approved') }}</span>
              </template>
              <span v-else-if="f.celdas[tp.id].falta" class="mz-falta"><Icono nombre="alerta" :tam="14" />{{ t('No design (required)') }}</span>
              <span v-else-if="f.celdas[tp.id].hereda?.accion === 'NO_LLEVA'" class="mz-hereda">↳ {{ t('Does not carry it') }}</span>
              <span v-else-if="f.celdas[tp.id].hereda" class="mz-hereda" :title="t('Inherited from {0}', [textoDonde(f.celdas[tp.id].hereda.nivel, f.celdas[tp.id].hereda.destino)])">
                ↳ {{ tx(f.celdas[tp.id].hereda.plantilla) }}</span>
              <span v-else class="apagado">—</span>
              <span v-if="dondeVa(f.celdas[tp.id], tp)" class="mz-extra"><Icono nombre="flecha" :tam="12" />{{ dondeVa(f.celdas[tp.id], tp) }}</span>
              <span v-if="f.celdas[tp.id].excepciones || f.celdas[tp.id].propios" class="mz-extra">
                <template v-if="f.celdas[tp.id].excepciones">{{ t('{0} exceptions', [f.celdas[tp.id].excepciones]) }}</template>
                <template v-if="f.celdas[tp.id].excepciones && f.celdas[tp.id].propios"> · </template>
                <template v-if="f.celdas[tp.id].propios">{{ t('{0} with their own', [fmtNum(f.celdas[tp.id].propios)]) }}</template>
              </span>
            </button>
          </td>
        </tr>
        <tr v-if="!filas.length"><td :colspan="datos.tipos.length + 1" class="apagado">{{ t('Nothing matches.') }}</td></tr>
      </tbody>
    </table>
  </div>
  <p class="ayuda mz-leyenda">
    <span><Icono nombre="etiqueta" :tam="13" /> {{ t('design of this place') }}</span>
    <span>↳ {{ t('inherited from the row above') }}</span>
    <span><Icono nombre="cerrar" :tam="13" /> {{ t('the label does not go there (decided by a rule)') }}</span>
    <span><Icono nombre="alerta" :tam="13" /> {{ t('a required label has no design') }}</span>
    <span v-if="!puede('etiquetas.configurar')">· {{ t('Read only: you can see the cells but not change them.') }}</span>
  </p>

  </template>
</template>

<style scoped>
.mz-barra { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 12px; }
.pildora { border: 1px solid var(--linea); background: var(--superficie); border-radius: 18px; padding: 6px 14px; font: inherit; font-size: var(--t-sm); cursor: pointer; color: var(--tinta-2); }
.pildora[aria-pressed='true'] { background: var(--acento-claro); border-color: var(--acento); color: var(--acento-texto); font-weight: 600; }
.pestanas-pildora { display: flex; gap: 6px; }
.mz-cobertura { display: inline-flex; gap: 6px; align-items: center; border: 1px solid var(--aviso); color: var(--aviso); background: var(--aviso-fondo); border-radius: 18px; padding: 5px 12px; font: inherit; font-size: var(--t-sm); cursor: pointer; }
.mz-cobertura.completa { border-color: var(--ok); color: var(--ok); background: transparent; cursor: default; }
.mz-marco { overflow-x: auto; border: 1px solid var(--linea); border-radius: var(--radio-panel); background: var(--superficie); }
.mz { width: 100%; border-collapse: collapse; font-size: var(--t-sm); }
.mz th, .mz td { border-bottom: 1px solid var(--linea-suave); padding: 6px 8px; text-align: start; vertical-align: top; }
.mz thead th { background: var(--superficie-2); position: sticky; top: 0; z-index: 1; min-width: 180px; }
.mz thead .mz-fila-cab { min-width: 220px; }
.mz-tipo { display: block; font-weight: 650; }
.mz-tipo-sub { display: block; font-size: var(--t-xs); color: var(--tinta-3); font-weight: 400; }
.mz-fila { font-weight: 500; white-space: nowrap; }
.mz-general .mz-fila { font-weight: 700; }
.mz-rama { color: var(--tinta-3); margin-inline-end: 4px; }
.mz-nombre { display: inline; }
.mz-cuenta { display: block; font-size: var(--t-xs); color: var(--tinta-3); font-weight: 400; }
.mz-celda { width: 100%; min-height: 44px; text-align: start; border: 1px solid transparent; border-radius: 8px; background: none; font: inherit; color: inherit;
  padding: 6px 8px; cursor: pointer; display: flex; flex-direction: column; gap: 3px; align-items: flex-start; }
.mz-celda:hover, .mz-celda:focus-visible { border-color: var(--acento); background: var(--acento-claro); }
.mz-celda.falta { background: var(--aviso-fondo); }
.mz-diseno { display: inline-flex; gap: 5px; align-items: center; font-weight: 600; }
.mz-hereda { color: var(--tinta-3); }
.mz-no-lleva { display: inline-flex; gap: 5px; align-items: center; color: var(--tinta-2); font-style: italic; }
.mz-categoria .mz-fila { font-weight: 400; color: var(--tinta-2); }
.mz-no-aplica { color: var(--tinta-3); font-size: var(--t-xs); font-style: italic; cursor: default; background: repeating-linear-gradient(135deg, transparent 0 6px, var(--superficie-2) 6px 8px); }
.mz-falta { color: var(--aviso); display: inline-flex; gap: 5px; align-items: center; font-weight: 600; }
.mz-extra { font-size: var(--t-xs); color: var(--tinta-2); }
.mz-leyenda { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 10px; }
.mz-leyenda span { display: inline-flex; gap: 4px; align-items: center; }
/* En el celular: una tarjeta por fila con un renglón por tipo */
@media (max-width: 700px) {
  .mz-marco { border: 0; background: none; overflow: visible; }
  .mz, .mz tbody, .mz tr, .mz th, .mz td { display: block; width: 100%; }
  .mz thead { display: none; }
  .mz tr { border: 1px solid var(--linea); border-radius: 10px; margin-bottom: 10px; background: var(--superficie); }
  .mz-fila { padding-inline-start: 10px !important; white-space: normal; }
  .mz td::before { content: attr(data-tipo); display: block; font-size: var(--t-xs); color: var(--tinta-3); font-weight: 600; }
}
</style>
