<script setup>
import { textoVariante } from '@/nucleo/utils'
import { t, tx } from '@/i18n/index.js'
import { computed, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { errorApi } from '@/stores/ui'
import { buscarArticulos, buscarOrdenes } from '@/modulos/etiquetado/componentes/buscadores.js'
import { usarEditor } from './estado.js'

// La etiqueta como sale impresa: la dibuja el servidor con el mismo motor
// que genera los PDF, PNG y SVG. Con datos de ejemplo o con los de un
// artículo, una OC, una línea o un bulto reales. Debajo, los problemas
// (clic para elegir el elemento) y los valores que usó.
const props = defineProps({ cargando: Boolean })
const ed = usarEditor()
const est = ed.estado
const fuente = est.fuenteDatos
const lineas = ref([])

// Qué datos reales sirven: un artículo (y si se quiere, su línea de una OC), un bulto de una OC o el documento de una OC
const usaArticulo = computed(() => est.sujeto === 'ARTICULO')
watch(() => fuente.oc_id, async (id) => {
  fuente.posicion_id = ''
  fuente.bulto = ''
  lineas.value = []
  if (!id || est.sujeto !== 'ARTICULO') return
  try {
    lineas.value = (await api.get(`/ordenes/${id}`)).posiciones
  } catch (e) {
    errorApi(e)
  }
})
function usarEjemplo() {
  fuente.real = false
}
const errores = computed(() => (est.previa?.problemas || []).filter((p) => p.nivel === 'error'))
const avisos = computed(() => (est.previa?.problemas || []).filter((p) => p.nivel !== 'error'))
const etiquetaCampo = (c) => tx(ed.camposTodos.value.find((x) => x.clave === c)?.etiqueta || c)
const fondo = ref('cuadros')
</script>

<template>
  <div class="vp">
    <div class="segmentos" role="group" :aria-label="t('Data for the preview')">
      <button type="button" class="segmento" :aria-pressed="!fuente.real" @click="usarEjemplo">{{ t('Sample data') }}</button>
      <button type="button" class="segmento" :aria-pressed="fuente.real" @click="fuente.real = true">{{ t('Real data') }}</button>
    </div>
    <div v-if="fuente.real" class="vp-datos">
      <SelectBusqueda v-if="usaArticulo" v-model="fuente.articulo_id" :buscar="buscarArticulos" :etiqueta="t('Item')" :vacio="t('Choose an item')" />
      <template v-if="true">
        <SelectBusqueda v-model="fuente.oc_id" :buscar="buscarOrdenes" :etiqueta="t('PO')" :vacio="t('Choose a PO')" />
        <Seleccion v-if="usaArticulo && lineas.length" v-model="fuente.posicion_id" :aria-label="t('PO line')">
          <option value="">{{ t('Without PO line') }}</option>
          <option v-for="l in lineas" :key="l.id" :value="l.id">{{ l.posicion }} · {{ l.codigo_articulo }} {{ textoVariante(l) }}</option>
        </Seleccion>
        <label v-if="est.sujeto === 'BULTO' && fuente.oc_id" class="vp-bulto">{{ t('Package number') }}
          <input v-model="fuente.bulto" type="number" min="1" :aria-label="t('Package number')" /></label>
      </template>
    </div>

    <div class="vp-lienzo" :class="[`fondo-${fondo}`, { cargando: props.cargando }]">
      <!-- SVG del propio servidor (mismo motor de la descarga) -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div v-if="est.previa?.svg" class="vp-svg previa-etiqueta" v-html="est.previa.svg" />
      <p v-else class="ayuda">{{ t('Drawing…') }}</p>
    </div>
    <div class="vp-pie">
      <span class="ayuda">{{ est.previa?.datos === 'reales' ? t('With real data') : t('With sample data') }} · {{ t('exact server drawing') }}</span>
      <button type="button" class="btn btn-texto btn-chico" @click="fondo = fondo === 'cuadros' ? 'liso' : 'cuadros'">{{ t('Background') }}</button>
    </div>

    <div v-if="errores.length || avisos.length" class="vp-problemas">
      <button v-for="(p, i) in [...errores, ...avisos]" :key="i" type="button" class="vp-problema" :class="p.nivel" @click="p.elemento && ed.seleccionar(p.elemento)">
        <Icono :nombre="p.nivel === 'error' ? 'alerta' : 'info'" :tam="15" />
        <span><strong v-if="p.nombre">{{ p.nombre }}: </strong>{{ tx(p.mensaje) }}</span>
      </button>
    </div>
    <p v-else-if="est.previa" class="vp-ok"><Icono nombre="check" :tam="15" />{{ t('No problems: the label can be printed.') }}</p>

    <details v-if="est.previa && Object.keys(est.previa.valores || {}).length" class="vp-valores">
      <summary>{{ t('Values used ({0})', [Object.keys(est.previa.valores).length]) }}</summary>
      <dl>
        <template v-for="(v, k) in est.previa.valores" :key="k">
          <dt :title="k">{{ etiquetaCampo(k) }}</dt><dd>{{ v ?? '—' }}</dd>
        </template>
      </dl>
    </details>
  </div>
</template>

<style scoped>
.vp { display: flex; flex-direction: column; gap: 10px; }
.vp-datos { display: flex; flex-direction: column; gap: 6px; }
.vp-lienzo { border: 1px solid var(--linea); border-radius: 8px; padding: 14px; display: flex; align-items: center; justify-content: center; min-height: 140px;
  transition: opacity 0.15s; }
.vp-lienzo.cargando { opacity: 0.6; }
.fondo-cuadros { background: repeating-conic-gradient(#eef1f5 0 25%, #fff 0 50%) 0 0 / 14px 14px; }
.fondo-liso { background: var(--superficie-2); }
.vp-svg { width: 100%; --previa-alto: 340px; }
.vp-svg :deep(svg) { box-shadow: 0 1px 3px rgba(16, 24, 40, 0.25); }
.vp-pie { display: flex; justify-content: space-between; align-items: center; margin-top: -4px; }
.vp-problemas { display: flex; flex-direction: column; gap: 4px; }
.vp-problema { display: flex; gap: 8px; align-items: flex-start; text-align: left; border: 1px solid; border-radius: 8px; padding: 7px 9px; font-size: 0.8rem; cursor: pointer;
  background: var(--aviso-suave); border-color: var(--aviso-borde); color: var(--aviso); }
.vp-problema.error { background: var(--error-fondo); border-color: color-mix(in srgb, var(--error) 30%, transparent); color: var(--error); }
.vp-problema svg { flex: none; margin-top: 1px; }
.vp-ok { display: flex; gap: 6px; align-items: center; color: var(--ok); font-size: 0.82rem; margin: 0; }
.vp-valores summary { cursor: pointer; font-size: 0.8rem; color: var(--tinta-2); }
.vp-valores dl { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 3px 10px; margin: 8px 0 0; font-size: 0.78rem; }
.vp-valores dt { color: var(--tinta-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vp-valores dd { margin: 0; overflow-wrap: anywhere; }
.segmentos { display: flex; }
</style>
