<script setup>
// Familias de producto: todo lo que clasifica un tipo de producto en un solo
// lugar, en el orden en que se arma (familia y categorías → preguntas →
// reglas), con la salud de cada familia y lo que le falta.
import { t, tx } from '../i18n/index.js'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Icono from '../components/Icono.vue'
import PanelDominios from '../components/aranceles/PanelDominios.vue'
import PanelAtributos from '../components/aranceles/PanelAtributos.vue'
import PanelReglas from '../components/aranceles/PanelReglas.vue'
import PanelMateriales from '../components/aranceles/PanelMateriales.vue'
import PanelBusqueda from '../components/aranceles/PanelBusqueda.vue'
import AsistenteFamilia from '../components/familias/AsistenteFamilia.vue'
import { puede } from '../stores/sesion'
import { errorApi } from '../stores/ui'

const route = useRoute()
const router = useRouter()
const vista = ref(route.query.vista || 'resumen')
const familias = ref(null)
const paises = ref([])
const meta = ref({ condiciones: {} })
const edita = puede('clasificacion.configurar')

const MENU = computed(() => [
  { titulo: t('Product families'), items: [['resumen', t('Overview'), 'tablero', familias.value?.length]] },
  { titulo: t('Set up, in this order'), items: [['dominios', t('1 · Families and categories'), 'capas'],
    ['atributos', t('2 · Questions'), 'lista'], ['reglas', t('3 · Rules'), 'varita']] },
  { titulo: t('Reference lists'), items: [['materiales', t('Material classes'), 'capas'], ['busqueda', t('Search vocabulary'), 'buscar']] },
])
// Qué sección resuelve cada aviso de la salud de una familia
const ARREGLA = [
  [/chapter/i, 'dominios'], [/categor/i, 'dominios'], [/question/i, 'atributos'], [/rule/i, 'reglas'],
]
const seccionDe = (aviso) => (ARREGLA.find(([re]) => re.test(aviso)) || [null, 'dominios'])[1]

const menu = ref(null)
// Asistente de una familia: ?vista=asistente&familia=CODIGO (sin código, una familia nueva)
const familiaAsistente = ref(route.query.familia || '')
function abrirAsistente(codigo = '') {
  familiaAsistente.value = codigo
  vista.value = 'asistente'
  router.replace({ query: { vista: 'asistente', ...(codigo && { familia: codigo }) } })
}
function codigoNuevo(codigo) {
  familiaAsistente.value = codigo
  router.replace({ query: { vista: 'asistente', familia: codigo } })
  cargar()
}
function cambiarVista(v) {
  vista.value = v
  router.replace({ query: { vista: v } })
  nextTick(() => {
    const nav = menu.value
    const el = nav?.querySelector('[aria-current="page"]')
    if (nav && el && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = el.offsetLeft - (nav.clientWidth - el.clientWidth) / 2
  })
}

async function cargar() {
  try {
    const [f, ps, m] = await Promise.all([api.get('/familias'), api.get('/aranceles/paises'), api.get('/aranceles/opciones')])
    familias.value = f
    paises.value = ps
    meta.value = m
  } catch (e) {
    errorApi(e)
  }
}

onMounted(cargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <div class="pestanas-pildora sub-mod">
        <router-link to="/productos" class="pildora">{{ t('Products') }}</router-link>
        <span class="pildora" aria-current="page" aria-pressed="true">{{ t('Product families') }}</span>
        <router-link v-if="puede('aranceles.ver')" to="/aranceles" class="pildora">{{ t('Tariff schedule') }}</router-link>
      </div>
      <h1>{{ t('Product families') }}</h1>
      <p>{{ t('Each family groups the categories, questions and rules that classify one kind of product. Suppliers and buyers only answer the questions; the code always comes from the official tariff.') }}</p>
    </div>
  </div>

  <div class="layout-lateral">
    <nav ref="menu" class="menu-lateral" :aria-label="t('Product families sections')">
      <template v-for="g in MENU" :key="g.titulo">
        <p class="menu-grupo">{{ tx(g.titulo) }}</p>
        <button v-for="[k, l, icono, n] in g.items" :key="k" type="button" class="menu-item" :aria-current="vista === k ? 'page' : undefined" @click="cambiarVista(k)">
          <Icono :nombre="icono" :tam="16" /><span class="menu-txt">{{ tx(l) }}</span><span v-if="n != null" class="cuenta">{{ tx(n) }}</span>
        </button>
      </template>
    </nav>
    <div class="layout-contenido">
      <template v-if="vista === 'resumen'">
        <ol class="guia" :aria-label="t('How a family is set up')">
          <li><b>{{ t('Family and categories') }}</b><span>{{ t('What kind of product it is and which tariff chapters it falls in.') }}</span></li>
          <li><b>{{ t('Questions') }}</b><span>{{ t('What the sheet asks to tell its codes apart (material, use, who it is for…).') }}</span></li>
          <li><b>{{ t('Rules') }}</b><span>{{ t('Which answers lead to which codes. Without rules the code comes only from the official text, with low confidence.') }}</span></li>
          <li><b>{{ t('Test with an item') }}</b><span>{{ t('Open an item of the family and check the suggested code and why.') }}</span></li>
        </ol>
        <div v-if="edita" class="acciones-resumen">
          <button class="btn btn-primario" @click="abrirAsistente()"><Icono nombre="mas" />{{ t('New family') }}</button>
        </div>
        <p v-if="familias && !familias.length" class="vacio-panel">
          {{ t('There are no product families yet. Create the first one to start classifying.') }}
          <button v-if="edita" class="btn btn-primario" @click="abrirAsistente()"><Icono nombre="mas" />{{ t('New family') }}</button>
        </p>
        <div class="familias">
          <article v-for="f in familias || []" :key="f.codigo" class="panel familia" :class="{ apagada: !f.activo }">
            <header>
              <div><h3>{{ tx(f.nombre) }}</h3><span class="ayuda">{{ tx(f.codigo) }}<template v-if="f.modo === 'MANUAL'"> · {{ t('classified by hand') }}</template></span></div>
              <span v-if="!f.publicada" class="etiqueta acento">{{ t('Draft') }}</span>
              <span v-else class="etiqueta" :class="f.estado === 'lista' ? 'ok' : 'aviso'">{{ tx(f.estado === 'lista' ? t('Ready') : t('Incomplete')) }}</span>
            </header>
            <div class="cifras">
              <button type="button" @click="cambiarVista('dominios')"><b>{{ tx(f.categorias) }}</b><span>{{ t('categories') }}</span></button>
              <button type="button" @click="cambiarVista('atributos')"><b>{{ tx(f.preguntas) }}</b><span>{{ t('questions') }}</span></button>
              <button type="button" @click="cambiarVista('reglas')"><b>{{ tx(f.reglas) }}</b><span>{{ t('rules') }}</span></button>
              <button type="button" @click="cambiarVista('dominios')"><b>{{ tx(f.capitulos_auto.length) }}/{{ tx(f.capitulos.length) }}</b><span>{{ t('automatic chapters') }}</span></button>
            </div>
            <p class="uso">
              <template v-if="f.productos.total">
                {{ t('{0} items · {1} pending', [f.productos.total, f.productos.pendientes]) }}
                <template v-if="f.aprobados_sin_cambio != null"> · <b>{{ t('{0}% approved as suggested', [f.aprobados_sin_cambio]) }}</b></template>
                <router-link v-if="f.productos.baja_confianza" :to="{ path: '/productos', query: { estado: 'baja_confianza' } }" class="baja">
                  · {{ t('{0} with low confidence', [f.productos.baja_confianza]) }}</router-link>
              </template>
              <template v-else>{{ t('No items in this family yet.') }}</template>
            </p>
            <button v-if="edita && !f.publicada" class="btn" @click="abrirAsistente(f.codigo)"><Icono nombre="derecha" :tam="15" />{{ t('Continue setup and publish') }}</button>
            <button v-else-if="edita" class="btn btn-fantasma" @click="abrirAsistente(f.codigo)"><Icono nombre="varita" :tam="15" />{{ t('Open in the guided setup') }}</button>
            <ul v-if="f.avisos.length" class="avisos">
              <li v-for="a in f.avisos" :key="a">
                <Icono nombre="alerta" :tam="14" /><span>{{ tx(a) }}</span>
                <button v-if="edita" type="button" class="btn-texto" @click="cambiarVista(seccionDe(a))">{{ t('Fix') }}</button>
              </li>
            </ul>
          </article>
        </div>
      </template>
      <AsistenteFamilia v-else-if="vista === 'asistente'" :codigo="familiaAsistente" @codigo="codigoNuevo" @listo="cargar" @cerrar="cargar(); cambiarVista('resumen')" />
      <PanelDominios v-else-if="vista === 'dominios'" />
      <PanelAtributos v-else-if="vista === 'atributos'" />
      <PanelReglas v-else-if="vista === 'reglas'" :paises="paises" :condiciones="meta.condiciones" />
      <PanelMateriales v-else-if="vista === 'materiales'" />
      <PanelBusqueda v-else-if="vista === 'busqueda'" />
    </div>
  </div>
</template>

<style scoped>
.sub-mod { margin-bottom: 10px; }
.sub-mod .pildora { text-decoration: none; }
.guia { list-style: none; counter-reset: paso; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin: 0 0 16px; padding: 0; }
.guia li { counter-increment: paso; display: flex; flex-direction: column; gap: 3px; padding: 12px 14px 12px 44px; position: relative; border: 1px solid var(--linea); border-radius: var(--radio); background: var(--superficie); }
.guia li::before { content: counter(paso); position: absolute; inset-inline-start: 12px; top: 12px; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); font-weight: 700; font-size: 0.8rem; }
[dir='rtl'] .guia li { padding: 12px 44px 12px 14px; }
.guia span { color: var(--tinta-3); font-size: 0.85rem; line-height: 1.35; }
.familias { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.familia { margin: 0; display: flex; flex-direction: column; gap: 10px; }
.familia.apagada { opacity: 0.6; }
.familia header { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.familia h3 { margin: 0; font-size: 1.05rem; }
.cifras { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.cifras button { display: flex; flex-direction: column; align-items: flex-start; gap: 1px; border: 1px solid var(--linea); border-radius: 9px; background: var(--superficie-2); padding: 7px 9px; font: inherit; color: var(--tinta); cursor: pointer; text-align: start; }
.cifras button:hover { border-color: var(--borde-hover); }
.cifras b { font-size: 1.05rem; }
.cifras span { font-size: 0.74rem; color: var(--tinta-3); }
.uso { margin: 0; font-size: 0.86rem; color: var(--tinta-2); }
.uso .baja { color: var(--aviso); }
.avisos { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.avisos li { display: flex; gap: 6px; align-items: flex-start; font-size: 0.84rem; color: var(--aviso); background: var(--aviso-suave); border: 1px solid var(--aviso-borde); border-radius: 8px; padding: 6px 8px; }
.avisos li span { flex: 1; }
.acciones-resumen { display: flex; justify-content: flex-end; margin: -6px 0 12px; }
.vacio-panel { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; padding: 18px; border: 1px dashed var(--linea); border-radius: var(--radio); }
@media (max-width: 520px) {
  .cifras { grid-template-columns: repeat(2, 1fr); }
}
</style>
