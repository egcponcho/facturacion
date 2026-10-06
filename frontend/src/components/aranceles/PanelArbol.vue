<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../../api'
import Icono from '../Icono.vue'
import { errorApi } from '../../stores/ui'
import { fmtNum } from '../../utils'

// Árbol arancelario oficial (versión SAC vigente): capítulo → partida →
// subpartida → inciso, con carga perezosa de cada rama, búsqueda por código o
// palabras y el detalle del nodo (texto oficial, DAI, notas y códigos nacionales).
const resumen = ref(null)
const raiz = ref([])
const hijos = reactive({}) // id → lista
const abiertos = reactive({})
const cargando = reactive({})
const q = ref('')
const resultados = ref(null)
const elegido = ref(null)
const detalle = ref(null)

onMounted(async () => {
  try {
    const [r, a] = await Promise.all([api.get('/aranceles/arbol/resumen'), api.get('/aranceles/arbol')])
    resumen.value = r
    raiz.value = a.items
  } catch (e) {
    errorApi(e)
  }
})
async function alternar(n) {
  if (!n.hijos) return elegir(n)
  abiertos[n.id] = !abiertos[n.id]
  if (abiertos[n.id] && !hijos[n.id]) {
    cargando[n.id] = true
    try {
      hijos[n.id] = (await api.get('/aranceles/arbol', { padre_id: n.id })).items
    } catch (e) {
      errorApi(e)
    } finally {
      cargando[n.id] = false
    }
  }
}
async function elegir(n) {
  elegido.value = n.id
  try {
    detalle.value = await api.get(`/aranceles/arbol/${n.id}`)
  } catch (e) {
    errorApi(e)
  }
}
let temporizador = null
function buscar() {
  clearTimeout(temporizador)
  if (!q.value.trim()) return (resultados.value = null)
  temporizador = setTimeout(async () => {
    try {
      resultados.value = await api.get('/aranceles/arbol', { q: q.value })
    } catch (e) {
      errorApi(e)
    }
  }, 280)
}
// Filas visibles del árbol (aplanadas con su profundidad)
const filas = computed(() => {
  const out = []
  const visitar = (lista, nivel) => {
    for (const n of lista) {
      out.push({ n, nivel })
      if (abiertos[n.id] && hijos[n.id]) visitar(hijos[n.id], nivel + 1)
    }
  }
  visitar(raiz.value, 0)
  return out
})
const paisesConDatos = computed(() => (detalle.value?.paises || []).filter((p) => p.codigos.length || p.impuestos?.length || p.regulaciones?.length))
const AMBITO = { seccion: t('Section note'), capitulo: t('Chapter note'), subpartida: t('Subheading note'), complementaria: t('Complementary note'), explicativa: t('Explanatory summary') }
const NIVEL = { CAPITULO: t('Chapter'), PARTIDA: t('Heading'), SUBPARTIDA: t('Subheading'), INCISO: t('Tariff line') }
</script>

<template>
  <div class="arbol-arancel">
    <section class="panel arbol">
      <div class="cabeza">
        <h3><Icono nombre="lista" :tam="16" />{{ t('Tariff tree (SAC)') }}</h3>
        <span v-if="resumen" class="ayuda" :title="t('Checksum {0}', [resumen.checksum || '—'])">{{ tx(resumen.version) }}</span>
      </div>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search code or description…')" :aria-label="t('Search')" @input="buscar" /></label>
      <p v-if="resumen" class="ayuda conteo">{{ t('{0} chapters · {1} headings · {2} subheadings · {3} tariff lines', [fmtNum(resumen.niveles.CAPITULO || 0), fmtNum(resumen.niveles.PARTIDA || 0), fmtNum(resumen.niveles.SUBPARTIDA || 0), fmtNum(resumen.niveles.INCISO || 0)]) }}</p>
      <ul v-if="resultados" class="lista-arbol" role="list">
        <li v-if="!resultados.items.length" class="ayuda">{{ t('No results.') }}</li>
        <li v-for="n in resultados.items" :key="n.id">
          <button type="button" class="nodo" :class="{ elegido: elegido === n.id }" @click="elegir(n)">
            <span class="cod">{{ tx(n.codigo) }}</span><span class="txt">{{ tx(n.texto) }}<small v-if="n.ruta.length">{{ tx(n.ruta.join(' › ')) }}</small></span>
          </button>
        </li>
        <li v-if="resultados.total > resultados.items.length" class="ayuda">{{ t('Showing {0} of {1}. Refine the search.', [resultados.items.length, fmtNum(resultados.total)]) }}</li>
      </ul>
      <ul v-else class="lista-arbol" role="tree">
        <li v-for="{ n, nivel } in filas" :key="n.id" role="treeitem" :aria-expanded="n.hijos ? !!abiertos[n.id] : undefined" :style="{ '--nivel': nivel }">
          <button type="button" class="nodo" :class="{ elegido: elegido === n.id, off: n.capitulo_habilitado === false }" @click="alternar(n); if (n.hijos) elegir(n)">
            <span class="flecha" :class="{ abierta: abiertos[n.id], vacia: !n.hijos }">›</span>
            <span class="cod">{{ tx(n.codigo) }}</span><span class="txt">{{ tx(n.texto) }}</span>
            <span v-if="cargando[n.id]" class="ayuda">…</span>
          </button>
        </li>
      </ul>
    </section>

    <section class="panel detalle">
      <template v-if="detalle">
        <nav class="ruta" :aria-label="t('Path')">
          <button v-for="a in detalle.ruta" :key="a.id" type="button" class="enlace" @click="elegir(a)">{{ tx(a.codigo) }}</button>
          <span>{{ tx(detalle.codigo) }}</span>
        </nav>
        <div class="titulo">
          <span class="etiqueta acento">{{ tx(NIVEL[detalle.nivel] || detalle.nivel) }}</span>
          <h3>{{ tx(detalle.codigo) }}</h3>
          <span v-if="detalle.dai !== null && detalle.dai !== undefined" class="dai">{{ t('DAI {0}%', [detalle.dai]) }}</span>
        </div>
        <p class="texto">{{ tx(detalle.descripcion) }}</p>
        <div class="meta">
          <span v-if="detalle.capitulo" :class="detalle.capitulo.clasificacion ? 'etiqueta ok' : 'etiqueta'">
            {{ tx(detalle.capitulo.clasificacion ? (detalle.capitulo.solo_manual ? t('Chapter: manual only') : t('Chapter enabled')) : t('Chapter not enabled')) }}</span>
          <span v-if="detalle.version" class="ayuda">{{ t('Version {0} · {1}', [detalle.version.codigo, detalle.version.fuente]) }}</span>
        </div>
        <template v-if="detalle.hijos_lista.length">
          <h4>{{ t('Contains') }}</h4>
          <ul class="hijos">
            <li v-for="h in detalle.hijos_lista" :key="h.id"><button type="button" class="nodo" @click="elegir(h)"><span class="cod">{{ tx(h.codigo) }}</span><span class="txt">{{ tx(h.texto) }}</span><span v-if="h.dai !== null" class="ayuda">{{ t('DAI {0}%', [h.dai]) }}</span></button></li>
          </ul>
        </template>
        <template v-if="paisesConDatos.length">
          <h4>{{ t('By country') }}</h4>
          <div class="paises">
            <div v-for="p in paisesConDatos" :key="p.iso" class="pais">
              <b>{{ tx(p.iso) }}</b>
              <div class="pais-datos">
                <div v-if="p.codigos.length" class="fila-chips">
                  <span v-for="c in p.codigos.slice(0, 8)" :key="c.codigo" class="codigo-sac" :title="tx(c.descripcion || '')">{{ tx(c.codigo) }}<small v-if="c.dai"> · {{ tx(c.dai) }}%</small></span>
                  <span v-if="p.codigos.length > 8" class="ayuda">{{ t('+{0} more', [p.codigos.length - 8]) }}</span>
                </div>
                <div v-if="p.impuestos.length || p.regulaciones.length" class="fila-chips">
                  <span v-for="i in p.impuestos" :key="i.id" class="etiqueta" :title="tx(i.base_legal || '')">{{ tx(i.tipo) }} {{ i.tasa != null ? `${fmtNum(i.tasa)}%` : '' }}</span>
                  <span v-for="r in p.regulaciones" :key="r.id" class="etiqueta aviso" :title="tx([r.autoridad, r.base_legal].filter(Boolean).join(' · '))"><Icono nombre="candado" :tam="12" />{{ tx(r.nombre) }}</span>
                </div>
              </div>
            </div>
          </div>
        </template>
        <template v-if="detalle.notas.length">
          <h4>{{ t('Legal notes') }}</h4>
          <details v-for="nota in detalle.notas.slice(0, 12)" :key="nota.id" class="nota-legal">
            <summary>{{ tx(AMBITO[nota.ambito] || nota.ambito) }} {{ tx(nota.codigo) }} · {{ tx(nota.numero) }}
              <span class="etiqueta" :class="nota.oficial ? 'ok' : 'aviso'">{{ nota.oficial ? t('Official text') : t('Guidance, not legal text') }}</span></summary>
            <p>{{ tx(nota.texto) }}</p>
          </details>
        </template>
      </template>
      <p v-else class="ayuda vacio-det"><Icono nombre="info" :tam="18" />{{ t('Choose a node of the tree to see its official text, duty, legal notes and national codes.') }}</p>
    </section>
  </div>
</template>

<style scoped>
.arbol-arancel { display: grid; grid-template-columns: minmax(300px, 420px) 1fr; gap: 14px; align-items: start; }
.cabeza { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.cabeza h3 { margin: 0; font-size: 1rem; display: flex; gap: 6px; align-items: center; }
.arbol .buscador { width: 100%; max-width: none; }
.conteo { margin: 6px 0; font-size: 0.78rem; }
.lista-arbol { list-style: none; margin: 0; padding: 0; max-height: 64vh; overflow-y: auto; }
.lista-arbol li { padding-inline-start: calc(var(--nivel, 0) * 16px); }
.nodo { display: flex; gap: 6px; align-items: baseline; width: 100%; text-align: start; border: 0; background: none; padding: 5px 6px; border-radius: 8px; cursor: pointer; color: inherit; font: inherit; font-size: 0.86rem; }
.nodo:hover { background: var(--superficie-2); }
.nodo.elegido { background: var(--acento-claro); color: var(--acento-texto); }
.nodo.off .cod { opacity: 0.6; }
.flecha { width: 12px; display: inline-block; transition: transform 0.12s; color: var(--tinta-3); }
.flecha.abierta { transform: rotate(90deg); }
.flecha.vacia { visibility: hidden; }
.cod { font-variant-numeric: tabular-nums; font-weight: 650; white-space: nowrap; }
.txt { color: var(--tinta-2); overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.txt small { display: block; color: var(--tinta-3); }
.detalle { min-height: 300px; }
.ruta { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; font-size: 0.82rem; color: var(--tinta-3); }
.ruta > * + *::before { content: '›'; margin-inline-end: 4px; color: var(--tinta-3); }
.titulo { display: flex; gap: 10px; align-items: center; margin-top: 6px; }
.titulo h3 { margin: 0; font-size: 1.6rem; font-variant-numeric: tabular-nums; }
.dai { margin-inline-start: auto; font-weight: 700; padding: 4px 10px; border-radius: 99px; background: var(--superficie-2); }
.texto { margin: 8px 0; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
h4 { margin: 16px 0 6px; font-size: 0.9rem; }
.hijos { list-style: none; margin: 0; padding: 0; border: 1px solid var(--linea); border-radius: var(--radio); max-height: 280px; overflow-y: auto; }
.hijos li + li { border-top: 1px solid var(--linea); }
.paises { display: grid; gap: 6px; }
.pais { display: flex; gap: 8px; align-items: flex-start; padding: 6px 0; border-top: 1px solid var(--linea); }
.pais:first-child { border-top: 0; }
.pais b { width: 30px; flex: none; padding-top: 2px; }
.pais-datos { display: grid; gap: 5px; min-width: 0; }
.fila-chips { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.etiqueta.aviso { display: inline-flex; gap: 4px; align-items: center; }
.pais .codigo-sac { font-size: 0.8rem; padding: 2px 6px; }
.nota-legal { border: 1px solid var(--linea); border-radius: var(--radio); padding: 6px 10px; margin-bottom: 6px; font-size: 0.86rem; }
.nota-legal summary { cursor: pointer; font-weight: 600; }
.vacio-det { display: flex; gap: 8px; align-items: center; justify-content: center; min-height: 260px; }
@media (max-width: 900px) { .arbol-arancel { grid-template-columns: 1fr; } }
</style>
