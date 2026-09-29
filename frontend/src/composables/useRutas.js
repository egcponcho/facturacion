import { ref } from 'vue'
import { api } from '../api'
import { errorApi } from '../stores/ui'

// Catálogos para la ruta de un embarque, coherentes con su modo:
//  - puertos del tipo del embarque (puerto marítimo, aeropuerto o aduana terrestre);
//  - el destino es uno de los puertos de llegada del centro (el principal primero);
//  - transportistas del modo (o multimodales) que trabajan con la sociedad del centro.
export const MODOS = {
  MARITIMO: { nombre: 'Ocean', icono: 'barco', puerto: 'Port', unidad: 'container', doc: 'B/L', transportista: 'Shipping line' },
  AEREO: { nombre: 'Air', icono: 'avion', puerto: 'Airport', unidad: 'air waybill', doc: 'AWB', transportista: 'Airline' },
  TERRESTRE: { nombre: 'Road', icono: 'camion', puerto: 'Customs post', unidad: 'truck', doc: 'Waybill', transportista: 'Carrier' },
}

export function useRutas() {
  const puertos = ref([])
  const centros = ref([])
  const transportistas = ref([])

  async function cargarRutas() {
    if (puertos.value.length) return
    try {
      const [p, c, t] = await Promise.all([
        api.get('/catalogos/puertos', { size: 200, activo: true }),
        api.get('/catalogos/centros', { size: 200 }),
        api.get('/catalogos/transportistas', { size: 200, activo: true }),
      ])
      puertos.value = p.items.map((x) => ({ valor: x.codigo, texto: `${x.codigo} · ${x.nombre}`, sub: x.pais, tipo: x.tipo }))
      centros.value = c.items.map((x) => ({
        valor: x.codigo, texto: `${x.codigo} · ${x.nombre}`, sub: `${x.sociedad_id_txt || ''} · arrives via ${[x.puerto, x.puertos_txt].filter(Boolean).join(', ') || '—'}`,
        sociedad_id: x.sociedad_id, puertos: [x.puerto, ...(x.puertos_txt || '').split(', ')].filter(Boolean),
      }))
      transportistas.value = t.items.map((x) => ({
        valor: x.id, texto: `${x.codigo} · ${x.nombre}`, sub: `${MODOS[x.tipo]?.nombre || 'Multimodal'} · ${x.sociedades_txt || ''}`,
        tipo: x.tipo, sociedades: x.sociedades || [],
      }))
    } catch (e) {
      errorApi(e)
    }
  }

  const puertosDe = (modo) => puertos.value.filter((p) => p.tipo === modo)
  const centroDe = (codigo) => centros.value.find((c) => c.valor === codigo)
  // Puertos de llegada del centro para ese modo (el principal primero)
  function destinosDe(modo, centro) {
    const delModo = puertosDe(modo)
    const c = centroDe(centro)
    if (!c) return delModo
    const propios = c.puertos.map((cod) => delModo.find((p) => p.valor === cod)).filter(Boolean)
    return propios.length ? propios.map((p, i) => ({ ...p, sub: i === 0 ? 'main port of the plant' : 'alternate port of the plant' })) : delModo
  }
  function transportistasDe(modo, centro) {
    const c = centroDe(centro)
    return transportistas.value.filter((t) => (t.tipo === modo || t.tipo === 'MULTIMODAL') && (!c || t.sociedades.includes(c.sociedad_id)))
  }
  return { puertos, centros, transportistas, cargarRutas, puertosDe, destinosDe, transportistasDe, centroDe }
}
