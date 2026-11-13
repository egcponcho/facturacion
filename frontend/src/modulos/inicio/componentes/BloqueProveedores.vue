<script setup>
import { t, tx } from '@/i18n/index.js'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { elegirProveedor } from '@/stores/sesion'
import { fmtMoneda } from '@/nucleo/utils'

// Por proveedor (equipo interno): saldo por facturar y documentos de cada uno.
// Un clic en la fila filtra todo el sistema por ese proveedor.
defineProps({ proveedores: { type: Array, required: true } })
const montosTxt = (m) => (m === null || m === undefined ? '—' : m.length ? m.map((x) => fmtMoneda(x.valor, x.moneda)).join(' · ') : '—')
const columnasProveedores = [
  { clave: 'nombre', texto: t('Supplier'), fija: true, prioridad: 1 },
  // Un monto por moneda (nunca sumados); para ordenar y filtrar, el de la moneda principal
  { clave: 'por_facturar', texto: t('To invoice'), num: true, prioridad: 2, valor: (p) => (p.por_facturar ? p.por_facturar[0]?.valor ?? 0 : null),
    textoValor: (v, p) => montosTxt(p?.por_facturar), exporta: (p) => montosTxt(p.por_facturar) },
  { clave: 'en_proceso', texto: t('In process'), num: true, prioridad: 2 },
  { clave: 'pl_abiertos', texto: t('Open PLs'), num: true, prioridad: 2 },
  { clave: 'listas', texto: t('Ready'), num: true, prioridad: 3 },
  { clave: 'en_camino', texto: t('On the way'), num: true, prioridad: 3 },
]
</script>

<template>
<section class="panel">
  <div class="panel-cabeza"><div><h2>{{ t('By supplier') }}</h2><p>{{ t('Click one to filter the whole system.') }}</p></div></div>
  <TablaDatos tabla="inicio_proveedores" :columnas="columnasProveedores" :filas="proveedores" :vistas-guardadas="false" fila-clicable
              orden-inicial="nombre:asc" :etiqueta="t('By supplier')" @fila="(p) => elegirProveedor(p.id)">
    <template #celda-nombre="{ fila: p }"><span class="principal-celda">{{ tx(p.nombre) }}</span></template>
    <template #celda-por_facturar="{ fila: p }">{{ tx(montosTxt(p.por_facturar)) }}</template>
    <template #celda-en_proceso="{ fila: p }"><span :title="t('Invoices in draft or correction')">{{ tx(p.en_proceso || '—') }}</span></template>
    <template #celda-pl_abiertos="{ fila: p }"><span :class="{ 'etiqueta aviso': p.pl_abiertos }">{{ tx(p.pl_abiertos || '—') }}</span></template>
    <template #celda-listas="{ fila: p }"><span :class="{ 'etiqueta ok': p.listas }" :title="t('Invoices ready to ship')">{{ tx(p.listas || '—') }}</span></template>
    <template #celda-en_camino="{ fila: p }"><span :title="t('Packing lists in transit or arrived')">{{ tx(p.en_camino || '—') }}</span></template>
  </TablaDatos>
</section>
</template>
