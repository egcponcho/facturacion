<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import { fmtFecha, fmtNum } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import CabezaEtiquetado from '@/modulos/etiquetado/componentes/CabezaEtiquetado.vue'
import CamposEtiqueta from '@/modulos/etiquetado/componentes/CamposEtiqueta.vue'
import ConversionReglas from '@/modulos/etiquetado/componentes/ConversionReglas.vue'
import NombresCampos from '@/modulos/etiquetado/componentes/NombresCampos.vue'
import FamiliasYArticulos from '@/modulos/etiquetado/componentes/FamiliasYArticulos.vue'
import HistorialEtiquetas from '@/modulos/etiquetado/componentes/HistorialEtiquetas.vue'
import MatrizEtiquetado from '@/modulos/etiquetado/componentes/MatrizEtiquetado.vue'
import PrimerUsoEtiquetado from '@/modulos/etiquetado/componentes/PrimerUsoEtiquetado.vue'
import TamanosEtiqueta from '@/modulos/etiquetado/componentes/TamanosEtiqueta.vue'
import TiposEtiqueta from '@/modulos/etiquetado/componentes/TiposEtiqueta.vue'
import { SUJETOS } from '@/modulos/etiquetado/etiquetas.js'

// Configuración del etiquetado como una guía en orden (no pestañas sueltas):
// 1 qué etiquetas se imprimen → 2 cómo se agrupan los artículos → 3 los
// diseños → 4 qué diseño va en qué → 5 nombres y campos (opcional) → 6 revisar.
// Cada paso dice si está listo o qué le falta, calculado de los datos reales;
// los asistentes que se dejan a medias quedan como borradores (abajo a la izquierda).
const route = useRoute()
const router = useRouter()
const PASOS = () => [
  { clave: 'tipos', titulo: t('Label types'), que: t('Which labels you print (hang tag, price sticker, carton label…), what each one labels and how many come out.') },
  { clave: 'familias', titulo: t('Families and items'), que: t('How you group your items to label them. Each family can have its own designs; without families, everything uses the design of the whole company.') },
  { clave: 'disenos', titulo: t('Designs'), que: t('Each label type needs at least one approved design.') },
  { clave: 'matriz', titulo: t('Which design goes on what'), que: t('The design of each label type for the whole company and for each family, with its exceptions.') },
  { clave: 'campos', titulo: t('Field names and sources'), que: t('Optional: rename fields and decide where each value comes from (item, product, PO…).'), opcional: true },
  { clave: 'revisar', titulo: t('Review and history'), que: t('What changed, by whom and when; conversions used by the fields.') },
]
// Las direcciones viejas (?vista=) siguen llevando al paso que corresponde
const ANTES = { tipos: 'tipos', familias: 'familias', campos: 'campos', historial: 'revisar', matriz: 'matriz' }
const paso = computed(() => {
  const p = route.query.paso || ANTES[route.query.vista]
  return PASOS().some((x) => x.clave === p) ? p : null
})
const indice = computed(() => PASOS().findIndex((x) => x.clave === (paso.value || pasoSugerido.value)))
const actual = computed(() => PASOS()[Math.max(indice.value, 0)])
function ir(clave, extra = {}) {
  router.replace({ query: { paso: clave, ...extra } })
  window.scrollTo({ top: 0 })
}

// ---- Estado de cada paso, desde los datos ----------------------------------------------------
const tipos = ref(null)
const familias = ref([])
const plantillas = ref([])
const matrices = ref({})
async function revisar() {
  try {
    const [ts, fs, ps] = await Promise.all([api.get('/etiquetas/tipos', { todos: true }), api.get('/etiquetas/familias'),
      api.get('/etiquetas/plantillas', { size: 200 })])
    const sujetos = [...new Set(ts.filter((x) => x.activo).map((x) => x.sujeto))]
    const ms = await Promise.all(sujetos.map((s) => api.get('/etiquetas/matriz', { sujeto: s }).catch(() => null)))
    // Todo junto: el paso sugerido se calcula con los datos completos
    matrices.value = Object.fromEntries(sujetos.map((s, i) => [s, ms[i]]))
    familias.value = fs
    plantillas.value = ps.items
    tipos.value = ts
  } catch (e) {
    errorApi(e)
  }
}
onMounted(revisar)
alCambiar(() => revisar(), ['/etiquetas/tipos', '/etiquetas/familias', '/etiquetas/plantillas', '/etiquetas/usos', '/etiquetas/articulos',
  '/etiquetas/productos', '/etiquetas/grupos-articulos'])

// «1 artículo» / «3 artículos»
const n = (k, uno, varios) => (k === 1 ? uno : varios)
const activos = computed(() => (tipos.value || []).filter((x) => x.activo))
const sinFamilia = computed(() => matrices.value.ARTICULO?.filas?.find((f) => f.nivel === 'SIN_FAMILIA')?.articulos || 0)
const tiposSinDiseno = computed(() => activos.value.filter((tp) => !plantillas.value.some((p) => p.tipo_etiqueta_id === tp.id && p.vigente)))
// Lugares sin diseño en tipos obligatorios: artículos (cuántos) y cajas/documentos (cuántas filas)
const faltan = computed(() => {
  const r = { articulos: matrices.value.ARTICULO?.cobertura?.sin_diseno || 0, otros: 0 }
  for (const s of ['BULTO', 'DOCUMENTO']) {
    for (const f of matrices.value[s]?.filas || []) r.otros += Object.values(f.celdas).filter((c) => c.falta).length
  }
  return r
})
// estado: listo | falta | opcional; texto: lo que le falta o lo que tiene
const estados = computed(() => {
  if (!tipos.value) return {}
  const e = {}
  e.tipos = activos.value.length ? { estado: 'listo', texto: n(activos.value.length, t('1 label type'), t('{0} label types', [fmtNum(activos.value.length)])) }
    : { estado: 'falta', texto: t('No label types yet') }
  e.familias = !familias.value.length ? { estado: 'opcional', texto: t('No families: one design for everything') }
    : sinFamilia.value ? { estado: 'falta', texto: n(sinFamilia.value, t('1 item without family'), t('{0} items without family', [fmtNum(sinFamilia.value)])) }
      : { estado: 'listo', texto: n(familias.value.length, t('1 family'), t('{0} families', [fmtNum(familias.value.length)])) }
  e.disenos = !activos.value.length ? { estado: 'espera', texto: t('First the label types') }
    : tiposSinDiseno.value.length ? { estado: 'falta', texto: n(tiposSinDiseno.value.length, t('1 type without an approved design'), t('{0} types without an approved design', [fmtNum(tiposSinDiseno.value.length)])) }
      : { estado: 'listo', texto: n(plantillas.value.filter((p) => p.vigente && p.usos).length, t('1 design in use'), t('{0} designs in use', [fmtNum(plantillas.value.filter((p) => p.vigente && p.usos).length)])) }
  e.matriz = !activos.value.length ? { estado: 'espera', texto: t('First the label types') }
    : faltan.value.articulos ? { estado: 'falta', texto: n(faltan.value.articulos, t('1 item without a design'), t('{0} items without a design', [fmtNum(faltan.value.articulos)])) }
      : faltan.value.otros ? { estado: 'falta', texto: n(faltan.value.otros, t('1 place without a design'), t('{0} places without a design', [fmtNum(faltan.value.otros)])) }
        : { estado: 'listo', texto: t('Everything has a design') }
  e.campos = { estado: 'opcional', texto: t('Optional') }
  e.revisar = { estado: 'info', texto: t('Whenever you need it') }
  return e
})
// Sin paso en la dirección se abre el primero que falta
const pasoSugerido = computed(() => PASOS().find((x) => estados.value[x.clave]?.estado === 'falta')?.clave || 'matriz')
// Una vez elegido, el paso queda en la dirección (no salta solo cuando cambian los datos)
watch(() => [tipos.value, pasoSugerido.value], () => {
  if (!paso.value && tipos.value) router.replace({ query: { ...route.query, vista: undefined, paso: pasoSugerido.value } })
})
const listos = computed(() => ['tipos', 'familias', 'disenos', 'matriz'].filter((k) => ['listo', 'opcional'].includes(estados.value[k]?.estado)).length)

// ---- Primer uso: sin tipos, el asistente corto en la página --------------------------------------
const primerUso = ref(false)
watch(() => [tipos.value, paso.value], () => {
  if (tipos.value && !tipos.value.length && puede('etiquetas.configurar') && (!paso.value || paso.value === 'tipos')) primerUso.value = true
})
function listo() {
  primerUso.value = false
  revisar()
  ir('familias')
}

// ---- Borradores (asistentes a medias, de esta persona) ---------------------------------------------
const borradores = ref([])
const cargarBorradores = () => api.get('/perfil/borradores', { prefijo: 'etiquetas.' }).then((r) => (borradores.value = r)).catch(() => {})
onMounted(cargarBorradores)
const rutaBorrador = (b) => (b.clave.startsWith('etiquetas.familia.') ? `/etiquetas/configuracion/familia/${b.clave.split('.')[2]}` : null)
async function descartar(b) {
  if (!(await confirmar(t('Discard the draft “{0}”? Nothing of it was applied.', [b.titulo]), { titulo: t('Discard draft'), boton: t('Discard'), peligro: true }))) return
  try {
    await api.del(`/perfil/borradores/${b.clave}`)
    cargarBorradores()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <CabezaEtiquetado :titulo="t('Labeling setup')" :texto="t('Follow the steps in order; each one says whether it is ready or what it lacks.')" />

  <div class="guia">
    <aside class="guia-lado">
      <p class="guia-progreso">{{ t('{0} of {1} main steps ready', [listos, 4]) }}</p>
      <div class="guia-barra" role="progressbar" :aria-valuenow="listos" aria-valuemin="0" aria-valuemax="4"><span :style="{ width: `${listos * 25}%` }" /></div>
      <ol class="guia-pasos">
        <li v-for="(p, i) in PASOS()" :key="p.clave">
          <button type="button" class="guia-paso" :class="[estados[p.clave]?.estado, { actual: i === indice }]" :aria-current="i === indice ? 'step' : undefined"
                  @click="ir(p.clave)">
            <span class="guia-num">
              <Icono v-if="estados[p.clave]?.estado === 'listo'" nombre="check" :tam="14" />
              <template v-else>{{ i + 1 }}</template>
            </span>
            <span class="guia-texto">
              <strong>{{ p.titulo }}</strong>
              <small>{{ estados[p.clave]?.texto || '…' }}</small>
            </span>
          </button>
        </li>
      </ol>
      <section v-if="borradores.length" class="guia-borradores">
        <h3>{{ t('Your drafts') }}</h3>
        <p class="ayuda">{{ t('Left halfway; nothing of them is applied yet.') }}</p>
        <div v-for="b in borradores" :key="b.clave" class="guia-borrador">
          <router-link v-if="rutaBorrador(b)" :to="rutaBorrador(b)">{{ b.titulo || b.clave }}</router-link>
          <span v-else>{{ b.titulo || b.clave }}</span>
          <small>{{ fmtFecha(b.actualizado) }}</small>
          <button type="button" class="btn-icono" :aria-label="t('Discard draft')" :title="t('Discard draft')" @click="descartar(b)"><Icono nombre="basura" :tam="14" /></button>
        </div>
      </section>
    </aside>

    <main class="guia-contenido">
      <header class="guia-cabeza">
        <p class="guia-sup">{{ t('Step {0} of {1}', [indice + 1, PASOS().length]) }}<template v-if="actual.opcional"> · {{ t('Optional') }}</template></p>
        <h2>{{ actual.titulo }}</h2>
        <p class="ayuda">{{ actual.que }}</p>
        <p v-if="estados[actual.clave]?.estado === 'falta'" class="guia-falta"><Icono nombre="alerta" :tam="15" />{{ estados[actual.clave].texto }}</p>
      </header>

      <!-- 1. Tipos de etiqueta -->
      <template v-if="actual.clave === 'tipos'">
        <PrimerUsoEtiquetado v-if="primerUso" @cerrar="primerUso = false" @listo="listo" />
        <template v-else>
          <TiposEtiqueta @cambio="revisar" />
          <TamanosEtiqueta />
        </template>
      </template>

      <!-- 2. Familias -->
      <FamiliasYArticulos v-else-if="actual.clave === 'familias'" />

      <!-- 3. Diseños: uno aprobado por tipo, al menos -->
      <div v-else-if="actual.clave === 'disenos'" class="guia-disenos">
        <article v-for="tp in activos" :key="tp.id" class="panel guia-tipo" :class="{ falta: tiposSinDiseno.includes(tp) }">
          <div>
            <h3>{{ tx(tp.nombre) }} <span class="etiqueta ms-0">{{ SUJETOS()[tp.sujeto] }}</span></h3>
            <p class="ayuda">
              <template v-if="tiposSinDiseno.includes(tp)">{{ t('No approved design yet') }}</template>
              <template v-else>{{ n(plantillas.filter((p) => p.tipo_etiqueta_id === tp.id && p.vigente).length, t('1 approved design'), t('{0} approved designs', [fmtNum(plantillas.filter((p) => p.tipo_etiqueta_id === tp.id && p.vigente).length)])) }}</template>
              · {{ n(plantillas.filter((p) => p.tipo_etiqueta_id === tp.id).length, t('1 design in total'), t('{0} designs in total', [fmtNum(plantillas.filter((p) => p.tipo_etiqueta_id === tp.id).length)])) }}
            </p>
            <div class="guia-mini">
              <img v-for="p in plantillas.filter((x) => x.tipo_etiqueta_id === tp.id && (x.vigente || x.ultima)).slice(0, 4)" :key="p.id" :alt="p.nombre" :title="p.nombre"
                   :src="`/api/etiquetas/versiones/${(p.vigente || p.ultima).id}/miniatura.svg?v=${encodeURIComponent(p.actualizada_en || '')}`" loading="lazy" />
            </div>
          </div>
          <div class="guia-tipo-acciones">
            <router-link v-if="puede('etiquetas.disenar')" :to="`/etiquetas/disenos?nuevo=${tp.id}`" class="btn" :class="{ 'btn-primario': tiposSinDiseno.includes(tp) }">
              <Icono nombre="mas" :tam="15" />{{ t('New design') }}</router-link>
            <router-link to="/etiquetas/disenos" class="btn">{{ t('See the designs') }}</router-link>
          </div>
        </article>
        <p v-if="!activos.length" class="vacio">{{ t('First create the label types (step 1).') }}</p>
      </div>

      <!-- 4. Qué diseño va en qué -->
      <MatrizEtiquetado v-else-if="actual.clave === 'matriz'" @familias="(f) => ir('familias', { familia: f })" />

      <!-- 5. Campos (opcional) -->
      <template v-else-if="actual.clave === 'campos'">
        <NombresCampos />
        <CamposEtiqueta />
      </template>

      <!-- 6. Revisar -->
      <template v-else>
        <ConversionReglas v-if="puede('etiquetas.configurar')" />
        <HistorialEtiquetas />
      </template>

      <footer class="guia-pie">
        <button v-if="indice > 0" type="button" class="btn" @click="ir(PASOS()[indice - 1].clave)"><Icono nombre="atras" :tam="15" />{{ PASOS()[indice - 1].titulo }}</button>
        <span class="separar" />
        <button v-if="indice < PASOS().length - 1" type="button" class="btn btn-primario" @click="ir(PASOS()[indice + 1].clave)">
          {{ t('Next: {0}', [PASOS()[indice + 1].titulo]) }}<Icono nombre="derecha" :tam="15" /></button>
      </footer>
    </main>
  </div>
</template>

<style scoped>
.guia { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 24px; align-items: start; }
.guia-lado { position: sticky; top: 76px; display: flex; flex-direction: column; gap: 10px; }
.guia-progreso { margin: 0; font-size: var(--t-xs); color: var(--tinta-2); font-weight: 600; }
.guia-barra { height: 6px; border-radius: 3px; background: var(--superficie-2); overflow: hidden; }
.guia-barra span { display: block; height: 100%; background: var(--ok); transition: width 0.3s; }
.guia-pasos { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column; gap: 2px; position: relative; }
.guia-paso { display: flex; gap: 10px; align-items: flex-start; width: 100%; padding: 9px 10px; border: 1px solid transparent; border-radius: 10px; background: none;
  font: inherit; text-align: start; cursor: pointer; color: var(--tinta); }
.guia-paso:hover { background: var(--fila-hover); }
.guia-paso.actual { background: var(--superficie); border-color: var(--acento-medio); box-shadow: 0 1px 2px rgb(0 0 0 / 5%); }
.guia-num { flex: none; display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; border: 1.5px solid var(--linea);
  font-size: var(--t-xs); font-weight: 700; color: var(--tinta-2); background: var(--superficie); }
.guia-paso.actual .guia-num { border-color: var(--acento); color: var(--acento-texto); }
.guia-paso.listo .guia-num { background: var(--ok); border-color: var(--ok); color: #fff; }
.guia-paso.falta .guia-num { border-color: var(--aviso); color: var(--aviso); }
.guia-texto { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.guia-texto strong { font-size: var(--t-sm); }
.guia-texto small { font-size: var(--t-xs); color: var(--tinta-3); }
.guia-paso.falta .guia-texto small { color: var(--aviso); }
.guia-borradores { margin-top: 10px; padding: 12px; border: 1px dashed var(--linea); border-radius: 10px; }
.guia-borradores h3 { margin: 0; font-size: var(--t-sm); }
.guia-borradores .ayuda { margin: 2px 0 8px; font-size: var(--t-xs); }
.guia-borrador { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0 6px; align-items: center; padding: 6px 0; border-top: 1px solid var(--linea); font-size: var(--t-sm); }
.guia-borrador a, .guia-borrador > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.guia-borrador small { grid-column: 1; color: var(--tinta-3); font-size: var(--t-xs); }
.guia-borrador .btn-icono { grid-row: 1 / span 2; grid-column: 2; }
.guia-cabeza { margin-bottom: 16px; }
.guia-sup { margin: 0; font-size: var(--t-xs); text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); font-weight: 600; }
.guia-cabeza h2 { margin: 2px 0 4px; font-size: var(--t-lg); }
.guia-cabeza .ayuda { margin: 0; max-width: 760px; }
.guia-falta { display: inline-flex; gap: 6px; align-items: center; margin: 10px 0 0; padding: 6px 10px; border-radius: 8px; font-size: var(--t-sm);
  background: var(--aviso-fondo); color: var(--aviso); }
.guia-disenos { display: flex; flex-direction: column; gap: 10px; }
.guia-tipo { margin: 0; display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.guia-tipo.falta { border-inline-start: 3px solid var(--aviso); }
.guia-tipo h3 { margin: 0; font-size: var(--t-md); }
.guia-tipo .ayuda { margin: 2px 0 0; }
.guia-mini { display: flex; gap: 6px; margin-top: 8px; }
.guia-mini img { height: 48px; max-width: 90px; object-fit: contain; border: 1px solid var(--linea); border-radius: 6px; background: #fff; }
.guia-tipo-acciones { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.guia-pie { display: flex; gap: 8px; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--linea); }
/* Pantallas medianas: los pasos van arriba, en una fila, y el contenido usa todo el ancho */
@media (max-width: 1500px) {
  .guia { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .guia-lado { position: static; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 16px; align-items: center; }
  .guia-progreso { grid-column: 1; }
  .guia-barra { grid-column: 1 / -1; grid-row: 2; }
  .guia-pasos { grid-column: 1 / -1; flex-direction: row; overflow-x: auto; gap: 6px; padding-bottom: 4px; }
  .guia-pasos li { flex: 1 0 150px; }
  .guia-paso { height: 100%; border-color: var(--linea); }
  .guia-borradores { grid-column: 2; grid-row: 1; margin: 0; padding: 4px 10px; display: flex; gap: 10px; align-items: center; border-style: dashed; }
  .guia-borradores .ayuda { display: none; }
  .guia-borrador { border: 0; padding: 0; }
}
@media (max-width: 640px) { .guia-tipo { flex-direction: column; align-items: stretch; } }
</style>
