import { api } from '@/nucleo/api'

// Búsquedas en el servidor para las listas de elección del módulo (artículo,
// producto, OC): devuelven opciones { valor, texto, sub } de SelectBusqueda.
export async function buscarArticulos(q) {
  const r = await api.get('/etiquetas/articulos', { q, size: 30 })
  return r.items.map((a) => ({ valor: a.id, texto: a.sku, sub: [a.descripcion, a.color, a.talla, a.familia].filter(Boolean).join(' · ') }))
}

export async function buscarProductos(q) {
  const r = await api.get('/productos', { q, size: 30 })
  return (r.items || []).map((p) => ({ valor: p.id, texto: p.estilo || p.nombre, sub: [p.nombre, p.marca, p.proveedor].filter(Boolean).join(' · ') }))
}

export async function buscarOrdenes(q) {
  const r = await api.get('/ordenes', { q, size: 30, solo_disponible: false })
  return (r.items || []).map((o) => ({ valor: o.id, texto: o.numero, sub: [o.proveedor_nombre || o.proveedor, o.fecha].filter(Boolean).join(' · ') }))
}
