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

// Requisitos no arancelarios por país (permisos, licencias, registros,
// etiquetado…) para un código o patrón de códigos. Un código puede tener
// varios; lo publicado no se borra: se desactiva o se le pone fin de vigencia.
const props = defineProps({ paises: { type: Array, default: () => [] } })
const edita = puede('aranceles.editar')
const datos = ref({ items: [], tipos: [] })
const f = reactive({ q: '', pais: '' })
const modal = ref(null)
const ocupado = ref(false)
const TIPO = { PERMIT: t('Permit'), LICENSE: t('License'), REGISTRATION: t('Registration'), CERTIFICATE: t('Certificate'), LABELING: t('Labeling'),
  SANITARY: t('Sanitary'), PHYTOSANITARY: t('Phytosanitary'), TECHNICAL: t('Technical regulation'), QUOTA: t('Quota'), PROHIBITION: t('Prohibition'), OTHER: t('Other') }

let temporizador = null
const cargando = ref(true)
async function cargar() {
  try {
    datos.value = await api.get('/aranceles/regulaciones', { q: f.q || undefined, pais: f.pais || undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
const columnas = computed(() => [
  { clave: 'pais', texto: t('Country'), prioridad: 1 },
  { clave: 'patron', texto: t('Codes'), prioridad: 1, textoValor: (v) => patronTxt(v) },
  { clave: 'nombre', texto: t('Requirement'), fija: true, prioridad: 1 },
  { clave: 'tipo', texto: t('Type'), prioridad: 2, opciones: Object.entries(TIPO) },
  { clave: 'autoridad', texto: t('Authority'), prioridad: 2, textoValor: (v) => v || '—' },
  { clave: 'obligatorio', texto: t('Mandatory'), prioridad: 3, inicial: false, opciones: [[true, t('Yes')], [false, t('No')]] },
  { clave: 'vigente_desde', texto: t('Validity'), prioridad: 3, textoValor: (v) => (v ? fechaTexto(v) : '—') },
  { clave: 'activo', texto: t('Active'), prioridad: 2, opciones: [[true, t('Yes')], [false, t('No')]] },
])
const buscar = () => { clearTimeout(temporizador); temporizador = setTimeout(cargar, 250) }
onMounted(cargar)
const patronTxt = (p) => (p === '*' ? t('All codes') : p.length > 4 ? `${p.slice(0, 4)}.${p.slice(4).match(/.{1,2}/g).join('.')}` : p)

function abrir(x = null) {
  modal.value = x ? { ...x } : { id: null, pais: f.pais || props.paises[0]?.iso, patron: '', tipo: 'PERMIT', nombre: '', autoridad: '', codigo_permiso: '',
    obligatorio: true, base_legal: '', url: '', nota: '', activo: true, vigente_desde: null, vigente_hasta: null }
}
async function guardar() {
  const m = modal.value
  ocupado.value = true
  try {
    const cuerpo = { pais: m.pais, patron: m.patron, tipo: m.tipo, nombre: m.nombre, autoridad: m.autoridad || null, codigo_permiso: m.codigo_permiso || null,
      obligatorio: m.obligatorio, base_legal: m.base_legal || null, url: m.url || null, nota: m.nota || null, activo: m.activo,
      vigente_desde: m.vigente_desde || null, vigente_hasta: m.vigente_hasta || null }
    if (m.id) await api.patch(`/aranceles/regulaciones/${m.id}`, cuerpo)
    else await api.post('/aranceles/regulaciones', cuerpo)
    modal.value = null
    avisar(t('Regulation saved.'))
    cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function activar(x, v) {
  try {
    Object.assign(x, await api.patch(`/aranceles/regulaciones/${x.id}`, { activo: v }))
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <section>
    <p class="ayuda">{{ t('Non-tariff requirements per country: permits, licenses, registrations, labeling… for a national code or a pattern (e.g. 3304 applies to every code of heading 33.04). They are loaded with package 03 or added here; what is published is deactivated, never deleted.') }}</p>
    <TablaDatos tabla="aranceles_regulaciones" :columnas="columnas" :filas="datos.items" :cargando="cargando" :clase-fila="(x) => ({ apagada: !x.activo })"
                :externos="{ q: f.q, pais: f.pais }" :etiqueta="t('Regulations')"
                @vista="(x) => { Object.assign(f, { q: x.q || '', pais: x.pais || '' }); cargar() }"
                @limpiar-externos="Object.assign(f, { q: '', pais: '' }); cargar()">
      <template #barra>
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Requirement, authority, type or code')" :aria-label="t('Search')" @input="buscar" /></label>
      </template>
      <template #filtros>
        <SelectBusqueda :model-value="f.pais" :opciones="paises.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` }))" :vacio="t('All countries')" :etiqueta="t('Country')" @update:model-value="(v) => { f.pais = v; cargar() }" />
        <button v-if="edita" type="button" class="btn btn-primario separar" @click="abrir()"><Icono nombre="mas" />{{ t('New regulation') }}</button>
      </template>
      <template #celda-pais="{ fila: x }"><span class="fuerte">{{ tx(x.pais) }}</span></template>
      <template #celda-patron="{ fila: x }"><span class="codigo">{{ tx(patronTxt(x.patron)) }}</span></template>
      <template #celda-nombre="{ fila: x }">
        <div class="requisito"><b>{{ tx(x.nombre) }}</b><span class="sub">{{ tx(x.codigo) }}<template v-if="x.codigo_permiso"> · {{ tx(x.codigo_permiso) }}</template><template v-if="!x.obligatorio"> · {{ t('optional') }}</template></span>
          <span v-if="x.base_legal" class="sub">{{ tx(x.base_legal) }}</span></div>
      </template>
      <template #celda-tipo="{ fila: x }"><span class="etiqueta ms-0">{{ tx(TIPO[x.tipo] || x.tipo) }}</span></template>
      <template #celda-autoridad="{ fila: x }"><div class="autoridad">{{ tx(x.autoridad || '—') }}<span v-if="x.fuente" class="sub codigo">{{ tx(x.fuente) }}</span></div></template>
      <template #celda-obligatorio="{ fila: x }">{{ x.obligatorio ? t('Yes') : t('No') }}</template>
      <template #celda-vigente_desde="{ fila: x }">{{ x.vigente_desde ? fechaTexto(x.vigente_desde) : '—' }}<span v-if="x.vigente_hasta" class="sub">{{ t('until {0}', [fechaTexto(x.vigente_hasta)]) }}</span></template>
      <template #celda-activo="{ fila: x }"><Interruptor :model-value="x.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="activar(x, $event)" /></template>
      <template v-if="edita" #acciones="{ fila: x }"><button type="button" class="btn-icono" :aria-label="t('Edit')" @click="abrir(x)"><Icono nombre="editar" :tam="15" /></button></template>
      <template #vacio>{{ t('No regulations loaded. Load package 03 in Data import or add one.') }}</template>
    </TablaDatos>

    <Modal v-if="modal" :titulo="modal.id ? t('Regulation {0}', [modal.codigo]) : t('New regulation')" ancho="680px" @cerrar="modal = null">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Country') }}</span>
          <SelectBusqueda v-model="modal.pais" :opciones="paises.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` }))" :etiqueta="t('Country')" :deshabilitado="!!modal.id" /></label>
        <label class="campo"><span class="req">{{ t('Code or pattern') }}</span><input v-model="modal.patron" class="entrada" maxlength="40" :placeholder="t('e.g. 3304, 6404.19 or * for all')" /></label>
        <label class="campo"><span class="req">{{ t('Type') }}</span>
          <SelectBusqueda v-model="modal.tipo" :opciones="Object.entries(TIPO).map(([valor, texto]) => ({ valor, texto }))" :etiqueta="t('Type')" /></label>
        <label class="campo"><span>{{ t('Permit or license code') }}</span><input v-model="modal.codigo_permiso" class="entrada" maxlength="60" /></label>
        <label class="campo col-completa"><span class="req">{{ t('Requirement') }}</span><input v-model="modal.nombre" class="entrada" maxlength="300" /></label>
        <label class="campo"><span>{{ t('Authority') }}</span><input v-model="modal.autoridad" class="entrada" maxlength="200" /></label>
        <label class="campo"><span>{{ t('Legal basis') }}</span><input v-model="modal.base_legal" class="entrada" maxlength="400" /></label>
        <label class="campo"><span>{{ t('Valid from') }}</span><CampoFecha v-model="modal.vigente_desde" /></label>
        <label class="campo"><span>{{ t('Valid to') }}</span><CampoFecha v-model="modal.vigente_hasta" /></label>
        <label class="campo col-completa"><span>{{ t('Official link') }}</span><input v-model="modal.url" class="entrada" maxlength="300" type="url" /></label>
        <label class="campo col-completa"><span>{{ t('Note') }}</span><input v-model="modal.nota" class="entrada" maxlength="400" /></label>
        <label class="check"><input v-model="modal.obligatorio" type="checkbox" /><span>{{ t('Mandatory') }}</span></label>
        <label class="check"><input v-model="modal.activo" type="checkbox" /><span>{{ t('Active') }}</span></label>
      </div>
      <template #pie>
        <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" :disabled="ocupado || !modal.pais || !modal.patron || !modal.nombre" @click="guardar">{{ t('Save') }}</button>
      </template>
    </Modal>
  </section>
</template>

<style scoped>
:deep(tr.apagada > td) { opacity: 0.55; }
.sub { display: block; }
.requisito { min-width: 240px; max-width: 460px; white-space: normal; }
.autoridad { min-width: 160px; max-width: 300px; white-space: normal; }
</style>
