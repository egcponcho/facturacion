<script setup>
import { t, tx } from '../../i18n/index.js'
import { onMounted, reactive, ref } from 'vue'
import { api } from '../../api'
import CampoFecha from '../CampoFecha.vue'
import Icono from '../Icono.vue'
import Interruptor from '../Interruptor.vue'
import Modal from '../Modal.vue'
import SelectBusqueda from '../SelectBusqueda.vue'
import { puede } from '../../stores/sesion'
import { fechaTexto } from '../../stores/preferencias'
import { avisar, errorApi } from '../../stores/ui'

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
async function cargar() {
  try {
    datos.value = await api.get('/aranceles/regulaciones', { q: f.q || undefined, pais: f.pais || undefined })
  } catch (e) {
    errorApi(e)
  }
}
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
    <div class="filtros" v-filtros>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Requirement, authority, type or code')" :aria-label="t('Search')" @input="buscar" /></label>
      <SelectBusqueda :model-value="f.pais" :opciones="paises.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` }))" :vacio="t('All countries')" :etiqueta="t('Country')" @update:model-value="(v) => { f.pais = v; cargar() }" />
      <button v-if="edita" class="btn btn-primario separar" @click="abrir()"><Icono nombre="mas" />{{ t('New regulation') }}</button>
    </div>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Country') }}</th><th>{{ t('Codes') }}</th><th>{{ t('Requirement') }}</th><th>{{ t('Type') }}</th><th>{{ t('Authority') }}</th><th>{{ t('Validity') }}</th><th>{{ t('Active') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-if="!datos.items.length"><td colspan="8" class="vacio">{{ t('No regulations loaded. Load package 03 in Data import or add one.') }}</td></tr>
          <tr v-for="x in datos.items" :key="x.id" :class="{ apagada: !x.activo }">
            <td class="fuerte">{{ tx(x.pais) }}</td>
            <td class="codigo">{{ tx(patronTxt(x.patron)) }}</td>
            <td class="envolver"><b>{{ tx(x.nombre) }}</b><span class="sub">{{ tx(x.codigo) }}<template v-if="x.codigo_permiso"> · {{ tx(x.codigo_permiso) }}</template><template v-if="!x.obligatorio"> · {{ t('optional') }}</template></span>
              <span v-if="x.base_legal" class="sub">{{ tx(x.base_legal) }}</span></td>
            <td><span class="etiqueta">{{ tx(TIPO[x.tipo] || x.tipo) }}</span></td>
            <td class="envolver">{{ tx(x.autoridad || '—') }}<span v-if="x.fuente" class="sub codigo">{{ tx(x.fuente) }}</span></td>
            <td>{{ x.vigente_desde ? fechaTexto(x.vigente_desde) : '—' }}<span v-if="x.vigente_hasta" class="sub">{{ t('until {0}', [fechaTexto(x.vigente_hasta)]) }}</span></td>
            <td><Interruptor :model-value="x.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="activar(x, $event)" /></td>
            <td><button v-if="edita" type="button" class="btn-icono" :aria-label="t('Edit')" @click="abrir(x)"><Icono nombre="editar" :tam="15" /></button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <Modal v-if="modal" :titulo="modal.id ? t('Regulation {0}', [modal.codigo]) : t('New regulation')" ancho="680px" @cerrar="modal = null">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Country') }}</span>
          <SelectBusqueda v-model="modal.pais" :opciones="paises.map((p) => ({ valor: p.iso, texto: `${p.iso} · ${p.nombre}` }))" :etiqueta="t('Country')" :deshabilitado="!!modal.id" /></label>
        <label class="campo"><span class="req">{{ t('Code or pattern') }}</span><input v-model="modal.patron" class="entrada" maxlength="40" :placeholder="t('e.g. 3304, 6404.19 or * for all')" /></label>
        <label class="campo"><span class="req">{{ t('Type') }}</span>
          <SelectBusqueda v-model="modal.tipo" :opciones="Object.entries(TIPO).map(([valor, texto]) => ({ valor, texto }))" :etiqueta="t('Type')" /></label>
        <label class="campo"><span>{{ t('Permit or license code') }}</span><input v-model="modal.codigo_permiso" class="entrada" maxlength="60" /></label>
        <label class="campo" style="grid-column: 1 / -1"><span class="req">{{ t('Requirement') }}</span><input v-model="modal.nombre" class="entrada" maxlength="300" /></label>
        <label class="campo"><span>{{ t('Authority') }}</span><input v-model="modal.autoridad" class="entrada" maxlength="200" /></label>
        <label class="campo"><span>{{ t('Legal basis') }}</span><input v-model="modal.base_legal" class="entrada" maxlength="400" /></label>
        <label class="campo"><span>{{ t('Valid from') }}</span><CampoFecha v-model="modal.vigente_desde" /></label>
        <label class="campo"><span>{{ t('Valid to') }}</span><CampoFecha v-model="modal.vigente_hasta" /></label>
        <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Official link') }}</span><input v-model="modal.url" class="entrada" maxlength="300" type="url" /></label>
        <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Note') }}</span><input v-model="modal.nota" class="entrada" maxlength="400" /></label>
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
tr.apagada td { opacity: 0.55; }
.sub { display: block; }
</style>
