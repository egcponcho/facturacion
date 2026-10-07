<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import Icono from '../Icono.vue'
import { puede } from '../../stores/sesion'
import { fechaTexto } from '../../stores/preferencias'
import { avisar, errorApi } from '../../stores/ui'
import { fmtNum } from '../../utils'

// Paquetes de carga oficiales, por etapas: el archivo sube a una previa
// (staging) que valida y muestra qué cambiaría contra lo vigente; nada se
// aplica hasta publicar. La carga actualiza por clave natural y nunca borra lo
// publicado; un cambio en una versión publicada se marca como advertencia.
const emit = defineEmits(['cargado'])
const edita = puede('aranceles.editar')
const PAQUETES = [
  { n: 1, titulo: t('Official catalogs'), detalle: t('Sources, versions, countries (code schema), chapter control and domain-chapter map.'), hojas: 'Sources · Versions · Countries · Chapter_Control · Domain_Chapter_Map' },
  { n: 2, titulo: t('Dynamic engine'), detalle: t('Classification domains, attributes, options, scopes and rules.'), hojas: 'Domains · Attributes · Attribute_Options · Attribute_Scope · Classification_Rules · Rule_Conditions' },
  { n: 3, titulo: t('National codes, regulations and taxes'), detalle: t('Official national codes per country and version, permits and tax rules with their legal basis.'), hojas: 'Country_Source_Map · National_Codes · Regulations · Taxes' },
]
const ACCION = { NUEVO: ['ok', t('New')], CAMBIO: ['acento', t('Changed')], ELIMINADO: ['error', t('Replaced')] }
const ESTADO = { PREVIA: ['acento', t('In preview')], PUBLICADA: ['ok', t('Published')], DESCARTADA: ['', t('Discarded')] }
const lote = ref(null)
const historial = ref([])
const filtro = ref('')
const ocupado = ref(false)
const archivo = ref(null)

async function cargarHistorial() {
  try {
    historial.value = await api.get('/aranceles/oficial/lotes')
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargarHistorial)
async function bajar(p) {
  try {
    await api.descargar(`/aranceles/oficial/paquete/${p.n}`, `package_${p.n}.xlsx`)
  } catch (e) {
    errorApi(e)
  }
}
async function subir(e) {
  const a = e.target.files?.[0]
  e.target.value = ''
  if (!a) return
  const datos = new FormData()
  datos.append('archivo', a)
  ocupado.value = true
  try {
    lote.value = await api.post('/aranceles/oficial/previa', datos)
    filtro.value = ''
    cargarHistorial()
  } catch (err) {
    errorApi(err)
  } finally {
    ocupado.value = false
  }
}
async function abrir(x) {
  try {
    lote.value = await api.get(`/aranceles/oficial/lotes/${x.id}`)
    filtro.value = ''
  } catch (e) {
    errorApi(e)
  }
}
async function accion(que) {
  ocupado.value = true
  try {
    const r = await api.post(`/aranceles/oficial/lotes/${lote.value.id}/${que}`)
    if (que === 'publicar') {
      avisar(t('Published: {0} created, {1} updated.', [r.creados, r.actualizados]))
      emit('cargado')
    } else avisar(t('Preview discarded. Nothing was applied.'))
    lote.value = { ...lote.value, ...r }
    cargarHistorial()
  } catch (e) {
    errorApi(e)
    if (e.status === 409) cargarHistorial()
  } finally {
    ocupado.value = false
  }
}
const filas = computed(() => (lote.value?.filas || []).filter((f) => !filtro.value || (filtro.value === 'aviso' ? f.advertencia : f.accion === filtro.value)))
const cuenta = (a) => (lote.value?.filas || []).filter((f) => (a === 'aviso' ? f.advertencia : f.accion === a)).length
const campos = (f) => Object.keys(f.accion === 'NUEVO' ? f.despues || {} : f.antes || {}).filter((k) => !k.endsWith('_id') || f.accion !== 'NUEVO')
const valor = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v))
</script>

<template>
  <section class="paquetes">
    <p class="ayuda">{{ t('Official data is loaded by stages: the file goes to a preview that validates it and shows what would change against what is in force; nothing is applied until you publish. Each load updates by natural key and never deletes what is published.') }}</p>
    <input ref="archivo" type="file" accept=".xlsx" hidden @change="subir" />
    <article v-for="p in PAQUETES" :key="p.n" class="panel paquete">
      <span class="num">{{ String(p.n).padStart(2, '0') }}</span>
      <div class="cuerpo">
        <h3>{{ tx(p.titulo) }}</h3>
        <p>{{ tx(p.detalle) }}</p>
        <p class="ayuda codigo">{{ tx(p.hojas) }}</p>
      </div>
      <div class="acciones">
        <button class="btn" @click="bajar(p)"><Icono nombre="descargar" :tam="15" />{{ t('Download package') }}</button>
        <button v-if="edita" class="btn btn-primario" :disabled="ocupado" @click="archivo.click()"><Icono nombre="importar" :tam="15" />{{ t('Upload to preview') }}</button>
      </div>
    </article>

    <article v-if="lote" class="panel previa">
      <header class="previa-cab">
        <div>
          <h3>{{ t('Load {0}', [lote.archivo]) }} <span class="etiqueta" :class="ESTADO[lote.estado]?.[0]">{{ tx(ESTADO[lote.estado]?.[1] || lote.estado) }}</span></h3>
          <p class="ayuda">{{ t('Uploaded {0} · checksum {1}', [fechaTexto(lote.creado_en), lote.checksum.slice(0, 12)]) }}</p>
        </div>
        <div v-if="lote.estado === 'PREVIA' && edita" class="acciones">
          <button class="btn" :disabled="ocupado" @click="accion('descartar')">{{ t('Discard') }}</button>
          <button class="btn btn-primario" :disabled="ocupado || !lote.filas.length || lote.errores.length > 0"
                  :title="lote.errores.length ? t('A load with errors cannot be published') : ''" @click="accion('publicar')"><Icono nombre="check" :tam="15" />{{ t('Publish') }}</button>
        </div>
      </header>
      <div class="chips">
        <button class="pildora" :aria-pressed="!filtro" @click="filtro = ''">{{ t('All') }} <span class="cuenta">{{ fmtNum(lote.filas.length) }}</span></button>
        <button v-for="(v, k) in ACCION" :key="k" class="pildora" :aria-pressed="filtro === k" @click="filtro = k">{{ tx(v[1]) }} <span class="cuenta">{{ fmtNum(cuenta(k)) }}</span></button>
        <button class="pildora" :aria-pressed="filtro === 'aviso'" @click="filtro = 'aviso'"><Icono nombre="alerta" :tam="14" />{{ t('Warnings') }} <span class="cuenta">{{ fmtNum(cuenta('aviso')) }}</span></button>
        <span class="ayuda">{{ t('{0} rows without changes', [fmtNum(Math.max(0, lote.resumen.sin_cambio || 0))]) }}</span>
      </div>
      <div v-if="lote.errores.length" class="errores">
        <b>{{ t('{0} rows with errors: the load cannot be published until the file is fixed and uploaded again', [lote.errores.length]) }}</b>
        <ul><li v-for="(e, i) in lote.errores.slice(0, 30)" :key="i"><span class="codigo">{{ tx(e.fila) }}</span> {{ tx(e.mensaje) }}</li></ul>
      </div>
      <p v-if="!lote.filas.length && !lote.errores.length" class="ayuda">{{ t('The file matches what is in force: nothing would change.') }}</p>
      <div v-if="filas.length" class="tabla-marco diffs">
        <table class="tabla">
          <thead><tr><th>{{ t('Data') }}</th><th>{{ t('Key') }}</th><th>{{ t('Change') }}</th><th>{{ t('Before → after') }}</th></tr></thead>
          <tbody>
            <tr v-for="f in filas.slice(0, 300)" :key="f.id">
              <td>{{ tx(f.tabla_txt) }}</td>
              <td class="codigo fuerte">{{ tx(f.clave) }}</td>
              <td><span class="etiqueta" :class="ACCION[f.accion]?.[0]">{{ tx(ACCION[f.accion]?.[1] || f.accion) }}</span></td>
              <td class="envolver">
                <div v-for="k in campos(f).slice(0, 8)" :key="k" class="campo-diff">
                  <span class="k">{{ tx(k) }}</span>
                  <template v-if="f.accion === 'CAMBIO'"><del>{{ tx(valor(f.antes[k])) }}</del> → <ins>{{ tx(valor(f.despues[k])) }}</ins></template>
                  <template v-else-if="f.accion === 'NUEVO'"><ins>{{ tx(valor(f.despues[k])) }}</ins></template>
                  <template v-else><del>{{ tx(valor(f.antes[k])) }}</del></template>
                </div>
                <p v-if="f.advertencia" class="aviso"><Icono nombre="alerta" :tam="13" />{{ tx(f.advertencia) }}</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="filas.length > 300" class="ayuda">{{ t('Showing {0} of {1}.', [300, fmtNum(filas.length)]) }}</p>
    </article>

    <article v-if="historial.length" class="panel">
      <h3 class="titulo-hist">{{ t('Load history') }}</h3>
      <ul class="historial">
        <li v-for="x in historial" :key="x.id">
          <button type="button" class="enlace" @click="abrir(x)">{{ tx(x.archivo) }}</button>
          <span class="etiqueta" :class="ESTADO[x.estado]?.[0]">{{ tx(ESTADO[x.estado]?.[1] || x.estado) }}</span>
          <span class="ayuda">{{ fechaTexto(x.creado_en) }}<template v-if="x.publicado_en"> · {{ t('published {0}', [fechaTexto(x.publicado_en)]) }}</template> · {{ t('{0} errors', [x.errores.length]) }}</span>
        </li>
      </ul>
    </article>
  </section>
</template>

<style scoped>
.paquetes { display: grid; gap: 10px; }
.paquete { display: grid; grid-template-columns: auto 1fr auto; gap: 14px; align-items: center; }
.num { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); font-weight: 800; }
.cuerpo h3 { margin: 0; font-size: 1rem; }
.cuerpo p { margin: 2px 0 0; }
.acciones { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.previa-cab { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
.previa-cab h3 { margin: 0; font-size: 1.05rem; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 12px 0; }
.errores { border: 1px solid var(--error); background: var(--error-fondo); border-radius: var(--radio); padding: 8px 12px; margin-bottom: 10px; font-size: 0.86rem; }
.errores ul { margin: 6px 0 0; padding-inline-start: 18px; max-height: 200px; overflow: auto; }
.diffs { max-height: 60vh; overflow: auto; }
.campo-diff { font-size: 0.82rem; }
.campo-diff .k { color: var(--tinta-3); margin-inline-end: 6px; }
del { color: var(--error); }
ins { color: var(--ok); text-decoration: none; font-weight: 600; }
.aviso { display: flex; gap: 5px; align-items: center; margin: 4px 0 0; font-size: 0.8rem; color: var(--aviso, var(--tinta-2)); }
.titulo-hist { margin: 0 0 8px; font-size: 1rem; }
.historial { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.historial li { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 0.88rem; }
@media (max-width: 640px) { .paquete { grid-template-columns: auto 1fr; } .acciones { grid-column: 1 / -1; justify-content: flex-start; } }
</style>
