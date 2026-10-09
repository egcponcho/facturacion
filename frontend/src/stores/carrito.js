import { t } from '@/i18n/index.js'
import { reactive, watch } from 'vue'

// Order lines selected for invoicing. Kept while you navigate
// (sessionStorage) and always from a single supplier.
const previo = JSON.parse(sessionStorage.getItem('carrito') || 'null')
export const carrito = reactive(previo || { proveedorId: null, items: [] })

watch(carrito, (v) => sessionStorage.setItem('carrito', JSON.stringify(v)), { deep: true })

export function agregarPosiciones(oc, posiciones) {
  if (carrito.items.length && carrito.proveedorId !== oc.proveedor_id) {
    return { error: t('The selection has lines from another supplier. Invoice them or clear the selection first.') }
  }
  carrito.proveedorId = oc.proveedor_id
  let agregadas = 0
  let omitidas = 0
  for (const p of posiciones) {
    const cantidad = Number(p.a_facturar ?? p.disponible)
    if (p.estado === 'NO_DISPONIBLE' || p.disponible <= 0 || !(cantidad > 0)) {
      omitidas++
      continue
    }
    const datos = {
      posicion_id: p.id,
      oc_id: oc.id,
      oc_numero: oc.numero,
      centro: oc.centro,
      moneda: oc.moneda,
      posicion: p.posicion,
      codigo_sap: p.codigo_sap,
      estilo: p.estilo,
      color: p.color,
      talla: p.talla,
      unidad: p.unidad,
      inner_pack: p.inner_pack,
      precio: p.precio,
      disponible: p.disponible,
      cantidad: Math.min(cantidad, p.disponible),
      solo_factura_id: p.solo_factura_id,
      aviso: p.motivo,
    }
    const existente = carrito.items.find((i) => i.posicion_id === p.id)
    if (existente) Object.assign(existente, datos)
    else carrito.items.push(datos)
    agregadas++
  }
  return { agregadas, omitidas }
}

export function quitarPosicion(posicionId) {
  const i = carrito.items.findIndex((x) => x.posicion_id === posicionId)
  if (i >= 0) carrito.items.splice(i, 1)
  if (!carrito.items.length) carrito.proveedorId = null
}

export function quitarOC(ocId) {
  carrito.items = carrito.items.filter((x) => x.oc_id !== ocId)
  if (!carrito.items.length) carrito.proveedorId = null
}

export function vaciarCarrito() {
  carrito.items = []
  carrito.proveedorId = null
}
