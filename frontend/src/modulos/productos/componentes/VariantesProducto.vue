<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref, watch } from 'vue'
import Icono from '@/componentes/Icono.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'

// Variantes de un producto, de cualquier tipo. Se ven como matriz (el último
// atributo de variante de su familia en las columnas y los demás en las filas:
// color × talla, concentración × envase…) o como lista con una columna por
// atributo. Los packs y kits van aparte con su contenido. Los atributos y sus
// valores vienen del producto (`ejes`): nada está fijo aquí.
const props = defineProps({
  producto: { type: Object, required: true },
  comex: { type: Boolean, default: false },
  puedeAgregar: { type: Boolean, default: false },
})
const emit = defineEmits(['agregar'])

const p = computed(() => props.producto)
const simples = computed(() => (p.value.articulos || []).filter((a) => a.tipo !== 'PREPACK'))
const ejes = computed(() => (p.value.ejes || []).filter((e) => e.valores.length))
const hayMatriz = computed(() => ejes.value.length > 0 && simples.value.length > 0)

const CLAVE = 'productos.vista_variantes'
let guardada = null
try { guardada = localStorage.getItem(CLAVE) } catch { /* sin almacenamiento */ }
const vista = ref(guardada === 'lista' ? 'lista' : 'matriz')
watch(vista, (v) => { try { localStorage.setItem(CLAVE, v) } catch { /* sin almacenamiento */ } })
const VISTAS = computed(() => [['matriz', t('Matrix')], ['lista', t('List')]])

// Matriz: columnas = valores del último eje; filas = combinaciones de los demás ejes que existen
const norm = (v) => String(v ?? '').trim().toUpperCase()
const ejeColumna = computed(() => ejes.value[ejes.value.length - 1])
const ejesFila = computed(() => ejes.value.slice(0, -1))
const claveFila = (vals) => ejesFila.value.map((e) => norm(vals?.[e.codigo])).join('|')
const filas = computed(() => {
  const vistas = new Map()
  for (const a of simples.value) {
    const k = claveFila(a.valores)
    if (!vistas.has(k)) vistas.set(k, ejesFila.value.map((e) => a.valores?.[e.codigo] || ''))
  }
  // En el orden de los valores de cada eje
  const pos = ejesFila.value.map((e) => new Map(e.valores.map((v, i) => [norm(v), i])))
  return [...vistas.entries()].sort(([, a], [, b]) => {
    for (let i = 0; i < a.length; i++) {
      const d = (pos[i].get(norm(a[i])) ?? 999) - (pos[i].get(norm(b[i])) ?? 999)
      if (d) return d
    }
    return 0
  }).map(([clave, valores]) => ({ clave, valores }))
})
const celdas = computed(() => {
  const m = new Map()
  for (const a of simples.value) m.set(`${claveFila(a.valores)}#${norm(a.valores?.[ejeColumna.value?.codigo])}`, a)
  return m
})
const celda = (fila, col) => celdas.value.get(`${fila.clave}#${norm(col)}`)
const sinValor = computed(() => simples.value.filter((a) => !ejes.value.every((e) => a.valores?.[e.codigo])))
const tituloCelda = (a) => [a.sku, a.codigo_barras && `${t('Barcode')}: ${a.codigo_barras}`,
  a.codigo_proveedor && `${t('Supplier code')}: ${a.codigo_proveedor}`, !a.activo && t('Inactive')].filter(Boolean).join('\n')

// Lista: una columna por atributo de variante
const columnas = computed(() => [
  { clave: 'sku', texto: t('Item code'), fija: true, prioridad: 1 },
  ...(p.value.ejes || []).map((e) => ({ clave: `v_${e.codigo}`, texto: tx(e.nombre), prioridad: 1, valor: (a) => a.valores?.[e.codigo] || '' })),
  { clave: 'codigo_barras', texto: t('Barcode'), prioridad: 2 },
  { clave: 'codigo_proveedor', texto: t('Supplier code'), prioridad: 3 },
  { clave: 'unidad', texto: t('Unit'), prioridad: 3 },
  { clave: 'peso_unitario', texto: t('Unit weight kg'), prioridad: 3, num: true },
  { clave: 'activo', texto: t('Status'), prioridad: 2, opciones: [[true, t('Active')], [false, t('Inactive')]] },
])

// Packs y kits: su contenido muestra solo lo que cambia entre sus componentes (en un pack de
// tallas de un color, la talla); lo común va una vez arriba
function contenido(x) {
  const comps = x.componentes || []
  const claves = [...new Set(comps.flatMap((c) => Object.keys(c.valores || {})))]
  const comunes = claves.filter((k) => new Set(comps.map((c) => norm(c.valores?.[k]))).size === 1)
  const nombres = Object.fromEntries((p.value.ejes || []).map((e) => [e.codigo, e.nombre]))
  return {
    comun: comunes.map((k) => `${tx(nombres[k] || k)}: ${tx(comps[0]?.valores?.[k])}`).join(' · '),
    items: comps.map((c) => ({ sku: c.sku, cantidad: c.cantidad,
      texto: claves.filter((k) => !comunes.includes(k)).map((k) => c.valores?.[k]).filter(Boolean).join(' · ') || c.variante || c.sku })),
  }
}
</script>

<template>
  <div class="vp">
    <div class="vp-barra">
      <p class="ayuda">{{ comex ? t('Every variant of product {0} shares its technical sheet and its HS code. Packs and kits are built with these variants and take their code.', [p.codigo_generico || '—'])
        : t('Every variant of product {0} shares its data. Packs and kits are built with these variants.', [p.codigo_generico || '—']) }}</p>
      <div class="vp-acciones">
        <Segmentos v-if="hayMatriz" v-model="vista" :opciones="VISTAS" :etiqueta="t('View')" />
        <button v-if="puedeAgregar" class="btn btn-chico" type="button" @click="emit('agregar')"><Icono nombre="mas" :tam="14" />{{ t('Add variants') }}</button>
      </div>
    </div>

    <div v-if="!simples.length" class="vp-vacio">
      <Icono nombre="caja" :tam="22" /><span>{{ t('This product has no variants yet.') }}</span>
      <button v-if="puedeAgregar" class="btn btn-primario btn-chico" type="button" @click="emit('agregar')">{{ t('Add variants') }}</button>
    </div>

    <section v-else-if="vista === 'matriz' && hayMatriz" class="vp-matriz-caja">
      <div class="vp-leyenda">
        <span><b>{{ tx(ejeColumna.nombre) }}</b> →</span>
        <span v-if="ejesFila.length">↓ <b>{{ ejesFila.map((e) => tx(e.nombre)).join(' · ') }}</b></span>
        <span class="vp-tenue">{{ t('{0} variants', [simples.length]) }}</span>
      </div>
      <div class="vp-scroll">
        <table class="vp-matriz">
          <thead>
            <tr>
              <th v-for="e in ejesFila" :key="e.codigo" scope="col" class="vp-cab-fila">{{ tx(e.nombre) }}</th>
              <th v-for="v in ejeColumna.valores" :key="v" scope="col">{{ tx(v) }}</th>
              <th scope="col" class="vp-total">{{ t('Total') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in filas" :key="f.clave">
              <th v-for="(v, i) in f.valores" :key="i" scope="row" class="vp-valor-fila">{{ tx(v || '—') }}</th>
              <td v-for="v in ejeColumna.valores" :key="v">
                <span v-if="celda(f, v)" class="vp-celda" :class="{ inactiva: !celda(f, v).activo }" :title="tituloCelda(celda(f, v))">
                  <span class="vp-sku">{{ celda(f, v).sku }}</span>
                  <span class="vp-marcas">
                    <Icono v-if="celda(f, v).codigo_barras" nombre="barras" :tam="12" />
                  </span>
                </span>
                <span v-else class="vp-hueco" :title="t('No variant with these values')">·</span>
              </td>
              <td class="vp-total">{{ ejeColumna.valores.filter((v) => celda(f, v)).length }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="sinValor.length" class="nota aviso mt-chico"><Icono nombre="alerta" :tam="15" />{{ t('{0} variants lack a value of their family and are only in the list.', [sinValor.length]) }}</p>
    </section>

    <TablaDatos v-else tabla="productos_variantes" :columnas="columnas" :filas="simples" :etiqueta="t('Variants')">
      <template #celda-sku="{ fila: a }"><span class="vp-sku-lista">{{ tx(a.sku) }}</span></template>
      <template #celda-activo="{ fila: a }"><span v-if="a.activo" class="etiqueta ok ms-0">{{ t('Active') }}</span><span v-else class="etiqueta ms-0">{{ t('Inactive') }}</span></template>
    </TablaDatos>

    <template v-if="p.compuestos?.length">
      <h3 class="vp-titulo">{{ t('Packs and kits') }} <span class="cuenta">{{ p.compuestos.length }}</span></h3>
      <div class="vp-packs">
        <article v-for="x in p.compuestos" :key="x.id" class="vp-pack">
          <header>
            <span class="vp-pack-id">{{ x.codigo }}</span>
            <div>
              <b>{{ x.kit ? t('Kit {0}', [x.codigo]) : t('Pack {0}', [x.codigo]) }}</b>
              <small>{{ x.sku }} · {{ t('{0} per pack', [x.total]) }}</small>
            </div>
          </header>
          <p v-if="contenido(x).comun" class="vp-tenue">{{ contenido(x).comun }}</p>
          <div class="vp-contenido">
            <span v-for="c in contenido(x).items" :key="c.sku" class="vp-componente" :title="c.sku"><b>{{ tx(c.texto) }}</b><small>× {{ c.cantidad }}</small></span>
          </div>
        </article>
      </div>
    </template>
  </div>
</template>

<style scoped>
.vp-barra { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin: 4px 0 12px; }
.vp-barra .ayuda { flex: 1 1 360px; }
.vp-acciones { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.vp-vacio { display: flex; align-items: center; gap: 10px; padding: 24px; border: 1px dashed var(--linea); border-radius: var(--radio-panel); color: var(--tinta-3); }
.vp-matriz-caja { background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio-panel); box-shadow: var(--sombra); padding: 14px 16px; }
.vp-leyenda { display: flex; gap: 16px; flex-wrap: wrap; font-size: var(--t-sm); color: var(--tinta-2); margin-bottom: 10px; }
.vp-tenue { color: var(--tinta-3); font-size: var(--t-sm); }
.vp-leyenda .vp-tenue { margin-inline-start: auto; }
.vp-scroll { overflow-x: auto; }
.vp-matriz { border-collapse: separate; border-spacing: 4px; font-size: var(--t-sm); }
.vp-matriz thead th { font-size: var(--t-xs); font-weight: 700; color: var(--tinta-2); text-align: center; padding: 4px 6px; background: var(--superficie-2); border-radius: 6px; min-width: 76px; }
.vp-matriz thead th.vp-cab-fila { text-align: start; background: none; color: var(--tinta-3); text-transform: uppercase; letter-spacing: 0.05em; }
.vp-valor-fila { text-align: start; font-weight: 650; padding: 4px 10px 4px 2px; white-space: nowrap; color: var(--tinta); }
.vp-matriz td { padding: 0; text-align: center; }
.vp-celda { display: flex; flex-direction: column; align-items: center; gap: 1px; padding: 6px 8px; border-radius: 8px;
  background: var(--acento-claro); border: 1px solid var(--acento-medio); color: var(--acento-texto); }
.vp-celda.inactiva { background: var(--superficie-2); border-color: var(--linea); color: var(--tinta-3); text-decoration: line-through; }
.vp-sku { font-family: var(--mono); font-size: var(--t-xs); font-weight: 650; white-space: nowrap; }
.vp-marcas { display: inline-flex; gap: 3px; min-height: 12px; opacity: 0.75; }
.vp-hueco { display: block; padding: 10px 8px; border: 1px dashed var(--linea); border-radius: 8px; color: var(--tinta-3); }
.vp-total { font-weight: 700; color: var(--tinta-2); font-variant-numeric: tabular-nums; }
.vp-sku-lista { font-family: var(--mono); font-weight: 650; }
.vp-titulo { margin: 22px 0 10px; display: flex; align-items: center; gap: 8px; }
.vp-titulo .cuenta { font-size: var(--t-2xs); font-weight: 650; background: var(--linea-suave); border-radius: 10px; padding: 0 7px; color: var(--tinta-2); }
.vp-packs { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.vp-pack { background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio-panel); padding: 14px 16px; box-shadow: var(--sombra); display: flex; flex-direction: column; gap: 8px; }
.vp-pack header { display: flex; gap: 10px; align-items: center; }
.vp-pack header small { display: block; color: var(--tinta-3); font-size: var(--t-xs); font-family: var(--mono); }
.vp-pack-id { font-family: var(--mono); font-weight: 750; background: var(--acento-claro); color: var(--acento-texto); border-radius: 8px; padding: 6px 9px; }
.vp-contenido { display: flex; flex-wrap: wrap; gap: 6px; }
.vp-componente { display: inline-flex; align-items: baseline; gap: 4px; border: 1px solid var(--linea); border-radius: 7px; padding: 3px 9px; background: var(--superficie-2); }
.vp-componente small { color: var(--tinta-3); font-variant-numeric: tabular-nums; }
</style>
