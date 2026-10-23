<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Kpi from '@/componentes/Kpi.vue'
import { fmtFecha, fmtNum } from '@/nucleo/utils'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import { comercioExterior, puede } from '@/stores/sesion'

// Resumen del módulo de productos (como el del ERP): la puesta en marcha
// mientras falte configuración, las cifras, los productos por estado y por
// familia, lo que falta completar y lo último modificado. Cada cifra abre el
// catálogo con ese filtro.
const router = useRouter()
// Sin comercio exterior no hay fichas que revisar ni códigos que aprobar: solo las cifras del catálogo
const comex = comercioExterior()
const r = ref(null)
const error = ref(false)
async function cargar() {
  error.value = false
  try {
    r.value = await api.get('/productos/resumen')
  } catch {
    error.value = true
  }
}
onMounted(cargar)
alCambiar(cargar, ['/productos', '/catalogos'])

const catalogo = (query = {}) => ({ path: '/productos/catalogo', query })
const kpis = computed(() => [
  { titulo: t('Products'), valor: r.value.total, icono: 'caja', detalle: t('{0} variants (items)', [fmtNum(r.value.variantes)]), a: catalogo({ estado: '' }) },
  ...(comex ? [
  // La vista «borradores» del catálogo incluye los devueltos
  { titulo: t('In draft'), valor: r.value.por_estado.borradores + r.value.por_estado.observado, icono: 'editar', detalle: t('Technical sheet to complete'),
    a: catalogo({ estado: 'borradores' }), tono: r.value.por_estado.borradores + r.value.por_estado.observado ? 'alerta' : 'normal' },
  { titulo: t('In review'), valor: r.value.por_estado.revision, icono: 'reloj', detalle: t('Waiting for customs review'), a: catalogo({ estado: 'revision' }) },
  { titulo: t('Approved'), valor: r.value.por_estado.aprobados, icono: 'check', detalle: t('Ready for orders and invoices'), a: catalogo({ estado: 'aprobados' }) },
  ] : [
    { titulo: t('Without family'), valor: r.value.sin_familia, icono: 'capas', detalle: t('The family says which data they need'), a: catalogo({ estado: '' }) },
    { titulo: t('Without variants'), valor: r.value.sin_variantes, icono: 'caja', detalle: t('They cannot be ordered yet'), a: catalogo({ estado: '' }) },
  ]),
])
// Barras por estado de la ficha (un solo color; rótulo y cifra escritos)
const porEstado = computed(() => [
  { clave: 'borradores', nombre: t('Draft'), n: r.value.por_estado.borradores, tono: 'neutro' },
  { clave: 'revision', nombre: t('In review'), n: r.value.por_estado.revision, tono: 'info' },
  { clave: 'observado', nombre: t('Returned'), n: r.value.por_estado.observado, tono: 'aviso' },
  { clave: 'aprobados', nombre: t('Approved'), n: r.value.por_estado.aprobados, tono: 'ok' },
])
const maximo = (lista, k = 'n') => Math.max(1, ...lista.map((x) => x[k]))
const ancho = (n, lista, k) => `${Math.round((n / maximo(lista, k)) * 100)}%`
const pct = (n) => (r.value.total ? t('{0}% of the products', [Math.round((n / r.value.total) * 100)]) : '')
const pendientes = computed(() => [
  { titulo: t('Without family'), n: r.value.sin_familia, texto: t('The family says which data they need, their variants, labels and packing.'), a: catalogo({ estado: '' }) },
  { titulo: t('Without variants'), n: r.value.sin_variantes, texto: t('A product needs at least one item to be ordered.'), a: catalogo({ estado: '' }) },
  ...(r.value.exige_codigo_barras ? [{ titulo: t('Variants without barcode'), n: r.value.sin_codigo_barras, texto: t('Your company or one of your families requires the barcode (GTIN, EAN or UPC).'), a: '/mantenimiento?catalogo=articulos' }] : []),
  ...(comex ? [{ titulo: t('Blocking invoices'), n: r.value.bloquean, texto: t('Without an approved HS code their invoices cannot be finalized.'), a: catalogo({ estado: 'bloquean' }), tono: 'error' }] : []),
])
// Puesta en marcha: lo que hay que configurar antes de crear productos
const pasos = computed(() => {
  const c = r.value?.configuracion
  if (!c) return []
  return [
    { titulo: t('Attributes'), texto: t('The data of your products (brand, model, material…) and what tells their variants apart (a measure, a flavor, a concentration…).'), hecho: c.atributos > 0, a: '/mantenimiento?catalogo=atributos' },
    { titulo: t('Product families'), texto: t('Each family says which data its products need and their variant attributes; labels and packing use it.'), hecho: c.familias > 0, a: '/grupos-producto' },
    { titulo: t('First product'), texto: t('Create it step by step with its variants.'), hecho: r.value.total > 0, a: '/productos/nuevo' },
  ]
})
const avance = computed(() => pasos.value.filter((p) => p.hecho).length)
const enMarcha = computed(() => pasos.value.length && avance.value < pasos.value.length)
</script>

<template>
  <div>
    <header class="pagina-cabeza">
      <div>
        <h1>{{ t('Products summary') }}</h1>
        <p>{{ t('How your catalog is and what is left to complete. Each figure opens the catalog with that filter.') }}</p>
      </div>
    </header>

    <div v-if="error" class="nota error" role="alert">
      <Icono nombre="alerta" :tam="16" /><span class="crece">{{ t('The summary could not be loaded.') }}</span>
      <button type="button" class="btn btn-chico" @click="cargar">{{ t('Retry') }}</button>
    </div>

    <!-- Cargando: el mismo esqueleto que ocupará el tablero (sin saltos) -->
    <div v-else-if="!r" aria-busy="true" :aria-label="t('Loading…')">
      <div class="kpis"><div v-for="i in 4" :key="i" class="kpi"><span class="esqueleto" style="width: 90px; height: 14px" /><span class="esqueleto" style="width: 60px; height: 30px" /></div></div>
      <div class="dos-columnas mt"><div class="panel"><span class="esqueleto" style="height: 160px" /></div><div class="panel"><span class="esqueleto" style="height: 160px" /></div></div>
    </div>

    <template v-else>
      <!-- Puesta en marcha: primero, mientras falte algo indispensable -->
      <section v-if="enMarcha" class="panel mb-3" aria-labelledby="t-marcha">
        <div class="panel-cabeza">
          <div><h2 id="t-marcha">{{ t('Getting started') }}</h2><p>{{ t('{0} of {1} steps. Follow the order: each step uses the previous one.', [avance, pasos.length]) }}</p></div>
        </div>
        <ol class="lista-accion">
          <li v-for="(p, i) in pasos" :key="p.titulo">
            <router-link :to="p.a" class="lista-accion-fila">
              <span class="cifra-tono" :class="{ 'tono-info': !p.hecho }"><Icono v-if="p.hecho" nombre="check" :tam="16" /><template v-else>{{ i + 1 }}</template></span>
              <span class="lista-accion-texto"><b>{{ p.titulo }}<span v-if="p.hecho" class="oculto-visual"> ({{ t('done') }})</span></b><small>{{ p.texto }}</small></span>
              <span class="lista-accion-ir">{{ p.hecho ? t('Review') : t('Start') }}<Icono nombre="derecha" :tam="14" /></span>
            </router-link>
          </li>
        </ol>
      </section>

      <section class="kpis" :aria-label="t('Catalog figures')">
        <Kpi v-for="k in kpis" :key="k.titulo" :titulo="k.titulo" :valor="k.valor" :detalle="k.detalle" :icono="k.icono" :tono="k.tono" @abrir="router.push(k.a)" />
      </section>

      <div class="dos-columnas mt">
        <section v-if="comex" class="panel" aria-labelledby="t-estado">
          <div class="panel-cabeza"><div><h2 id="t-estado">{{ t('Products by status') }}</h2><p>{{ t('Where their technical sheet and classification are.') }}</p></div></div>
          <ul class="barras">
            <li v-for="e in porEstado" :key="e.clave">
              <router-link :to="catalogo({ estado: e.clave })" class="barra-fila" :title="pct(e.n)">
                <span class="barra-rotulo"><span class="estado" :class="`estado-${e.tono}`"><span class="estado-marca" />{{ e.nombre }}</span></span>
                <span class="barra-riel" aria-hidden="true"><span class="barra-dato" :style="{ width: ancho(e.n, porEstado) }" /></span>
                <span class="barra-cifra">{{ fmtNum(e.n) }}</span>
              </router-link>
            </li>
          </ul>
        </section>

        <section class="panel" aria-labelledby="t-familia">
          <div class="panel-cabeza">
            <div><h2 id="t-familia">{{ t('Products by family') }}</h2><p>{{ t('The families with the most products.') }}</p></div>
            <router-link v-if="puede('catalogos.ver')" to="/grupos-producto" class="btn btn-chico btn-fantasma">{{ t('See families') }}</router-link>
          </div>
          <ul v-if="r.por_familia.length" class="barras">
            <li v-for="f in r.por_familia" :key="f.id">
              <router-link :to="catalogo({ familia: f.id })" class="barra-fila" :title="pct(f.productos)">
                <span class="barra-rotulo"><span>{{ tx(f.nombre) }}</span></span>
                <span class="barra-riel" aria-hidden="true"><span class="barra-dato" :style="{ width: ancho(f.productos, r.por_familia, 'productos') }" /></span>
                <span class="barra-cifra">{{ fmtNum(f.productos) }}</span>
              </router-link>
            </li>
            <li v-if="r.otras_familias" class="barra-fila"><span class="barra-rotulo apagado">{{ t('Other families') }}</span><span /><span class="barra-cifra">{{ fmtNum(r.otras_familias) }}</span></li>
          </ul>
          <p v-else class="ayuda">{{ t('No product has a family yet.') }}</p>
        </section>
      </div>

      <div class="dos-columnas mt">
        <section class="panel" aria-labelledby="t-completar">
          <div class="panel-cabeza"><div><h2 id="t-completar">{{ t('To complete') }}</h2><p>{{ t('Products and variants that lack something. Open the list and complete them.') }}</p></div></div>
          <ul class="lista-accion">
            <li v-for="p in pendientes" :key="p.titulo">
              <router-link v-if="p.n" :to="p.a" class="lista-accion-fila">
                <span class="cifra-tono" :class="p.tono === 'error' ? 'tono-error' : 'tono-alerta'">{{ fmtNum(p.n) }}</span>
                <span class="lista-accion-texto"><b>{{ p.titulo }}</b><small>{{ p.texto }}</small></span>
                <span class="lista-accion-ir">{{ t('See') }}<Icono nombre="derecha" :tam="14" /></span>
              </router-link>
              <div v-else class="lista-accion-fila">
                <span class="cifra-tono" aria-hidden="true"><Icono nombre="check" :tam="16" /></span>
                <span class="lista-accion-texto"><b>{{ t('{0}: none', [p.titulo]) }}</b><small>{{ p.texto }}</small></span>
              </div>
            </li>
          </ul>
        </section>

        <section class="panel" aria-labelledby="t-recientes">
          <div class="panel-cabeza"><div><h2 id="t-recientes">{{ t('Recently changed') }}</h2></div>
            <router-link to="/productos/catalogo" class="btn btn-chico btn-fantasma">{{ t('See catalog') }}</router-link></div>
          <ul v-if="r.recientes.length" class="lista-accion">
            <li v-for="p in r.recientes" :key="p.id">
              <router-link :to="`/productos/${p.id}`" class="lista-accion-fila">
                <span class="lista-accion-texto"><b>{{ tx(p.nombre || p.codigo || '—') }}</b>
                  <small><span class="mono">{{ tx(p.codigo || '') }}</span><template v-if="p.familia"> · {{ tx(p.familia) }}</template> · {{ fmtFecha(p.actualizado_en) }}</small></span>
                <EstadoBadge v-if="comex" :estado="p.estado" tipo="producto" />
              </router-link>
            </li>
          </ul>
          <p v-else class="ayuda">{{ t('No products yet.') }} <router-link v-if="puede('catalogos.crear')" to="/productos/nuevo" class="enlace">{{ t('Create the first one') }}</router-link></p>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* Barras horizontales de un solo color (como en el ERP): rótulo, riel y cifra; cada fila abre la lista filtrada */
.barras { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.barra-fila { display: grid; grid-template-columns: minmax(0, 11rem) minmax(0, 1fr) 3rem; align-items: center; gap: 12px; padding: 7px 8px; margin: 0 -8px;
  border-radius: var(--radio); color: inherit; text-decoration: none; }
a.barra-fila:hover { background: var(--fila-hover); }
.barra-rotulo { display: flex; align-items: center; gap: 6px; min-width: 0; }
.barra-rotulo > span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.barra-riel { height: 10px; background: var(--barra-fondo, var(--linea-suave)); border-radius: 3px; overflow: hidden; }
.barra-dato { display: block; height: 100%; background: var(--barra-dato, var(--acento)); border-radius: 3px; transition: width 0.4s ease-out; }
.barra-cifra { text-align: end; font-weight: 700; font-variant-numeric: tabular-nums; }
@media (max-width: 600px) { .barra-fila { grid-template-columns: minmax(0, 1fr) 3rem; } .barra-riel { grid-column: 1 / -1; grid-row: 2; } }
@media (prefers-reduced-motion: reduce) { .barra-dato { transition: none; } }
/* Estado: color con forma (el texto lo dice) */
.estado { display: inline-flex; align-items: center; gap: 6px; font-size: var(--t-xs); font-weight: 650; padding: 1px 9px 1px 8px; border-radius: 20px; white-space: nowrap; line-height: 1.65; }
.estado-marca { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.estado-neutro { background: var(--linea-suave); color: var(--tinta-2); }
.estado-neutro .estado-marca { border: 2px solid var(--tinta-3); }
.estado-ok { background: var(--ok-fondo); color: var(--ok); }
.estado-ok .estado-marca { background: var(--ok); }
.estado-aviso { background: var(--aviso-fondo); color: var(--aviso); }
.estado-aviso .estado-marca { background: linear-gradient(90deg, var(--aviso) 50%, transparent 50%); border: 1.5px solid var(--aviso); }
.estado-info { background: var(--info-fondo); color: var(--info-texto); }
.estado-info .estado-marca { background: var(--info); border-radius: 2px; }
.lista-accion-ir { display: inline-flex; align-items: center; gap: 4px; font-size: var(--t-sm); font-weight: 600; color: var(--acento-texto); }
.mt { margin-top: 16px; }
</style>
