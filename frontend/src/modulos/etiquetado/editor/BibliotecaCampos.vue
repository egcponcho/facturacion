<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref } from 'vue'
import Icono from '@/componentes/Icono.vue'
import { usarEditor } from './estado.js'

// Los campos con datos reales, por grupo, con su origen y un ejemplo. Clic
// agrega al centro; también se arrastran al lienzo. Arriba, los campos
// habituales de la familia del diseño (los obligatorios marcados). Los
// elementos (texto, códigos, imagen, formas) están en la barra del editor.
const props = defineProps({ grupos: { type: Object, default: () => ({}) }, familia: { type: Object, default: null } })
const ed = usarEditor()
const est = ed.estado
const q = ref('')

const normal = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
const filtrados = computed(() => {
  const n = normal(q.value)
  return ed.camposTodos.value.filter((c) => !c.oculto && (!n || normal(`${tx(c.etiqueta)} ${c.clave} ${c.origen}`).includes(n)))
})
const porGrupo = computed(() => {
  const r = {}
  for (const c of filtrados.value) (r[c.grupo] ||= []).push(c)
  return Object.entries(r)
})
const habituales = computed(() => {
  const lista = props.familia?.campos || []
  return lista.map((x) => ({ ...ed.camposTodos.value.find((c) => c.clave === x.campo), obligatorio: x.obligatorio })).filter((c) => c.clave)
})
const abiertos = ref(new Set(['articulo', 'oc', 'linea', 'manual']))
const alternarGrupo = (g) => (abiertos.value.has(g) ? abiertos.value.delete(g) : abiertos.value.add(g))

// Un campo se agrega como «campo»; las imágenes, como imagen leída del campo
function datosCampo(c) {
  if (c.tipo === 'imagen') return { tipo: 'imagen', extra: { fuente_imagen: 'campo', campo: c.clave, nombre: tx(c.etiqueta) } }
  return { tipo: 'campo', extra: { campo: c.clave, nombre: tx(c.etiqueta), ...(c.tipo === 'numero' ? { formato: { tipo: 'numero', decimales: 0, miles: true } } : {}) } }
}
function agregarCampo(c) {
  // Con un texto elegido, el campo se inserta en su contenido
  const u = ed.unico.value
  if (u && u.tipo === 'texto' && est.editable) {
    u.contenido = `${u.contenido || ''}{{${c.clave}}}`
    return
  }
  const { tipo, extra } = datosCampo(c)
  ed.agregar(tipo, extra)
}
function arrastrar(ev, tipo, extra) {
  ev.dataTransfer.setData('application/x-etiqueta', JSON.stringify({ tipo, extra }))
  ev.dataTransfer.effectAllowed = 'copy'
}
const ejemplo = (c) => (c.ejemplo == null || c.tipo === 'imagen' ? '' : String(c.ejemplo))
const textoEnSeleccion = computed(() => ed.unico.value?.tipo === 'texto')
</script>

<template>
  <div class="biblioteca">
    <section class="bib-campos">
      <p class="ayuda">{{ textoEnSeleccion ? t('A text is selected: the field is inserted in it.') : t('Click to add, or drag onto the label.') }}</p>
      <label class="buscador bib-buscar" @click.stop><Icono nombre="buscar" :tam="15" />
        <input v-model="q" type="search" :placeholder="t('Search field')" :aria-label="t('Search field')" /></label>

      <div v-if="habituales.length && !q" class="bib-grupo">
        <p class="bib-grupo-titulo fijo">{{ t('Usual for {0}', [tx(props.familia.nombre)]) }}</p>
        <button v-for="c in habituales" :key="`h${c.clave}`" type="button" class="bib-campo" :disabled="!est.editable" draggable="true"
                :title="c.origen" @click="agregarCampo(c)" @dragstart="arrastrar($event, datosCampo(c).tipo, datosCampo(c).extra)">
          <span class="bib-campo-nombre">{{ tx(c.etiqueta) }}<span v-if="c.obligatorio" class="req" :title="t('Required by the family')">*</span></span>
          <span class="bib-campo-ej">{{ ejemplo(c) }}</span>
        </button>
      </div>

      <div v-for="[g, lista] in porGrupo" :key="g" class="bib-grupo">
        <button type="button" class="bib-grupo-titulo" :aria-expanded="abiertos.has(g) || !!q" @click="alternarGrupo(g)">
          <Icono :nombre="abiertos.has(g) || q ? 'abajo' : 'derecha'" :tam="14" />{{ g === 'manual' ? t('Written when generating') : tx(props.grupos[g] || g) }}<span class="cuenta">{{ lista.length }}</span>
        </button>
        <template v-if="abiertos.has(g) || q">
          <button v-for="c in lista" :key="c.clave" type="button" class="bib-campo" :disabled="!est.editable" draggable="true"
                  :title="`${c.clave} · ${c.origen}`" @click="agregarCampo(c)" @dragstart="arrastrar($event, datosCampo(c).tipo, datosCampo(c).extra)">
            <span class="bib-campo-nombre">{{ tx(c.etiqueta) }}</span>
            <span class="bib-campo-ej">{{ ejemplo(c) }}</span>
          </button>
        </template>
      </div>
      <p v-if="!porGrupo.length" class="ayuda">{{ t('No field matches.') }}</p>
      <p class="ayuda mt-chico">{{ t('Need a value that is not in the system (lot, season, destination…)? Add it in Label → Fields written when generating.') }}</p>
    </section>
  </div>
</template>

<style scoped>
.biblioteca { display: flex; flex-direction: column; gap: 14px; }
.bib-campo:disabled { opacity: 0.55; cursor: default; }
.bib-campos .ayuda { margin: -4px 0 8px; font-size: 0.76rem; }
.bib-buscar { width: 100%; max-width: 100%; box-sizing: border-box; margin-bottom: 6px; }
.bib-buscar input { min-width: 0; width: 100%; }
.bib-grupo { display: flex; flex-direction: column; margin-bottom: 4px; }
.bib-grupo-titulo { display: flex; align-items: center; gap: 4px; padding: 6px 2px; border: 0; background: none; font-size: 0.8rem; font-weight: 600;
  color: var(--tinta); cursor: pointer; text-align: left; }
.bib-grupo-titulo.fijo { cursor: default; color: var(--acento-texto); margin: 0; }
.bib-grupo-titulo .cuenta { margin-left: auto; font-weight: 500; color: var(--tinta-3); font-size: 0.74rem; }
.bib-campo { display: flex; flex-direction: column; gap: 1px; padding: 5px 8px 5px 22px; border: 0; border-radius: 6px; background: none; text-align: left; cursor: grab; }
.bib-campo:hover:not(:disabled) { background: var(--acento-claro); }
.bib-campo-nombre { font-size: 0.8rem; color: var(--tinta); }
.bib-campo-ej { font-size: 0.72rem; color: var(--tinta-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.req { color: var(--error); margin-left: 2px; }
</style>
