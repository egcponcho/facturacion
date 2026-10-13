<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import CampoFecha from '@/componentes/CampoFecha.vue'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { fechaTexto } from '@/stores/preferencias'
import { avisar, errorApi } from '@/stores/ui'
import { fmtNum } from '@/nucleo/utils'

// Impuestos de importación por país (IVA, ITBMS, ISV, selectivo…) con tasa,
// base de cálculo, umbrales, base legal y vigencia. El DAI de cada código
// nacional vive en el código; aquí van los demás tributos y sus excepciones
// por patrón: gana el patrón más específico de cada tipo.
const props = defineProps({ paises: { type: Array, default: () => [] } })
const edita = puede('aranceles.editar')
const datos = ref({ items: [], tipos: [] })
const f = reactive({ q: '', pais: '' })
const modal = ref(null)
const ocupado = ref(false)
const TIPO = { DAI: t('Import duty (DAI)'), IVA: t('VAT (IVA)'), ITBMS: t('ITBMS (Panama sales tax)'), ISV: t('Sales tax (ISV)'), ISC: t('Excise tax (ISC)'), SELECTIVO: t('Selective consumption tax'), OTRO: t('Other') }

let temporizador = null
const cargando = ref(true)
async function cargar() {
  try {
    datos.value = await api.get('/aranceles/impuestos', { q: f.q || undefined, pais: f.pais || undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const columnas = computed(() => [
  { clave: 'pais', texto: t('Country'), prioridad: 1 },
  { clave: 'tipo', texto: t('Tax'), fija: true, prioridad: 1, opciones: Object.entries(TIPO) },
  { clave: 'tasa', texto: t('Rate'), num: true, prioridad: 1, textoValor: (v) => (v != null ? `${fmtNum(v)}%` : '—') },
  { clave: 'patron', texto: t('Codes'), prioridad: 2, textoValor: (v) => patronTxt(v) },
  { clave: 'base_calculo', texto: t('Basis'), prioridad: 2, textoValor: (v) => v || '—' },
  { clave: 'base_legal', texto: t('Legal basis'), prioridad: 3, filtro: false },
  { clave: 'vigente_desde', texto: t('Validity'), prioridad: 3, textoValor: (v) => (v ? fechaTexto(v) : '—') },
  { clave: 'activo', texto: t('Active'), prioridad: 2, opciones: [[true, t('Yes')], [false, t('No')]] },
])
const buscar = () => { clearTimeout(temporizador); temporizador = setTimeout(cargar, 250) }
onMounted(cargar)
const patronTxt = (p) => (p === '*' ? t('All codes') : p.length > 4 ? `${p.slice(0, 4)}.${p.slice(4).match(/.{1,2}/g).join('.')}` : p)

function abrir(x = null) {
  modal.value = x ? { ...x } : { id: null, pais: f.pais || props.paises[0]?.iso, patron: '*', tipo: datos.value.tipos[0] || '', tasa: null, base_calculo: '',
    umbral_desde: null, umbral_hasta: null, formula: '', base_legal: '', url: '', activo: true, vigente_desde: null, vigente_hasta: null }
}
const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v))
async function guardar() {
  const m = modal.value
  ocupado.value = true
  try {
    const cuerpo = { pais: m.pais, patron: m.patron, tipo: m.tipo, tasa: num(m.tasa), base_calculo: m.base_calculo || null, umbral_desde: num(m.umbral_desde),
      umbral_hasta: num(m.umbral_hasta), formula: m.formula || null, base_legal: m.base_legal || null, url: m.url || null, activo: m.activo,
      vigente_desde: m.vigente_desde || null, vigente_hasta: m.vigente_hasta || null }
    if (m.id) await api.patch(`/aranceles/impuestos/${m.id}`, cuerpo)
    else await api.post('/aranceles/impuestos', cuerpo)
    modal.value = null
    avisar(t('Tax rule saved.'))
    cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function activar(x, v) {
  try {
    Object.assign(x, await api.patch(`/aranceles/impuestos/${x.id}`, { activo: v }))
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <section>
    <p class="ayuda">{{ t('Import taxes per country with rate, basis, thresholds, legal basis and validity. The DAI of each national code lives in the code; here go the other taxes and any exception by code pattern (the most specific pattern of each type wins).') }}</p>
    <TablaDatos tabla="aranceles_impuestos" :columnas="columnas" :filas="datos.items" :cargando="cargando" :clase-fila="(x) => ({ apagada: !x.activo })"
                :externos="{ q: f.q, pais: f.pais }" :etiqueta="t('Taxes')"
                @vista="(x) => { Object.assign(f, { q: x.q || '', pais: x.pais || '' }); cargar() }"
                @limpiar-externos="Object.assign(f, { q: '', pais: '' }); cargar()">
      <template #barra>
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Tax, code pattern or legal basis')" :aria-label="t('Search')" @input="buscar" /></label>
      </template>
      <template #filtros>
        <SelectBusqueda :model-value="f.pais" :opciones="paises.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` }))" :vacio="t('All countries')" :etiqueta="t('Country')" @update:model-value="(v) => { f.pais = v; cargar() }" />
        <button v-if="edita" type="button" class="btn btn-primario separar" @click="abrir()"><Icono nombre="mas" />{{ t('New tax rule') }}</button>
      </template>
      <template #celda-pais="{ fila: x }"><span class="fuerte">{{ tx(x.pais) }}</span></template>
      <template #celda-tipo="{ fila: x }"><span class="etiqueta ms-0">{{ tx(TIPO[x.tipo] || x.tipo) }}</span><span class="sub codigo">{{ tx(x.codigo) }}</span></template>
      <template #celda-tasa="{ fila: x }"><span class="fuerte">{{ x.tasa != null ? `${fmtNum(x.tasa)}%` : '—' }}</span></template>
      <template #celda-patron="{ fila: x }"><span class="codigo">{{ tx(patronTxt(x.patron)) }}</span></template>
      <template #celda-base_calculo="{ fila: x }">{{ tx(x.base_calculo || '—') }}<span v-if="x.umbral_desde != null || x.umbral_hasta != null" class="sub">{{ t('from {0} to {1}', [x.umbral_desde ?? '—', x.umbral_hasta ?? '—']) }}</span></template>
      <template #celda-base_legal="{ fila: x }"><div class="base-legal ayuda">{{ tx(x.base_legal || '—') }}<span v-if="x.fuente" class="sub codigo">{{ tx(x.fuente) }}</span></div></template>
      <template #celda-vigente_desde="{ fila: x }">{{ x.vigente_desde ? fechaTexto(x.vigente_desde) : '—' }}<span v-if="x.vigente_hasta" class="sub">{{ t('until {0}', [fechaTexto(x.vigente_hasta)]) }}</span></template>
      <template #celda-activo="{ fila: x }"><Interruptor :model-value="x.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="activar(x, $event)" /></template>
      <template v-if="edita" #acciones="{ fila: x }"><button type="button" class="btn-icono" :aria-label="t('Edit')" @click="abrir(x)"><Icono nombre="editar" :tam="15" /></button></template>
      <template #vacio>{{ t('No tax rules loaded. Load package 03 in Data import or add one.') }}</template>
    </TablaDatos>

    <Modal v-if="modal" :titulo="modal.id ? t('Tax rule {0}', [modal.codigo]) : t('New tax rule')" ancho="680px" @cerrar="modal = null">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Country') }}</span>
          <SelectBusqueda v-model="modal.pais" :opciones="paises.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` }))" :etiqueta="t('Country')" :deshabilitado="!!modal.id" /></label>
        <label class="campo"><span class="req">{{ t('Tax') }}</span>
          <SelectBusqueda v-model="modal.tipo" :opciones="Object.entries(TIPO).map(([valor, texto]) => ({ valor, texto }))" :etiqueta="t('Tax')" /></label>
        <label class="campo"><span class="req">{{ t('Rate %') }}</span><input v-model="modal.tasa" type="number" min="0" step="0.01" class="entrada" /></label>
        <label class="campo"><span class="req">{{ t('Code or pattern') }}</span><input v-model="modal.patron" class="entrada" maxlength="40" :placeholder="t('e.g. 3304, 6404.19 or * for all')" /></label>
        <label class="campo"><span class="req">{{ t('Basis') }}</span><input v-model="modal.base_calculo" class="entrada" maxlength="80" :placeholder="t('e.g. CIF + DAI')" /></label>
        <label class="campo"><span>{{ t('Threshold from') }}</span><input v-model="modal.umbral_desde" type="number" step="0.01" class="entrada" /></label>
        <label class="campo"><span>{{ t('Threshold to') }}</span><input v-model="modal.umbral_hasta" type="number" step="0.01" class="entrada" /></label>
        <label class="campo"><span>{{ t('Valid from') }}</span><CampoFecha v-model="modal.vigente_desde" /></label>
        <label class="campo"><span>{{ t('Valid to') }}</span><CampoFecha v-model="modal.vigente_hasta" /></label>
        <label class="campo col-completa"><span>{{ t('Formula or rule') }}</span><input v-model="modal.formula" class="entrada" maxlength="300" /></label>
        <label class="campo col-completa"><span>{{ t('Legal basis') }}</span><input v-model="modal.base_legal" class="entrada" maxlength="400" /></label>
        <label class="campo col-completa"><span>{{ t('Official link') }}</span><input v-model="modal.url" class="entrada" maxlength="300" type="url" /></label>
        <label class="check"><input v-model="modal.activo" type="checkbox" /><span>{{ t('Active') }}</span></label>
      </div>
      <p class="ayuda">{{ t('Every tax rule needs its rate, the basis it is calculated on and the official tax source of its country or its legal basis. There are no example taxes: what is not loaded from an official source does not apply.') }}</p>
      <template #pie>
        <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" :disabled="ocupado || !modal.pais || !modal.patron" @click="guardar">{{ t('Save') }}</button>
      </template>
    </Modal>
  </section>
</template>

<style scoped>
:deep(tr.apagada > td) { opacity: 0.55; }
.sub { display: block; }
.base-legal { min-width: 200px; max-width: 380px; white-space: normal; }
</style>
