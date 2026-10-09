<script setup>
import { t, tx } from '@/i18n/index.js'
import { onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import CampoFecha from '@/componentes/CampoFecha.vue'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
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
async function cargar() {
  try {
    datos.value = await api.get('/aranceles/impuestos', { q: f.q || undefined, pais: f.pais || undefined })
  } catch (e) {
    errorApi(e)
  }
}
const buscar = () => { clearTimeout(temporizador); temporizador = setTimeout(cargar, 250) }
onMounted(cargar)
const patronTxt = (p) => (p === '*' ? t('All codes') : p.length > 4 ? `${p.slice(0, 4)}.${p.slice(4).match(/.{1,2}/g).join('.')}` : p)

function abrir(x = null) {
  modal.value = x ? { ...x } : { id: null, pais: f.pais || props.paises[0]?.iso, patron: '*', tipo: 'IVA', tasa: null, base_calculo: 'CIF + DAI',
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
    <div class="filtros" v-filtros>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Tax, code pattern or legal basis')" :aria-label="t('Search')" @input="buscar" /></label>
      <SelectBusqueda :model-value="f.pais" :opciones="paises.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` }))" :vacio="t('All countries')" :etiqueta="t('Country')" @update:model-value="(v) => { f.pais = v; cargar() }" />
      <button v-if="edita" class="btn btn-primario separar" @click="abrir()"><Icono nombre="mas" />{{ t('New tax rule') }}</button>
    </div>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Country') }}</th><th>{{ t('Tax') }}</th><th class="num">{{ t('Rate') }}</th><th>{{ t('Codes') }}</th><th>{{ t('Basis') }}</th><th>{{ t('Legal basis') }}</th><th>{{ t('Validity') }}</th><th>{{ t('Active') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-if="!datos.items.length"><td colspan="9" class="vacio">{{ t('No tax rules loaded. Load package 03 in Data import or add one.') }}</td></tr>
          <tr v-for="x in datos.items" :key="x.id" :class="{ apagada: !x.activo }">
            <td class="fuerte">{{ tx(x.pais) }}</td>
            <td><span class="etiqueta">{{ tx(TIPO[x.tipo] || x.tipo) }}</span><span class="sub codigo">{{ tx(x.codigo) }}</span></td>
            <td class="num fuerte">{{ x.tasa != null ? `${fmtNum(x.tasa)}%` : '—' }}</td>
            <td class="codigo">{{ tx(patronTxt(x.patron)) }}</td>
            <td>{{ tx(x.base_calculo || '—') }}<span v-if="x.umbral_desde != null || x.umbral_hasta != null" class="sub">{{ t('from {0} to {1}', [x.umbral_desde ?? '—', x.umbral_hasta ?? '—']) }}</span></td>
            <td class="envolver ayuda">{{ tx(x.base_legal || '—') }}<span v-if="x.fuente" class="sub codigo">{{ tx(x.fuente) }}</span></td>
            <td>{{ x.vigente_desde ? fechaTexto(x.vigente_desde) : '—' }}<span v-if="x.vigente_hasta" class="sub">{{ t('until {0}', [fechaTexto(x.vigente_hasta)]) }}</span></td>
            <td><Interruptor :model-value="x.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="activar(x, $event)" /></td>
            <td><button v-if="edita" type="button" class="btn-icono" :aria-label="t('Edit')" @click="abrir(x)"><Icono nombre="editar" :tam="15" /></button></td>
          </tr>
        </tbody>
      </table>
    </div>

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
        <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Formula or rule') }}</span><input v-model="modal.formula" class="entrada" maxlength="300" /></label>
        <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Legal basis') }}</span><input v-model="modal.base_legal" class="entrada" maxlength="400" /></label>
        <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Official link') }}</span><input v-model="modal.url" class="entrada" maxlength="300" type="url" /></label>
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
tr.apagada td { opacity: 0.55; }
.sub { display: block; }
</style>
