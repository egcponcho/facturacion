<script setup>
// Asistente de una familia de producto, en el orden en que se arma:
// familia → capítulos → categorías → preguntas → reglas → probar y publicar.
// La familia nace en borrador: la ficha no la ofrece ni toca artículos reales
// hasta publicarla; mientras tanto se prueba con artículos de ejemplo.
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import EditorRegla from './EditorRegla.vue'
import { cargarContexto } from '@/modulos/clasificacion/useClasificacion'
import { fmtCode } from '@/modulos/clasificacion/formato.js'
import { avisar, errorApi } from '@/stores/ui'
import { confirmar } from '@/stores/confirmar'

const props = defineProps({ codigo: { type: String, default: '' } })
const emit = defineEmits(['codigo', 'listo', 'cerrar'])

const PASOS = [['familia', t('Family')], ['capitulos', t('Chapters')], ['categorias', t('Categories')], ['preguntas', t('Questions')],
  ['reglas', t('Rules')], ['probar', t('Test and publish')]]
const paso = ref(props.codigo ? 'capitulos' : 'familia')
const fam = ref(null)
const ocupado = ref(false)
const forma = ref({ codigo: '', nombre: '', descripcion: '', modo: 'AUTO' })
const capitulosOficiales = ref([])
const atributos = ref([])
const nuevoCap = ref('')
const nuevaCat = ref({ nombre: '', nombre_aduana: '' })
const nuevaPregunta = ref('')
const editor = ref(null)
const prueba = ref({ nombre: '', categoria: '', ficha: {} })
const resultado = ref(null)

const listo = computed(() => ({
  familia: !!fam.value, capitulos: !!fam.value?.capitulos.length, categorias: !!fam.value?.categorias.length,
  preguntas: !!fam.value?.preguntas.length, reglas: !!fam.value?.reglas.length, probar: !!fam.value?.publicada,
}))
const disponible = (k) => k === 'familia' || !!fam.value

async function cargar() {
  if (!props.codigo) return
  try {
    fam.value = await api.get(`/familias/${props.codigo}`)
    forma.value = { codigo: fam.value.codigo, nombre: fam.value.nombre, descripcion: fam.value.descripcion || '', modo: fam.value.modo }
  } catch (e) {
    errorApi(e)
  }
}
async function guardarFamilia() {
  ocupado.value = true
  try {
    const f = forma.value
    const cuerpo = { nombre: f.nombre, descripcion: f.descripcion || null, modo: f.modo }
    if (fam.value) await api.patch(`/aranceles/oficial/dominios/${fam.value.id}`, cuerpo)
    else {
      const d = await api.post('/aranceles/oficial/dominios', { ...cuerpo, codigo: f.codigo })
      emit('codigo', d.codigo)
    }
    avisar(t('Family saved.'))
    paso.value = 'capitulos'
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function capitulo(cap, datos) {
  try {
    await api.put(`/aranceles/oficial/dominios/${fam.value.id}/capitulos/${cap}`, datos)
    nuevoCap.value = ''
    await cargar()
  } catch (e) {
    errorApi(e)
  }
}
async function agregarCategoria() {
  ocupado.value = true
  try {
    await api.post('/aranceles/categorias', { nombre: nuevaCat.value.nombre, nombre_aduana: nuevaCat.value.nombre_aduana || null,
      dominio: fam.value.codigo, capitulos: fam.value.capitulos.map((c) => c.capitulo) })
    nuevaCat.value = { nombre: '', nombre_aduana: '' }
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function preguntar(atributoId, datos, ambitoId = null) {
  try {
    if (ambitoId) await api.patch(`/aranceles/atributos/${atributoId}/ambitos/${ambitoId}`, datos)
    else await api.post(`/aranceles/atributos/${atributoId}/ambitos`, { tipo_ambito: 'DOMAIN', codigo_ambito: fam.value.codigo, modo: 'SHOW', ...datos })
    nuevaPregunta.value = ''
    await cargar()
  } catch (e) {
    errorApi(e)
  }
}
const yaPregunta = computed(() => new Set((fam.value?.preguntas || []).map((p) => p.atributo_id)))
const opcionesPregunta = computed(() => atributos.value.filter((a) => !yaPregunta.value.has(a.id))
  .map((a) => ({ valor: String(a.id), texto: a.etiqueta, sub: a.codigo })))
const MODO = { SHOW: t('Ask'), REQUIRE: t('Required'), HIDE: t('Do not ask') }

async function probar(cambio = null) {
  ocupado.value = true
  try {
    const p = prueba.value
    if (cambio) p.ficha = { ...p.ficha, [cambio.campo]: cambio.valor }
    resultado.value = await api.post(`/familias/${fam.value.codigo}/probar`, { nombre: p.nombre, categoria: p.categoria || undefined,
      ficha: p.ficha, tocados: Object.keys(p.ficha) })
    if (!p.categoria && resultado.value.categoria?.codigo) p.categoria = resultado.value.categoria.codigo
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
const preguntasPrueba = computed(() => (resultado.value?.campos || []).filter((c) => c.opciones?.length && c.tipo_dato !== 'composition'))
async function publicar() {
  ocupado.value = true
  try {
    await api.post(`/familias/${fam.value.codigo}/publicar`)
    avisar(t('Family published: the product sheet offers it now.'))
    cargarContexto(true)
    await cargar()
    emit('listo')
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function despublicar() {
  if (!(await confirmar(t('Back to draft? The product sheet stops offering this family until you publish it again. Approved items keep their code.'), { boton: t('Back to draft') }))) return
  ocupado.value = true
  try {
    await api.post(`/familias/${fam.value.codigo}/despublicar`)
    avisar(t('The family is a draft again.'))
    cargarContexto(true)
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
const NIVEL = { high: t('High'), medium: t('Medium'), low: t('Low') }

onMounted(async () => {
  cargar()
  try {
    const [c, a] = await Promise.all([api.get('/aranceles/oficial/capitulos'), api.get('/aranceles/atributos')])
    capitulosOficiales.value = c.items.map((x) => ({ valor: x.capitulo, texto: `${x.capitulo} · ${x.titulo}`,
      sub: x.clasificacion && !x.solo_manual ? t('automatic') : t('by hand only') }))
    atributos.value = a.items.filter((x) => x.activo && !x.codigo.startsWith('comp.'))
  } catch (e) {
    errorApi(e)
  }
})
watch(() => props.codigo, cargar)
</script>

<template>
  <section class="asistente panel">
    <header class="cabeza">
      <div>
        <h2>{{ fam ? tx(fam.nombre) : t('New family') }}</h2>
        <p class="ayuda">
          <span v-if="fam" class="etiqueta ms-0" :class="fam.publicada ? 'ok' : 'aviso'">{{ tx(fam.publicada ? t('Published') : t('Draft')) }}</span>
          {{ tx(fam && !fam.publicada ? t('While it is a draft the product sheet does not offer it and no real item changes.') : '') }}
        </p>
      </div>
      <button type="button" class="btn btn-fantasma" @click="emit('cerrar')"><Icono nombre="cerrar" :tam="15" />{{ t('Close') }}</button>
    </header>

    <ol class="pasos-asistente">
      <li v-for="([k, l], i) in PASOS" :key="k">
        <button type="button" :aria-current="paso === k ? 'step' : undefined" :disabled="!disponible(k)" :class="{ hecho: listo[k] }" @click="paso = k">
          <span class="num"><Icono v-if="listo[k]" nombre="check" :tam="13" /><template v-else>{{ tx(i + 1) }}</template></span>{{ tx(l) }}
        </button>
      </li>
    </ol>

    <!-- 1. Familia -->
    <div v-if="paso === 'familia'" class="cuerpo">
      <p class="ayuda">{{ t('A family groups one kind of product (for example tableware, toys or electronics). Give it a short code and a name.') }}</p>
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Code') }}</span><input v-model="forma.codigo" class="entrada" maxlength="30" :disabled="!!fam" placeholder="TABLEWARE" /></label>
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="forma.nombre" class="entrada" maxlength="100" /></label>
        <label class="campo ancho"><span>{{ t('Description') }}</span><input v-model="forma.descripcion" class="entrada" maxlength="400" /></label>
        <label class="campo"><span>{{ t('How it is classified') }}</span>
          <select v-model="forma.modo" class="entrada"><option value="AUTO">{{ t('The engine suggests the code') }}</option><option value="MANUAL">{{ t('Always by hand') }}</option></select></label>
      </div>
      <div class="pie"><button class="btn btn-primario" :disabled="ocupado || !forma.nombre || !forma.codigo" @click="guardarFamilia">{{ t('Save and continue') }}<Icono nombre="derecha" :tam="15" /></button></div>
    </div>

    <p v-else-if="!fam" class="ayuda">{{ t('Loading…') }}</p>

    <!-- 2. Capítulos -->
    <div v-else-if="paso === 'capitulos'" class="cuerpo">
      <p class="ayuda">{{ t('The tariff chapters where its products fall. Main chapters give automatic candidates; secondary ones are only used when the data points there.') }}</p>
      <ul class="lista-filas">
        <li v-for="c in fam.capitulos" :key="c.capitulo">
          <b>{{ tx(c.capitulo) }}</b><span class="crece">{{ tx(c.titulo) }}<small v-if="!c.automatico" class="aviso-txt"> · {{ t('by hand only') }}</small></span>
          <select class="entrada corto" :value="c.relevancia" :aria-label="t('Relevance')" @change="capitulo(c.capitulo, { relevancia: $event.target.value, habilitado: true })">
            <option value="PRIMARY">{{ t('Main') }}</option><option value="SECONDARY">{{ t('Secondary') }}</option></select>
          <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="capitulo(c.capitulo, { quitar: true })"><Icono nombre="basura" :tam="15" /></button>
        </li>
        <li v-if="!fam.capitulos.length" class="vacio-fila">{{ t('No chapters yet.') }}</li>
      </ul>
      <div class="agregar">
        <SelectBusqueda v-model="nuevoCap" :opciones="capitulosOficiales.filter((c) => !fam.capitulos.some((x) => x.capitulo === c.valor))" :etiqueta="t('Chapter')" :placeholder="t('Add a chapter…')" class="crece" />
        <button class="btn" :disabled="!nuevoCap" @click="capitulo(nuevoCap, { relevancia: 'PRIMARY', habilitado: true })"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button>
      </div>
      <div class="pie"><button class="btn btn-primario" :disabled="!listo.capitulos" @click="paso = 'categorias'">{{ t('Continue') }}<Icono nombre="derecha" :tam="15" /></button></div>
    </div>

    <!-- 3. Categorías -->
    <div v-else-if="paso === 'categorias'" class="cuerpo">
      <p class="ayuda">{{ t('What the person chooses in “What is the product?”. Each category can have its own words to be recognized and its customs name (edit them later in Families and categories).') }}</p>
      <ul class="lista-filas">
        <li v-for="c in fam.categorias" :key="c.id"><b class="crece">{{ tx(c.nombre) }}</b><span class="ayuda">{{ tx(c.nombre_aduana || '—') }}</span></li>
        <li v-if="!fam.categorias.length" class="vacio-fila">{{ t('No categories yet.') }}</li>
      </ul>
      <form class="agregar" @submit.prevent="agregarCategoria">
        <input v-model="nuevaCat.nombre" class="entrada crece" maxlength="120" :placeholder="t('Category name, e.g. Mugs and cups')" :aria-label="t('Name')" />
        <input v-model="nuevaCat.nombre_aduana" class="entrada" maxlength="120" :placeholder="t('Customs name, e.g. TAZA')" :aria-label="t('Customs name')" />
        <button class="btn" type="submit" :disabled="ocupado || !nuevaCat.nombre"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button>
      </form>
      <div class="pie"><button class="btn btn-primario" :disabled="!listo.categorias" @click="paso = 'preguntas'">{{ t('Continue') }}<Icono nombre="derecha" :tam="15" /></button></div>
    </div>

    <!-- 4. Preguntas -->
    <div v-else-if="paso === 'preguntas'" class="cuerpo">
      <p class="ayuda">{{ t('What the sheet asks for products of this family. Reuse questions that already exist (material, use, who it is for…) or create new ones in Questions.') }}</p>
      <ul class="lista-filas">
        <li v-for="q in fam.preguntas" :key="q.ambito_id">
          <b class="crece">{{ tx(q.etiqueta) }} <small class="ayuda">{{ tx(q.tipo_ambito === 'CATEGORY' ? t('only in {0}', [q.codigo_ambito]) : '') }}</small></b>
          <select class="entrada corto" :value="q.modo" :aria-label="t('Mode')" @change="preguntar(q.atributo_id, { modo: $event.target.value }, q.ambito_id)">
            <option v-for="(l, k) in MODO" :key="k" :value="k">{{ tx(l) }}</option></select>
          <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="preguntar(q.atributo_id, { quitar: true }, q.ambito_id)"><Icono nombre="basura" :tam="15" /></button>
        </li>
        <li v-if="!fam.preguntas.length" class="vacio-fila">{{ t('No questions yet.') }}</li>
      </ul>
      <div class="agregar">
        <SelectBusqueda v-model="nuevaPregunta" :opciones="opcionesPregunta" :etiqueta="t('Question')" :placeholder="t('Add a question that already exists…')" class="crece" />
        <button class="btn" :disabled="!nuevaPregunta" @click="preguntar(Number(nuevaPregunta), {})"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button>
        <router-link class="btn btn-fantasma" :to="{ path: '/familias', query: { vista: 'atributos' } }">{{ t('Create a new question') }}</router-link>
      </div>
      <div class="pie"><button class="btn btn-primario" @click="paso = 'reglas'">{{ t('Continue') }}<Icono nombre="derecha" :tam="15" /></button></div>
    </div>

    <!-- 5. Reglas -->
    <div v-else-if="paso === 'reglas'" class="cuerpo">
      <p class="ayuda">{{ t('Which answers lead to which codes. Without rules the code comes only from the official text, with low confidence.') }}</p>
      <ul class="lista-filas">
        <li v-for="r in fam.reglas" :key="r.id" :class="{ apagada: !r.activo }">
          <b>{{ tx(r.codigo) }}</b><span class="crece">{{ tx(r.efecto || '') }}</span>
          <span v-if="r.accion?.codigos?.length" class="codigo-sac">{{ tx(r.accion.codigos.map(fmtCode).join(', ')) }}</span>
        </li>
        <li v-if="!fam.reglas.length" class="vacio-fila">{{ t('No rules yet.') }}</li>
      </ul>
      <div class="agregar">
        <button class="btn" @click="editor = { borrador: { tipo_ambito: 'DOMAIN', codigo_ambito: fam.codigo, tipo_regla: 'HARD_CONSTRAINT', prioridad: 800, accion: { tipo: 'RESTRICT', codigos: [] } } }">
          <Icono nombre="mas" :tam="14" />{{ t('New rule') }}</button>
      </div>
      <div class="pie"><button class="btn btn-primario" @click="paso = 'probar'">{{ t('Continue') }}<Icono nombre="derecha" :tam="15" /></button></div>
      <EditorRegla v-if="editor" :borrador="editor.borrador" @cerrar="editor = null" @guardada="editor = null; cargar()" />
    </div>

    <!-- 6. Probar y publicar -->
    <div v-else class="cuerpo">
      <p class="ayuda">{{ t('Write an example item as a supplier would and answer the questions: you see the code the engine would suggest and why. Nothing is saved.') }}</p>
      <form class="agregar" @submit.prevent="probar()">
        <input v-model="prueba.nombre" class="entrada crece" :placeholder="t('Item name, e.g. Ceramic coffee mug 350 ml')" :aria-label="t('Item name')" />
        <select v-model="prueba.categoria" class="entrada" :aria-label="t('Category')">
          <option value="">{{ t('Detect the category') }}</option>
          <option v-for="c in fam.categorias" :key="c.codigo" :value="c.codigo">{{ tx(c.nombre) }}</option>
        </select>
        <button class="btn" type="submit" :disabled="ocupado || (!prueba.nombre && !prueba.categoria)"><Icono nombre="varita" :tam="14" />{{ t('Test') }}</button>
      </form>
      <div v-if="resultado" class="resultado">
        <div class="sello">
          <span class="codigo-grande">{{ tx(resultado.hs6 ? fmtCode(resultado.hs6) : '——.——') }}</span>
          <span>{{ tx(resultado.categoria?.nombre || t('No category recognized')) }} · {{ t('Confidence: {0}', [NIVEL[resultado.confianza] || '—']) }}</span>
        </div>
        <div v-if="preguntasPrueba.length" class="preguntas">
          <label v-for="c in preguntasPrueba" :key="c.codigo" class="campo"><span>{{ tx(c.etiqueta) }}<b v-if="c.estado === 'preguntar'" class="aviso-txt"> *</b></span>
            <select class="entrada" :value="String(c.valor ?? '')" @change="probar({ campo: c.codigo, valor: $event.target.value || null })">
              <option value="">—</option>
              <option v-for="o in c.opciones" :key="o.codigo" :value="o.codigo" :disabled="o.bloqueada">{{ tx(o.etiqueta) }}</option>
            </select></label>
        </div>
        <ul class="razones"><li v-for="(x, i) in (resultado.razones || []).slice(0, 5)" :key="i">{{ tx(x) }}</li></ul>
        <ul v-if="resultado.revision_por?.length" class="razones aviso-txt"><li v-for="(x, i) in resultado.revision_por.slice(0, 3)" :key="i">{{ tx(x) }}</li></ul>
      </div>
      <div class="pie">
        <template v-if="fam.publicada"><span class="etiqueta ok">{{ t('Published') }}</span>
          <button class="btn btn-fantasma" :disabled="ocupado" @click="despublicar"><Icono nombre="editar" :tam="15" />{{ t('Back to draft') }}</button></template>
        <button v-else class="btn btn-primario" :disabled="ocupado || !listo.capitulos || !listo.categorias" @click="publicar"><Icono nombre="check" :tam="15" />{{ t('Publish family') }}</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.asistente { display: grid; gap: 14px; }
.cabeza { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.cabeza h2 { margin: 0 0 4px; }
.pasos-asistente { list-style: none; margin: 0; padding: 0; display: flex; gap: 6px; flex-wrap: wrap; }
.pasos-asistente button { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--linea); background: var(--superficie); border-radius: 99px; padding: 5px 12px 5px 6px; font: inherit; font-size: 0.86rem; color: var(--tinta-2); cursor: pointer; }
.pasos-asistente button[aria-current='step'] { border-color: var(--acento); background: var(--acento-claro); color: var(--acento-texto); font-weight: 650; }
.pasos-asistente button:disabled { opacity: 0.5; cursor: not-allowed; }
.pasos-asistente .num { width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center; background: var(--linea-suave); font-size: 0.75rem; font-weight: 700; }
.pasos-asistente .hecho .num { background: var(--ok-fondo); color: var(--ok); }
.cuerpo { display: grid; gap: 10px; }
.campo.ancho { grid-column: 1 / -1; }
.lista-filas { list-style: none; margin: 0; padding: 0; border: 1px solid var(--linea); border-radius: var(--radio); }
.lista-filas li { display: flex; gap: 10px; align-items: center; padding: 8px 10px; border-top: 1px solid var(--linea-suave); flex-wrap: wrap; }
.lista-filas li:first-child { border-top: 0; }
.lista-filas li.apagada { opacity: 0.55; }
.vacio-fila { color: var(--tinta-3); font-size: 0.88rem; }
.crece { flex: 1; min-width: 180px; }
.corto { width: auto; }
.agregar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pie { display: flex; justify-content: flex-end; gap: 8px; }
.aviso-txt { color: var(--aviso); }
.resultado { border: 1px solid var(--linea); border-radius: var(--radio); padding: 12px; display: grid; gap: 10px; background: var(--superficie-2); }
.sello { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.codigo-grande { font-size: 1.6rem; font-weight: 750; letter-spacing: 0.02em; }
.preguntas { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.razones { margin: 0; padding-inline-start: 18px; font-size: 0.86rem; display: grid; gap: 3px; }
</style>
