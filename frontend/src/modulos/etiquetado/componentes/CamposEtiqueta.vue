<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { MODALIDADES, textoModalidad } from '@/modulos/etiquetado/etiquetas.js'

// Campos lógicos: un dato de la etiqueta que puede salir de varias fuentes en
// orden (UPC: primero el de la línea de la OC, si no el del artículo). La
// política dice qué hacer si dos fuentes traen valores distintos. Se usan en
// los diseños como {{logico.clave}} y la generación guarda de qué fuente salió.
const lista = ref([])
const catalogo = ref([])
const cargando = ref(false)
const editable = computed(() => puede('etiquetas.campos'))
const POLITICAS = () => ({ PRIMERA: t('Use the first one'), ADVERTIR: t('Use the first one and warn'), BLOQUEAR: t('Do not generate until they match') })

async function cargar() {
  cargando.value = true
  try {
    lista.value = await api.get('/etiquetas/campos-logicos')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(() => {
  cargar()
  api.get('/etiquetas/campos').then((r) => (catalogo.value = r.campos.filter((c) => !['logico', 'etiqueta'].includes(c.grupo)))).catch(() => {})
})
const nombre = (clave) => catalogo.value.find((c) => c.clave === clave)?.etiqueta || clave
const columnas = computed(() => [
  { clave: 'campo', texto: t('Field in the designs'), fija: true, prioridad: 1 },
  { clave: 'etiqueta', texto: t('Name'), prioridad: 1 },
  { clave: 'fuentes', texto: t('Sources, in order'), prioridad: 1, textoValor: (v) => v.join(' → ') },
  { clave: 'politica', texto: t('If they disagree'), prioridad: 2, textoValor: (v) => tx(POLITICAS()[v]) },
  { clave: 'modalidades', texto: t('Data'), prioridad: 3, textoValor: (v) => (v.length ? v.map((m) => tx(textoModalidad(m))).join(', ') : t('All')) },
  { clave: 'en_uso', texto: t('Designs using it'), prioridad: 3 },
  { clave: 'activo', texto: t('Active'), prioridad: 3, opciones: [[true, t('Yes')], [false, t('No')]] },
])

const edicion = ref(null)
const nuevaFuente = ref('')
function abrir(c) {
  edicion.value = c ? { ...c, fuentes: [...c.fuentes], modalidades: [...c.modalidades] }
    : { clave: '', etiqueta: '', descripcion: '', tipo: 'texto', fuentes: [], politica: 'ADVERTIR', modalidades: [], activo: true }
}
function agregarFuente() {
  if (nuevaFuente.value && !edicion.value.fuentes.includes(nuevaFuente.value)) edicion.value.fuentes.push(nuevaFuente.value)
  nuevaFuente.value = ''
}
function mover(i, d) {
  const f = edicion.value.fuentes
  ;[f[i], f[i + d]] = [f[i + d], f[i]]
}
async function guardar() {
  const e = edicion.value
  const cuerpo = { clave: e.clave, etiqueta: e.etiqueta, descripcion: e.descripcion, tipo: e.tipo, fuentes: e.fuentes, politica: e.politica,
    modalidades: e.modalidades, activo: e.activo }
  try {
    if (e.id) await api.patch(`/etiquetas/campos-logicos/${e.id}`, { ...cuerpo, version: e.version })
    else await api.post('/etiquetas/campos-logicos', cuerpo)
    avisar(t('Logical field saved.'))
    edicion.value = null
    cargar()
  } catch (err) {
    errorApi(err)
  }
}
async function quitar(c) {
  try {
    await api.del(`/etiquetas/campos-logicos/${c.id}`)
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <TablaDatos tabla="etiquetas_campos_logicos" :columnas="columnas" :filas="lista" :cargando="cargando" :etiqueta="t('Logical fields')">
    <template #filtros>
      <button v-if="editable" type="button" class="btn btn-primario separar" @click="abrir(null)"><Icono nombre="mas" />{{ t('New logical field') }}</button>
    </template>
    <template #celda-campo="{ fila: c }"><code v-text="`{{${c.campo}}}`"></code></template>
    <template #celda-etiqueta="{ fila: c }">
      <button v-if="editable" type="button" class="btn-texto" @click="abrir(c)">{{ c.etiqueta }}</button><span v-else>{{ c.etiqueta }}</span>
    </template>
    <template #celda-fuentes="{ fila: c }"><span v-for="(f, i) in c.fuentes" :key="f" class="fuente">{{ i + 1 }}. {{ tx(nombre(f)) }}</span></template>
    <template #acciones="{ fila: c }">
      <button v-if="editable" type="button" class="btn-icono" :aria-label="t('Remove')" :title="c.en_uso ? t('Designs use it: deactivate it instead') : t('Remove')"
              :disabled="!!c.en_uso" @click="quitar(c)"><Icono nombre="basura" :tam="15" /></button>
    </template>
    <template #vacio>{{ t('No logical fields yet. Create one when a datum can come from several places (PO line, item, product…).') }}</template>
  </TablaDatos>

  <Modal v-if="edicion" :titulo="edicion.id ? t('Edit logical field') : t('New logical field')" ancho="560px" @cerrar="edicion = null">
    <form id="form-campo-logico" class="form-cl" @submit.prevent="guardar">
      <div class="fila-cl">
        <label class="campo"><span class="req">{{ t('Key') }}</span>
          <input v-model="edicion.clave" required pattern="[a-z][a-z0-9_]{0,39}" :disabled="!!edicion.en_uso" placeholder="upc" /></label>
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="edicion.etiqueta" required maxlength="80" /></label>
      </div>
      <label class="campo"><span>{{ t('Description') }}</span><input v-model="edicion.descripcion" maxlength="300" /></label>
      <div class="fila-cl">
        <label class="campo"><span>{{ t('Type') }}</span>
          <Seleccion v-model="edicion.tipo"><option value="texto">{{ t('Text') }}</option><option value="numero">{{ t('Number') }}</option>
            <option value="fecha">{{ t('Date') }}</option></Seleccion></label>
        <label class="campo"><span>{{ t('If the sources disagree') }}</span>
          <Seleccion v-model="edicion.politica"><option v-for="(txt, k) in POLITICAS()" :key="k" :value="k">{{ tx(txt) }}</option></Seleccion></label>
      </div>
      <fieldset class="grupo-cl"><legend class="req">{{ t('Sources, in order of precedence') }}</legend>
        <ol class="fuentes">
          <li v-for="(f, i) in edicion.fuentes" :key="f">
            <span>{{ tx(nombre(f)) }} <code>{{ f }}</code></span>
            <button type="button" class="btn-icono" :disabled="i === 0" :aria-label="t('Move up')" @click="mover(i, -1)"><Icono nombre="arriba" :tam="14" /></button>
            <button type="button" class="btn-icono" :disabled="i === edicion.fuentes.length - 1" :aria-label="t('Move down')" @click="mover(i, 1)"><Icono nombre="abajo" :tam="14" /></button>
            <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="edicion.fuentes.splice(i, 1)"><Icono nombre="cerrar" :tam="14" /></button>
          </li>
        </ol>
        <div class="fila-cl">
          <Seleccion v-model="nuevaFuente" :aria-label="t('Add a source')"><option value="">{{ t('Add a source…') }}</option>
            <option v-for="c in catalogo.filter((x) => !edicion.fuentes.includes(x.clave))" :key="c.clave" :value="c.clave">{{ tx(c.etiqueta) }} ({{ c.clave }})</option></Seleccion>
          <button type="button" class="btn" :disabled="!nuevaFuente" @click="agregarFuente">{{ t('Add') }}</button>
        </div>
      </fieldset>
      <fieldset class="grupo-cl"><legend>{{ t('Available in (empty: all)') }}</legend>
        <label v-for="[m, txt] in MODALIDADES()" :key="m" class="check"><input v-model="edicion.modalidades" type="checkbox" :value="m" /> {{ tx(txt) }}</label>
      </fieldset>
      <label class="check"><input v-model="edicion.activo" type="checkbox" /> {{ t('Active') }}</label>
    </form>
    <template #pie>
      <button class="btn separar" type="button" @click="edicion = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-campo-logico" :disabled="!edicion.fuentes.length">{{ t('Save') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.form-cl { display: flex; flex-direction: column; gap: 12px; }
.fila-cl { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
.fila-cl > .campo { flex: 1 1 180px; }
.grupo-cl { border: 1px solid var(--linea); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.fuentes { margin: 0; padding-inline-start: 20px; display: flex; flex-direction: column; gap: 4px; }
.fuentes li > span { display: inline-block; min-width: 60%; }
.fuente { display: inline-block; margin-inline-end: 8px; font-size: 0.85rem; }
code { font-size: 0.8rem; color: var(--tinta-3); }
</style>
