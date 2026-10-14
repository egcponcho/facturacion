<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { sesion } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { fmtCant, fmtFecha, fmtNum, porUnidadTxt } from '@/nucleo/utils'

// Existencias por bodega: lo que entró a cada bodega o bodega fiscal con las
// recepciones de los contenedores, por artículo y almacén. Lo dañado se recibe
// pero no está disponible. Cada fila se abre en sus ingresos (kardex).
const datos = ref({ items: [], bodegas: [], truncado: false })
const filtros = reactive({ centro: '', q: '' })
const cargando = ref(false)
const kardex = reactive({})

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/existencias', { centro: filtros.centro || undefined, q: filtros.q || undefined, proveedor_id: sesion.proveedorId || undefined })
  } catch (err) {
    errorApi(err)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)
watch(() => [filtros.centro, sesion.proveedorId], cargar)
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(cargar, 300)
}
const clave = (f) => `${f.centro}|${f.almacen || ''}|${f.codigo}|${f.talla || ''}|${f.unidad}|${f.proveedor_id}`
async function abrir(f) {
  const k = clave(f)
  if (kardex[k]) return
  try {
    kardex[k] = await api.get('/existencias/movimientos', { centro: f.centro, codigo: f.codigo, talla: f.talla || undefined, almacen: f.almacen || undefined })
  } catch (err) {
    errorApi(err)
  }
}
const opcionesBodega = computed(() => datos.value.bodegas.map((b) => ({ valor: b.centro, texto: `${b.centro} · ${b.nombre || ''}` })))
const TIPOS = { CONTEO: t('Count'), AJUSTE: t('Adjustment'), SIN_CONTEO: t('Confirmed without counting') }
const columnas = [
  { clave: 'centro', texto: t('Warehouse'), fija: true, prioridad: 1, textoValor: (v, f) => `${v} · ${f?.centro_nombre || ''}` },
  { clave: 'codigo', texto: t('Item'), prioridad: 1 },
  { clave: 'descripcion', texto: t('Description'), prioridad: 3 },
  { clave: 'proveedor', texto: t('Supplier'), prioridad: 3 },
  { clave: 'almacen', texto: t('Storage location'), prioridad: 3 },
  { clave: 'recibido', texto: t('Received'), num: true, prioridad: 2 },
  { clave: 'danado', texto: t('Damaged'), num: true, prioridad: 2 },
  { clave: 'disponible', texto: t('Available'), num: true, prioridad: 1 },
  { clave: 'unidad', texto: t('Unit'), prioridad: 2 },
  { clave: 'ultimo_ingreso', texto: t('Last receipt'), prioridad: 3, textoValor: (v) => fmtFecha(v) },
]
// Datos de otros usuarios: se vuelven a pedir solo cuando cambian (nucleo/cambios.js)
alCambiar(() => cargar(), ['/existencias'])
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Stock by warehouse') }}</h1>
      <p>{{ t('What entered each warehouse or bonded warehouse with the container receipts, by item. Damaged units are received but not available. Open a row to see its receipts.') }}</p>
    </div>
  </div>

  <div v-if="datos.bodegas.length" class="tarjetas-resumen mb">
    <button v-for="b in datos.bodegas" :key="b.centro" type="button" class="tarjeta-resumen" :class="{ activa: filtros.centro === b.centro }"
            @click="filtros.centro = filtros.centro === b.centro ? '' : b.centro">
      <span class="eyebrow">{{ tx(b.centro) }}</span>
      <b>{{ tx(b.nombre || b.centro) }}</b>
      <span class="ayuda">{{ t('{0} items', [fmtNum(b.articulos)]) }} · {{ t('available {0}', [porUnidadTxt(b.por_unidad, 'disponible')]) }}</span>
    </button>
  </div>

  <p v-if="datos.truncado" class="nota aviso mb"><Icono nombre="alerta" />{{ t('Only the first rows are shown: filter by warehouse or search an item.') }}</p>

  <TablaDatos tabla="existencias" :columnas="columnas" :filas="datos.items" :clave-fila="clave" :cargando="cargando" expandible
              :etiqueta="t('Stock by warehouse')" @expandir="abrir">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="t('Search item, style, PO or supplier')" :aria-label="t('Search')" @input="buscar" />
      </label>
      <SelectBusqueda v-model="filtros.centro" :opciones="opcionesBodega" :vacio="t('All warehouses')" :etiqueta="t('Warehouse')" />
    </template>
    <template #celda-centro="{ fila: f }"><b class="codigo">{{ tx(f.centro) }}</b><span class="sub">{{ tx(f.centro_nombre || '') }}</span></template>
    <template #celda-codigo="{ fila: f }"><span class="codigo">{{ tx(f.codigo) }}</span><template v-if="f.talla"> · {{ tx(f.talla) }}</template><span class="sub">{{ tx([f.estilo, f.color].filter(Boolean).join(' · ')) }}</span></template>
    <template #celda-recibido="{ fila: f }">{{ fmtCant(f.recibido) }}</template>
    <template #celda-danado="{ fila: f }"><span :class="{ 'texto-aviso': f.danado > 0 }">{{ fmtCant(f.danado) }}</span></template>
    <template #celda-disponible="{ fila: f }"><b>{{ fmtCant(f.disponible) }}</b></template>
    <template #celda-ultimo_ingreso="{ fila: f }">{{ fmtFecha(f.ultimo_ingreso) }}</template>
    <template #detalle="{ fila: f }">
      <ul v-if="kardex[clave(f)]" class="linea-tiempo">
        <li v-for="(m, i) in kardex[clave(f)]" :key="i">
          <span class="ayuda">{{ fmtFecha(m.fecha) }}<br />{{ tx(m.usuario || '') }}</span>
          <span>
            <b>{{ tx(TIPOS[m.tipo] || m.tipo) }}</b> · {{ fmtCant(m.cantidad) }}<template v-if="m.danada"> · {{ t('damaged {0}', [fmtCant(m.danada)]) }}</template>
            <span class="sub">
              <router-link :to="`/transporte/unidades/${m.unidad_id}/recepcion`" class="enlace">{{ tx(m.unidad) }}</router-link> ·
              <router-link :to="`/transporte/embarques/${m.embarque_id}`" class="enlace">{{ tx(m.embarque) }}</router-link> ·
              <router-link :to="`/packing-lists/${m.pl_id}`" class="enlace">{{ tx(m.pl) }}</router-link> · {{ tx(m.factura || '') }} · {{ t('PO {0}', [m.oc]) }}
            </span>
            <span v-if="m.observacion" class="sub">{{ tx(m.observacion) }}</span>
          </span>
        </li>
      </ul>
      <p v-else class="ayuda">{{ t('Loading…') }}</p>
    </template>
    <template #vacio>
      <Icono nombre="caja" :tam="28" />
      <p>{{ t('No receipts yet. Stock enters when a load unit is received at a warehouse.') }}</p>
    </template>
  </TablaDatos>
</template>

<style scoped>
.tarjetas-resumen { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.tarjeta-resumen { display: flex; flex-direction: column; gap: 2px; text-align: left; padding: 12px 14px; border: 1px solid var(--linea); border-radius: 10px;
  background: var(--superficie); color: inherit; font: inherit; cursor: pointer; min-height: 44px; }
.tarjeta-resumen:hover { border-color: var(--borde-hover); }
.tarjeta-resumen.activa { border-color: var(--acento); box-shadow: 0 0 0 1px var(--acento); }
</style>
