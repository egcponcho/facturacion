<script setup>
import { t, tx } from '../../i18n/index.js'
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import Icono from '../Icono.vue'
import SelectBusqueda from '../SelectBusqueda.vue'
import Interruptor from '../Interruptor.vue'
import Modal from '../Modal.vue'
import { puede } from '../../stores/sesion'
import { avisar, errorApi } from '../../stores/ui'
import { cargarContexto } from '../../clasificacion/useClasificacion'
import CampoComportamiento from './comportamiento/CampoComportamiento.vue'

// Dominios de clasificación (químicos, materias primas, calzado, ropa,
// accesorios…) y los capítulos con que se relacionan. PRIMARY genera
// candidatos automáticos; SECONDARY queda disponible si los datos lo justifican.
const edita = puede('clasificacion.configurar')
const dominios = ref([])
const capitulos = ref([])
const nuevo = ref({})

const categorias = ref([])
// Preguntas del catálogo (para patrones y plantilla): se leen al abrir una categoría
const atributos = ref([])
const nuevaCat = ref({})
const modal = ref(null)
async function cargar() {
  try {
    categorias.value = await api.get('/aranceles/categorias', { todas: true })
    dominios.value = await api.get('/aranceles/oficial/dominios')
  } catch (e) {
    errorApi(e)
  }
}
onMounted(async () => {
  cargar()
  const r = await api.get('/aranceles/oficial/capitulos').catch(() => ({ items: [] }))
  capitulos.value = r.items.map((c) => ({ valor: c.capitulo, texto: `${c.capitulo} · ${c.titulo}`, sub: c.seccion ? t('Section {0}', [c.seccion]) : '' }))
})
async function guardar(d, cap, datos) {
  try {
    await api.put(`/aranceles/oficial/dominios/${d.id}/capitulos/${cap}`, datos)
    await cargar()
  } catch (e) {
    errorApi(e)
  }
}
// ---- Dominios y categorías (configuración: agregar un dominio no requiere programar)
const catsDe = (d) => categorias.value.filter((c) => c.dominio === d.codigo)
async function guardarDominio() {
  const m = modal.value
  try {
    const cuerpo = { nombre: m.nombre, descripcion: m.descripcion || null, modo: m.modo, activo: m.activo }
    if (m.id) await api.patch(`/aranceles/oficial/dominios/${m.id}`, cuerpo)
    else await api.post('/aranceles/oficial/dominios', { ...cuerpo, codigo: m.codigo })
    modal.value = null
    avisar(t('Family saved.'))
    cargar()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  }
}
async function activarDominio(d, v) {
  try {
    await api.patch(`/aranceles/oficial/dominios/${d.id}`, { activo: v })
    cargar()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  }
}
async function agregarCategoria(d) {
  const nombre = (nuevaCat.value[d.id] || '').trim()
  if (!nombre) return
  try {
    await api.post('/aranceles/categorias', { nombre, dominio: d.codigo, grupo: d.nombre })
    nuevaCat.value[d.id] = ''
    cargar()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  }
}
// Una categoría completa: cómo se reconoce en el nombre, sus capítulos y su
// descripción aduanera (el servidor valida patrones, capítulos y plantilla)
const cat = ref(null)
const catMal = ref({})
const sinDominio = () => categorias.value.filter((c) => !c.dominio)
async function abrirCategoria(c) {
  catMal.value = {}
  cat.value = { ...c, capitulosTxt: (c.capitulos || []).join(', ') }
  if (!atributos.value.length) atributos.value = (await api.get('/aranceles/atributos').catch(() => ({ items: [] }))).items
}
async function guardarCategoria() {
  const c = cat.value
  const cuerpo = { nombre: c.nombre, nombre_corto: c.nombre_corto || null, nombre_aduana: c.nombre_aduana || null, dominio: c.dominio || null,
    alias: c.alias || null, terminos: c.terminos || null, activo: c.activo, patrones: (c.patrones || []).filter((x) => x.re || x.cuando?.length || x.defecto), plantilla_aduana: c.plantilla_aduana || {},
    capitulos: c.capitulosTxt.split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean) }
  try {
    await api.patch(`/aranceles/categorias/${c.id}`, cuerpo)
    cat.value = null
    avisar(t('Category saved.'))
    cargar()
    cargarContexto(true)
  } catch (e) {
    errorApi(e)
  }
}
const EJ_PATRONES = '[\n  {"re": "\\\\b(mugs?|tazas?)\\\\b", "prioridad": 10}\n]'
const EJ_PLANTILLA = '{\n  "nombre": "TAZA",\n  "material": "DE {clase}",\n  "clase": ["material"],\n  "comercial": "TAZA"\n}'
function agregar(d) {
  const cap = nuevo.value[d.id]
  if (!cap) return
  guardar(d, cap, { relevancia: 'SECONDARY', habilitado: true })
  nuevo.value[d.id] = ''
}
</script>

<template>
  <section class="dominios">
    <div class="cab">
      <p class="ayuda">{{ t('The commercial domain only helps choose questions and candidates. The legal result always comes from the tariff text, legal notes and rules; a domain never forces or excludes a chapter.') }}</p>
      <button v-if="edita" class="btn btn-primario" @click="modal = { id: null, codigo: '', nombre: '', descripcion: '', modo: 'AUTO', activo: true }"><Icono nombre="mas" />{{ t('New family') }}</button>
    </div>
    <article v-for="d in dominios" :key="d.id" class="panel dominio" :class="{ apagado: !d.activo }">
      <header>
        <div><h3>{{ tx(d.nombre) }} <span class="codigo ayuda">{{ tx(d.codigo) }}</span>
          <span v-if="d.estado === 'BORRADOR'" class="etiqueta acento">{{ t('Draft') }}</span></h3><p class="ayuda">{{ tx(d.descripcion) }}</p></div>
        <div class="dom-acc">
          <span class="etiqueta">{{ tx(d.modo === 'AUTO' ? t('Automatic') : t('Manual')) }}</span>
          <Interruptor :model-value="d.activo" :deshabilitado="!edita" :etiqueta="t('Active')" @update:model-value="activarDominio(d, $event)" />
          <button v-if="edita" type="button" class="btn-icono" :aria-label="t('Edit')" @click="modal = { ...d }"><Icono nombre="editar" :tam="15" /></button>
        </div>
      </header>
      <div class="cats">
        <span class="lbl">{{ t('Product categories') }}</span>
        <button v-for="c in catsDe(d)" :key="c.id" type="button" class="cat-chip" :class="{ off: !c.activo }"
                :title="t('Open the category')" @click="abrirCategoria(c)">
          {{ tx(c.nombre) }}</button>
        <form v-if="edita" class="cat-nueva" @submit.prevent="agregarCategoria(d)">
          <input v-model="nuevaCat[d.id]" class="entrada" maxlength="120" :placeholder="t('New category…')" :aria-label="t('New category')" />
        </form>
      </div>
      <div class="caps">
        <span v-for="c in d.capitulos" :key="c.id" class="cap" :class="[c.relevancia === 'PRIMARY' ? 'primario' : 'secundario', { off: !c.capitulo_habilitado }]"
              :title="tx(`${c.titulo}${c.capitulo_habilitado ? '' : ' · ' + t('chapter not enabled')}`)">
          <b>{{ tx(c.capitulo) }}</b>
          <button v-if="edita" type="button" class="mini" :title="tx(c.relevancia === 'PRIMARY' ? t('Make secondary') : t('Make primary'))"
                  @click="guardar(d, c.capitulo, { relevancia: c.relevancia === 'PRIMARY' ? 'SECONDARY' : 'PRIMARY' })">{{ c.relevancia === 'PRIMARY' ? 'P' : 'S' }}</button>
          <button v-if="edita" type="button" class="mini" :aria-label="t('Remove chapter {0}', [c.capitulo])" @click="guardar(d, c.capitulo, { quitar: true })">×</button>
        </span>
      </div>
      <div v-if="edita" class="agregar">
        <SelectBusqueda v-model="nuevo[d.id]" :opciones="capitulos.filter((c) => !d.capitulos.some((x) => x.capitulo === c.valor))" :placeholder="t('Add a chapter…')" :etiqueta="t('Chapter')" />
        <button class="btn btn-chico" :disabled="!nuevo[d.id]" @click="agregar(d)"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button>
      </div>
    </article>
    <article v-if="sinDominio().length" class="panel dominio">
      <header><div><h3>{{ t('Outside a family') }}</h3><p class="ayuda">{{ t('Categories without a domain: the product sheet asks the generic questions (technical description and composition).') }}</p></div></header>
      <div class="cats">
        <button v-for="c in sinDominio()" :key="c.id" type="button" class="cat-chip" :class="{ off: !c.activo }" @click="abrirCategoria(c)">{{ tx(c.nombre) }}</button>
      </div>
    </article>
    <Modal v-if="cat" :titulo="t('Category {0}', [cat.codigo])" ancho="760px" @cerrar="cat = null">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="cat.nombre" class="entrada" maxlength="120" :disabled="!edita" /></label>
        <label class="campo"><span>{{ t('Short name') }}</span><input v-model="cat.nombre_corto" class="entrada" maxlength="80" :disabled="!edita" /></label>
        <label class="campo"><span>{{ t('Customs name') }}</span><input v-model="cat.nombre_aduana" class="entrada" maxlength="120" :disabled="!edita" :placeholder="t('e.g. TAZA')" /></label>
        <label class="campo"><span>{{ t('Product family') }}</span>
          <SelectBusqueda v-model="cat.dominio" :opciones="dominios.map((d) => ({ valor: d.codigo, texto: d.nombre }))" :vacio="t('Outside a family')" :deshabilitado="!edita" :etiqueta="t('Product family')" /></label>
        <label class="campo"><span>{{ t('Compatible chapters') }}</span><input v-model="cat.capitulosTxt" class="entrada" :disabled="!edita" :placeholder="t('e.g. 69, 70')" /></label>
        <label class="campo"><span>{{ t('Other names (aliases)') }}</span><input v-model="cat.alias" class="entrada" maxlength="400" :disabled="!edita" /></label>
        <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Words of the official text (only order candidates)') }}</span><input v-model="cat.terminos" class="entrada" maxlength="400" :disabled="!edita" /></label>
        <label class="check"><input v-model="cat.activo" type="checkbox" :disabled="!edita" /><span>{{ t('Active') }}</span></label>
      </div>
      <CampoComportamiento v-model="cat.patrones" tipo="patrones" :atributos="atributos" :etiqueta="t('How it is recognized in the product name')" :ejemplo="EJ_PATRONES"
                           :deshabilitado="!edita" :ayuda="t('Words that mark the category. The lowest priority that matches wins.')" @valido="catMal.patrones = !$event" />
      <CampoComportamiento v-model="cat.plantilla_aduana" tipo="plantilla" :atributos="atributos" :etiqueta="t('Customs description template')" :ejemplo="EJ_PLANTILLA"
                           :deshabilitado="!edita" @valido="catMal.plantilla = !$event" />
      <template #pie>
        <button class="btn" @click="cat = null">{{ t('Cancel') }}</button>
        <button v-if="edita" class="btn btn-primario" :disabled="!cat.nombre || Object.values(catMal).some(Boolean)" @click="guardarCategoria">{{ t('Save') }}</button>
      </template>
    </Modal>
    <Modal v-if="modal" :titulo="modal.id ? t('Family {0}', [modal.codigo]) : t('New family')" @cerrar="modal = null">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Code') }}</span><input v-model="modal.codigo" class="entrada" maxlength="30" :disabled="!!modal.id" placeholder="ELECTRONICS" /></label>
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="modal.nombre" class="entrada" maxlength="100" /></label>
        <label class="campo" style="grid-column: 1 / -1"><span>{{ t('Description') }}</span><input v-model="modal.descripcion" class="entrada" maxlength="400" /></label>
        <label class="campo"><span>{{ t('Mode') }}</span><select v-model="modal.modo" class="entrada"><option value="AUTO">{{ t('Automatic') }}</option><option value="MANUAL">{{ t('Manual') }}</option></select></label>
        <label class="check"><input v-model="modal.activo" type="checkbox" /><span>{{ t('Active') }}</span></label>
      </div>
      <p class="ayuda">{{ t('Next: add its chapters and categories here, then its questions and its rules. The product sheet offers it right away.') }}</p>
      <template #pie>
        <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
        <button class="btn btn-primario" :disabled="!modal.nombre || !modal.codigo" @click="guardarDominio">{{ t('Save') }}</button>
      </template>
    </Modal>
    <p class="ayuda leyenda"><span class="cap primario"><b>P</b></span> {{ t('Primary: automatic candidates') }} · <span class="cap secundario"><b>S</b></span> {{ t('Secondary: available when the data justifies it') }} · <span class="cap off"><b>—</b></span> {{ t('chapter not enabled') }}</p>
  </section>
</template>

<style scoped>
.dominios { display: grid; gap: 12px; }
.dominio header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.dominio h3 { margin: 0; font-size: 1.05rem; }
.dominio p { margin: 2px 0 0; }
.caps { display: flex; flex-wrap: wrap; gap: 5px; margin: 10px 0; }
.cap { display: inline-flex; align-items: center; gap: 3px; padding: 2px 6px; border-radius: 8px; font-size: 0.82rem; border: 1px solid var(--linea); }
.cap.primario { background: var(--acento-claro); color: var(--acento-texto); border-color: transparent; }
.cap.secundario { background: var(--superficie-2); }
.cap.off { opacity: 0.5; text-decoration: line-through; }
.mini { border: 0; background: none; cursor: pointer; color: inherit; font-size: 0.72rem; padding: 0 2px; opacity: 0.7; }
.mini:hover { opacity: 1; }
.cab { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.dom-acc { display: flex; gap: 8px; align-items: center; }
.cats { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; margin: 8px 0; }
.cats .lbl { font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--tinta-3); font-weight: 650; margin-inline-end: 4px; }
.cat-chip { border: 1px solid var(--linea); background: var(--superficie); border-radius: 99px; padding: 3px 10px; font: inherit; font-size: 0.8rem; cursor: pointer; color: inherit; }
.cat-chip small { color: var(--tinta-3); }
.cat-chip.off { opacity: 0.5; text-decoration: line-through; }
.cat-nueva .entrada { width: 180px; padding: 3px 8px; font-size: 0.82rem; }
.agregar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.agregar :deep(.sb) { min-width: 260px; }
.leyenda { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
</style>
