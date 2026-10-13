import { t, tx } from '@/i18n/index.js'
import { singularPlural, valor, valores } from '@/nucleo/listas.js'
import { ref } from 'vue'
import { api } from '@/nucleo/api'
import { errorApi } from '@/stores/ui'

// Catálogos para la ruta de un embarque, coherentes con su modo:
//  - puertos del tipo del embarque (puerto marítimo, aeropuerto o aduana terrestre);
//  - el destino es uno de los puertos de llegada del centro (el principal primero);
//  - transportistas del modo (o multimodales) que trabajan con la sociedad del centro.

// Datos de un modo de transporte según la lista de la empresa (Datos maestros →
// Listas de valores → Transport modes): nombre, ícono y cómo se llaman su
// documento, sus puertos, sus transportistas y sus unidades de carga.
export function datosModo(codigo) {
  const m = valor('modo_transporte', codigo) || {}
  const [unidad, unidades] = singularPlural(m.etiqueta_unidad, `${t('Load unit')}|${t('Load units')}`)
  return {
    codigo, nombre: tx(m.nombre || codigo || ''), icono: m.icono || 'caja', unidad, unidades,
    puerto: tx(m.etiqueta_puerto || t('Port')), doc: tx(m.documento || t('Transport document')),
    transportista: tx(m.etiqueta_transportista || t('Carrier')),
  }
}
// Ícono de las unidades de carga del modo (el barco lleva contenedores)
export const iconoUnidad = (codigo) => (datosModo(codigo).icono === 'barco' ? 'contenedor' : datosModo(codigo).icono)
export const modosTransporte = () => valores('modo_transporte').map((m) => datosModo(m.codigo))
export const modoInicial = () => valores('modo_transporte')[0]?.codigo || ''

export function useRutas() {
  const puertos = ref([])
  const centros = ref([])
  const transportistas = ref([])

  async function cargarRutas() {
    if (puertos.value.length) return
    try {
      const [p, c, tr] = await Promise.all([
        api.get('/catalogos/puertos', { size: 200, activo: true }),
        api.get('/catalogos/centros', { size: 200 }),
        api.get('/catalogos/transportistas', { size: 200, activo: true }),
      ])
      puertos.value = p.items.map((x) => ({ valor: x.codigo, texto: `${x.codigo} · ${x.nombre}`, sub: x.pais, tipo: x.tipo }))
      centros.value = c.items.map((x) => ({
        valor: x.codigo, texto: `${x.codigo} · ${x.nombre}`, sub: t('{0} · arrives via {1}', [x.sociedad_id_txt || '', [x.puerto, x.puertos_txt].filter(Boolean).join(', ') || '—']),
        sociedad_id: x.sociedad_id, puertos: [x.puerto, ...(x.puertos_txt || '').split(', ')].filter(Boolean),
      }))
      transportistas.value = tr.items.map((x) => ({
        valor: x.id, texto: `${x.codigo} · ${x.nombre}`, sub: `${valor('modo_transporte', x.tipo) ? datosModo(x.tipo).nombre : t('Multimodal')} · ${x.sociedades_txt || ''}`,
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
