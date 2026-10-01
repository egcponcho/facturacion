import { t } from '../i18n/index.js'
import { ref } from 'vue'
import { api } from '../api'
import { errorApi } from '../stores/ui'

// Catálogos para la ruta de un embarque, coherentes con su modo:
//  - puertos del tipo del embarque (puerto marítimo, aeropuerto o aduana terrestre);
//  - el destino es uno de los puertos de llegada del centro (el principal primero);
//  - transportistas del modo (o multimodales) que trabajan con la sociedad del centro.
export const MODOS = {
  MARITIMO: { nombre: t('Ocean'), icono: 'barco', puerto: t('Port'), unidad: 'container', doc: 'B/L', transportista: t('Shipping line') },
  AEREO: { nombre: t('Air'), icono: 'avion', puerto: t('Airport'), unidad: t('air waybill'), doc: 'AWB', transportista: t('Airline') },
  TERRESTRE: { nombre: t('Road'), icono: 'camion', puerto: t('Customs post'), unidad: 'truck', doc: t('Waybill'), transportista: t('Carrier') },
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
        valor: x.codigo, texto: `${x.codigo} · ${x.nombre}`, sub: t('{0} · arrives via {1}', [x.sociedad_id_txt || '', [x.puerto, x.puertos_txt].filter(Boolean).join(', ') || '—']),
        sociedad_id: x.sociedad_id, puertos: [x.puerto, ...(x.puertos_txt || '').split(', ')].filter(Boolean),
      }))
      transportistas.value = t.items.map((x) => ({
        valor: x.id, texto: `${x.codigo} · ${x.nombre}`, sub: `${MODOS[x.tipo]?.nombre || t('Multimodal')} · ${x.sociedades_txt || ''}`,
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
    return propios.length ? propios.map((p, i) => ({ ...p, sub: i === 0 ? t('main port of the plant') : t('alternate port of the plant') })) : delModo
  }
  function transportistasDe(modo, centro) {
    const c = centroDe(centro)
    return transportistas.value.filter((t) => (t.tipo === modo || t.tipo === 'MULTIMODAL') && (!c || !t.sociedades.length || t.sociedades.includes(c.sociedad_id)))
  }
  return { puertos, centros, transportistas, cargarRutas, puertosDe, destinosDe, transportistasDe, centroDe }
}
