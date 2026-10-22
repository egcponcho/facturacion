<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import { avisar } from '@/stores/ui'
import { puede } from '@/stores/sesion'
import { fmtFechaHora } from '@/nucleo/utils'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import BotonArchivo from '@/componentes/BotonArchivo.vue'
import EstadoVacio from '@/componentes/EstadoVacio.vue'

// Integraciones con sistemas externos (ERP u otros). Cada una elige un formato
// de intercambio (adaptador) y, por entidad, cómo se llaman sus campos y
// códigos (mapeo versionado). Lo que entra pasa por las mismas validaciones
// que una carga a mano; lo que sale queda registrado para no reenviarlo.
const meta = ref(null)
const elegida = ref(null)
const edicion = ref(null) // datos del formulario de la integración (nueva o elegida)
const mapeoAbierto = ref(null) // { entidad, direccion }
const formMapeo = reactive({ campos: {}, valores: {}, codigos: {}, formato_fecha: '' })
const previa = ref(null)
const bitacora = ref([])
const ocupado = ref(false)
const configura = computed(() => puede('integraciones.configurar'))
const ejecuta = computed(() => puede('integraciones.ejecutar'))

async function cargar() {
  meta.value = await api.get('/integraciones')
  if (elegida.value) elegida.value = meta.value.integraciones.find((x) => x.id === elegida.value.id) || null
}
onMounted(cargar)

const adaptador = (codigo) => meta.value?.adaptadores.find((a) => a.codigo === codigo)
const entidad = (codigo) => meta.value?.entidades.find((e) => e.entidad === codigo)
const DIRECCION = { ENTRADA: t('In: the external system sends'), SALIDA: t('Out: the system sends') }
const ESTADO = { PREVIA: [t('Preview'), 'info'], APLICADA: [t('Applied'), 'ok'], CON_ERRORES: [t('Applied with errors'), 'aviso'], FALLIDA: [t('Failed'), 'peligro'] }

function nueva() {
  elegida.value = null
  edicion.value = { codigo: '', nombre: '', sistema: '', adaptador: meta.value.adaptadores[0]?.codigo, parametros: {}, activa: true }
}
async function elegir(x) {
  elegida.value = x
  edicion.value = null
  previa.value = null
  mapeoAbierto.value = null
  bitacora.value = (await api.get(`/integraciones/${x.id}/ejecuciones`, { size: 10 })).items
}
function editar() {
  edicion.value = JSON.parse(JSON.stringify({ ...elegida.value }))
}
async function guardar() {
  ocupado.value = true
  try {
    const d = edicion.value
    const cuerpo = { codigo: d.codigo, nombre: d.nombre, sistema: d.sistema, adaptador: d.adaptador, parametros: d.parametros, activa: d.activa }
    const x = d.id ? await api.put(`/integraciones/${d.id}`, cuerpo) : await api.post('/integraciones', cuerpo)
    avisar(t('Integration saved'))
    edicion.value = null
    await cargar()
    await elegir(meta.value.integraciones.find((i) => i.id === x.id))
  } catch (e) {
    avisar(e.message, 'error')
  } finally {
    ocupado.value = false
  }
}

// ---- Mapeo de una entidad -------------------------------------------------------
const mapeoVigente = (ent, dir) => elegida.value?.mapeos.find((m) => m.entidad === ent && m.direccion === dir)
function abrirMapeo(ent, dir) {
  const m = mapeoVigente(ent, dir)
  mapeoAbierto.value = { entidad: ent, direccion: dir }
  formMapeo.campos = { ...(m?.campos || {}) }
  formMapeo.valores = { ...(m?.valores || {}) }
  // Los códigos se editan como «EXTERNO=INTERNO, OTRO=…»
  formMapeo.codigos = Object.fromEntries(Object.entries(m?.codigos || {}).map(([k, v]) => [k, Object.entries(v).map(([a, b]) => `${a}=${b}`).join(', ')]))
  formMapeo.formato_fecha = m?.formato_fecha || ''
}
function leerCodigos(texto) {
  return Object.fromEntries(String(texto || '').split(',').map((x) => x.split('=').map((y) => y.trim())).filter(([a, b]) => a && b))
}
async function guardarMapeo() {
  const { entidad: ent, direccion: dir } = mapeoAbierto.value
  ocupado.value = true
  try {
    const m = await api.put(`/integraciones/${elegida.value.id}/mapeos/${ent}/${dir}`, {
      campos: formMapeo.campos, valores: formMapeo.valores, formato_fecha: formMapeo.formato_fecha || null,
      codigos: Object.fromEntries(Object.entries(formMapeo.codigos).map(([k, v]) => [k, leerCodigos(v)])),
    })
    avisar(t('Mapping saved as version {0}', [m.version]))
    mapeoAbierto.value = null
    await cargar()
  } catch (e) {
    avisar(e.message, 'error')
  } finally {
    ocupado.value = false
  }
}

// ---- Intercambio --------------------------------------------------------------------
async function subir(ent, archivo) {
  const datos = new FormData()
  datos.append('archivo', archivo)
  ocupado.value = true
  try {
    previa.value = await api.post(`/integraciones/${elegida.value.id}/entrada/${ent}`, datos)
  } catch (e) {
    avisar(e.message, 'error')
  } finally {
    ocupado.value = false
  }
}
async function aplicar() {
  ocupado.value = true
  try {
    const r = await api.post(`/integraciones/ejecuciones/${previa.value.id}/aplicar`)
    avisar(t('{0} lines applied', [r.resumen.aplicadas || 0]))
    previa.value = null
    await elegir(elegida.value)
  } catch (e) {
    avisar(e.message, 'error')
  } finally {
    ocupado.value = false
  }
}
const soloNuevas = ref(true)
async function exportar(ent) {
  ocupado.value = true
  try {
    await api.descargar(`/integraciones/${elegida.value.id}/salida/${ent}`, `${ent}.csv`, { solo_nuevas: soloNuevas.value }, {})
    await elegir(elegida.value)
  } catch (e) {
    avisar(e.message, 'error')
  } finally {
    ocupado.value = false
  }
}
const resumenTexto = (r) => Object.entries(r || {}).filter(([, v]) => typeof v === 'number').map(([k, v]) => `${tx(k)}: ${v}`).join(' · ')
</script>

<template>
  <div>
    <header class="pagina-cabeza">
      <div>
        <h1>{{ t('Integrations') }}</h1>
        <p>{{ t('Exchange data with your ERP or any external system through files, without changing how the system works: each integration says how the external system names its fields and codes.') }}</p>
      </div>
      <button v-if="configura && meta" class="btn btn-primario" @click="nueva"><Icono nombre="mas" />{{ t('New integration') }}</button>
    </header>

    <div v-if="!meta" class="esqueleto" style="height: 120px" />
    <template v-else>
      <EstadoVacio v-if="!meta.integraciones.length && !edicion" icono="ruta" :titulo="t('No integrations yet')"
                   :texto="t('Create one per external system: choose its file format and map its fields.')" />
      <div class="int-rejilla">
        <nav v-if="meta.integraciones.length" class="int-lista" :aria-label="t('Integrations')">
          <button v-for="x in meta.integraciones" :key="x.id" type="button" class="int-item" :aria-current="elegida?.id === x.id ? 'true' : undefined" @click="elegir(x)">
            <span class="int-item-cabeza"><b>{{ tx(x.nombre) }}</b><span class="etiqueta" :class="x.activa ? 'ok' : 'neutro'">{{ x.activa ? t('Active') : t('Inactive') }}</span></span>
            <small>{{ x.codigo }} · {{ tx(adaptador(x.adaptador)?.nombre || x.adaptador) }}<template v-if="x.sistema"> · {{ tx(x.sistema) }}</template></small>
            <small v-if="x.ultima_ejecucion" class="apagado">{{ t('Last run') }}: {{ fmtFechaHora(x.ultima_ejecucion.iniciada_en) }}</small>
          </button>
        </nav>

        <section class="int-detalle">
          <!-- Datos de la integración (nueva o en edición) -->
          <form v-if="edicion" class="panel int-form" @submit.prevent="guardar">
            <h2>{{ edicion.id ? t('Edit integration') : t('New integration') }}</h2>
            <div class="rejilla-campos">
              <label class="campo"><span>{{ t('Code') }}</span><input v-model="edicion.codigo" class="entrada" maxlength="20" required /></label>
              <label class="campo"><span>{{ t('Name') }}</span><input v-model="edicion.nombre" class="entrada" maxlength="100" required /></label>
              <label class="campo"><span>{{ t('External system') }}</span><input v-model="edicion.sistema" class="entrada" maxlength="60" :placeholder="t('Descriptive only, e.g. the ERP and its version')" /></label>
              <label class="campo"><span>{{ t('File format') }}</span>
                <Seleccion v-model="edicion.adaptador" class="entrada"><option v-for="a in meta.adaptadores" :key="a.codigo" :value="a.codigo">{{ tx(a.nombre) }}</option></Seleccion></label>
              <label v-for="p in adaptador(edicion.adaptador)?.parametros || []" :key="p.nombre" class="campo">
                <span>{{ tx(p.ayuda) }}</span>
                <Seleccion v-if="p.tipo.startsWith('opcion:')" v-model="edicion.parametros[p.nombre]" class="entrada">
                  <option v-for="o in p.tipo.slice(7).split(',')" :key="o" :value="o">{{ o.toUpperCase() }}</option></Seleccion>
                <input v-else v-model="edicion.parametros[p.nombre]" class="entrada" :type="p.tipo === 'entero' ? 'number' : 'text'" :placeholder="String(p.defecto ?? '')" />
              </label>
              <label class="check"><input v-model="edicion.activa" type="checkbox" />{{ t('Active') }}</label>
            </div>
            <div class="fila-flex gap-2"><button class="btn btn-primario" :disabled="ocupado">{{ t('Save') }}</button><button type="button" class="btn" @click="edicion = null">{{ t('Cancel') }}</button></div>
          </form>

          <template v-else-if="elegida">
            <div class="panel">
              <div class="fila-flex entre">
                <div><h2>{{ tx(elegida.nombre) }}</h2><p class="ayuda">{{ elegida.codigo }} · {{ tx(adaptador(elegida.adaptador)?.nombre) }}<template v-if="elegida.sistema"> · {{ tx(elegida.sistema) }}</template></p></div>
                <button v-if="configura" class="btn btn-chico" @click="editar"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button>
              </div>
            </div>

            <!-- Una tarjeta por entidad y dirección: su mapeo y su intercambio -->
            <div v-for="e in meta.entidades" :key="e.entidad" class="panel">
              <template v-for="dir in e.direcciones" :key="dir">
                <div class="fila-flex entre">
                  <div><h3>{{ tx(e.nombre) }}</h3><p class="ayuda">{{ DIRECCION[dir] }}<template v-if="mapeoVigente(e.entidad, dir)"> · {{ t('Mapping version {0}', [mapeoVigente(e.entidad, dir).version]) }}</template><template v-else> · {{ t('No mapping: fields are read with their system names') }}</template></p></div>
                  <div class="fila-flex gap-2">
                    <button v-if="configura" class="btn btn-chico" @click="abrirMapeo(e.entidad, dir)"><Icono nombre="lista" :tam="14" />{{ t('Map fields') }}</button>
                    <BotonArchivo v-if="ejecuta && dir === 'ENTRADA' && elegida.activa" class="btn btn-chico btn-primario" acepta=".csv,.xlsx,.json" :deshabilitado="ocupado" @elegir="(f) => subir(e.entidad, f)">
                      <Icono nombre="importar" :tam="14" />{{ t('Upload file') }}</BotonArchivo>
                    <template v-if="ejecuta && dir === 'SALIDA' && elegida.activa">
                      <label class="check"><input v-model="soloNuevas" type="checkbox" />{{ t('Only not sent yet') }}</label>
                      <button class="btn btn-chico btn-primario" :disabled="ocupado" @click="exportar(e.entidad)"><Icono nombre="descargar" :tam="14" />{{ t('Generate file') }}</button>
                    </template>
                  </div>
                </div>

                <!-- Mapeo: nombre externo, valor por defecto y códigos de cada campo interno -->
                <div v-if="mapeoAbierto?.entidad === e.entidad && mapeoAbierto?.direccion === dir" class="int-mapeo">
                  <p class="ayuda">{{ t('Write how the external system names each field; empty: its system name. Codes translate values, as pairs separated by commas: APPROVED=C, PENDING=P.') }}</p>
                  <div class="tabla-envoltura">
                    <table class="tabla">
                      <thead><tr><th>{{ t('System field') }}</th><th>{{ t('External field name') }}</th><th v-if="dir === 'ENTRADA'">{{ t('Default value') }}</th><th>{{ t('Codes (EXTERNAL=SYSTEM)') }}</th></tr></thead>
                      <tbody>
                        <tr v-for="c in e.campos" :key="c.campo">
                          <td><span :class="{ req: c.requerido }">{{ tx(c.etiqueta) }}</span><br><code class="apagado">{{ c.campo }}</code></td>
                          <td><input v-model="formMapeo.campos[c.campo]" class="entrada" :placeholder="c.campo" :aria-label="t('External field name')" /></td>
                          <td v-if="dir === 'ENTRADA'"><input v-model="formMapeo.valores[c.campo]" class="entrada" :aria-label="t('Default value')" /></td>
                          <td><input v-model="formMapeo.codigos[c.campo]" class="entrada" :aria-label="t('Codes (EXTERNAL=SYSTEM)')" /></td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div class="fila-flex gap-2">
                    <label v-if="dir === 'ENTRADA'" class="campo"><span>{{ t('Date format of the file') }}</span>
                      <Seleccion v-model="formMapeo.formato_fecha" class="entrada"><option value="">{{ t('ISO or the user format') }}</option><option v-for="f in meta.formatos_fecha" :key="f" :value="f">{{ f }}</option></Seleccion></label>
                    <button class="btn btn-primario" :disabled="ocupado" @click="guardarMapeo">{{ t('Save as new version') }}</button>
                    <button class="btn" @click="mapeoAbierto = null">{{ t('Cancel') }}</button>
                  </div>
                </div>

                <!-- Vista previa de una entrada: nada se aplica hasta confirmar -->
                <div v-if="previa && previa.entidad === e.entidad && dir === 'ENTRADA'" class="int-previa">
                  <p><b>{{ tx(previa.archivo) }}</b> · {{ resumenTexto(previa.resumen) }}</p>
                  <ul v-if="previa.errores.length" class="lista-errores">
                    <li v-for="x in previa.errores.slice(0, 20)" :key="x.fila">{{ t('Row {0}', [x.fila]) }}: {{ x.mensajes.map(tx).join(' ') }}</li>
                  </ul>
                  <div class="fila-flex gap-2"><button class="btn btn-primario" :disabled="ocupado" @click="aplicar"><Icono nombre="check" :tam="14" />{{ t('Apply') }}</button><button class="btn" @click="previa = null">{{ t('Discard') }}</button></div>
                </div>
              </template>
            </div>

            <!-- Bitácora -->
            <div class="panel">
              <h3>{{ t('Run log') }}</h3>
              <p v-if="!bitacora.length" class="ayuda">{{ t('No runs yet.') }}</p>
              <div v-else class="tabla-envoltura">
                <table class="tabla">
                  <thead><tr><th>{{ t('Date') }}</th><th>{{ t('Data') }}</th><th>{{ t('File') }}</th><th>{{ t('Status') }}</th><th>{{ t('Result') }}</th></tr></thead>
                  <tbody>
                    <tr v-for="b in bitacora" :key="b.id">
                      <td>{{ fmtFechaHora(b.iniciada_en) }}</td>
                      <td>{{ tx(entidad(b.entidad)?.nombre || b.entidad) }} · {{ b.direccion === 'ENTRADA' ? t('In') : t('Out') }}</td>
                      <td>{{ tx(b.archivo || '—') }}</td>
                      <td><span class="etiqueta" :class="ESTADO[b.estado]?.[1]">{{ ESTADO[b.estado]?.[0] || b.estado }}</span></td>
                      <td class="apagado">{{ resumenTexto(b.resumen) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
          <p v-else-if="meta.integraciones.length" class="ayuda">{{ t('Choose an integration to see its mappings, exchange data and see its log.') }}</p>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.int-rejilla { display: grid; grid-template-columns: minmax(220px, 300px) minmax(0, 1fr); gap: 16px; align-items: start; }
.int-lista { display: flex; flex-direction: column; gap: 8px; }
.int-item { display: flex; flex-direction: column; gap: 2px; text-align: start; padding: 12px 14px; border: 1px solid var(--linea); border-radius: var(--radio-panel); background: var(--superficie); color: inherit; font: inherit; cursor: pointer; }
.int-item[aria-current='true'] { border-color: var(--acento); box-shadow: 0 0 0 1px var(--acento); }
.int-item-cabeza { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.int-item small { color: var(--tinta-3); }
.int-detalle { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.int-detalle h2, .int-detalle h3 { margin: 0; }
.int-mapeo, .int-previa { margin-top: 12px; display: flex; flex-direction: column; gap: 10px; }
.lista-errores { margin: 0; padding-inline-start: 18px; color: var(--peligro); font-size: 0.86rem; }
.entre { justify-content: space-between; align-items: flex-start; }
@media (max-width: 800px) { .int-rejilla { grid-template-columns: minmax(0, 1fr); } }
</style>
