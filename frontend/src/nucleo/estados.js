// Estados de los documentos en un solo lugar (el servidor los define en
// backend/app/core/estados.py). Cada estado: [texto, tono de la etiqueta].
// Un mismo código puede leerse distinto según el documento (p. ej. un embarque
// anulado frente a una factura cancelada): va en POR_TIPO.
import { t } from '@/i18n/index.js'
import { sesion } from '@/stores/sesion.js'

export const ESTADOS = {
  BORRADOR: [t('Draft'), 'neutro'],
  EN_CORRECCION: [t('In correction'), 'aviso'],
  FINALIZADA: [t('Finalized'), 'ok'],
  FINALIZADO: [t('Finalized'), 'ok'],
  CANCELADA: [t('Cancelled'), 'error'],
  CANCELADO: [t('Cancelled'), 'error'],
  DISPONIBLE: [t('Available'), 'ok'],
  PARCIAL: [t('Partial'), 'aviso'],
  FACTURADA: [t('Invoiced'), 'neutro'],
  NO_DISPONIBLE: [t('Not available'), 'error'],
  SIN_CAJA: [t('Not packed'), 'error'],
  COMPLETO: [t('Packed'), 'ok'],
  CONFIRMADA: [t('Confirmed'), 'ok'],
  PLANIFICADO: [t('Planned'), 'neutro'],
  EN_TRANSITO: [t('In transit'), 'info'],
  ARRIBADO: [t('Arrived'), 'info'],
  ENTREGADO: [t('Delivered'), 'ok'],
  RECIBIDO: [t('Received'), 'ok'],
  // Orden de compra
  EN_APROBACION: [t('Pending approval'), 'aviso'],
  RECHAZADA: [t('Rejected'), 'error'],
  APROBADA: [t('Approved'), 'ok'],
  CERRADA: [t('Closed'), 'neutro'],
  // Liberación de la OC (estados universales)
  RELEASED: [t('Released'), 'ok'],
  PENDING: [t('Not released'), 'aviso'],
  // Ficha técnica y clasificación del producto
  borrador: [t('Draft'), 'neutro'],
  sugerida: [t('Draft · complete'), 'neutro'],
  revision: [t('In review'), 'info'],
  aprobado: [t('Approved'), 'ok'],
  corregido: [t('Approved'), 'ok'],
  observado: [t('Returned'), 'aviso'],
}

const POR_TIPO = {
  embarque: { CANCELADO: [t('Called off'), 'error'] },
  avance: {
    SIN_FACTURAR: [t('Not invoiced'), 'neutro'],
    FACTURADA_PARCIAL: [t('Partly invoiced'), 'aviso'],
    FACTURADA: [t('Fully invoiced'), 'info'],
    EMBARCADA_PARCIAL: [t('Partly shipped'), 'info'],
    EN_TRANSITO: [t('In transit'), 'info'],
    RECIBIDA_PARCIAL: [t('Partly received'), 'aviso'],
    RECIBIDA: [t('Fully received'), 'ok'],
  },
  // Documentos comerciales, su cobro y los pagos
  documento: { BORRADOR: [t('Draft'), 'neutro'], EMITIDO: [t('Issued'), 'ok'], ANULADO: [t('Voided'), 'error'] },
  cobro: {
    PENDIENTE: [t('Unpaid'), 'aviso'],
    PARCIAL: [t('Partly paid'), 'info'],
    PAGADO: [t('Paid'), 'ok'],
    VENCIDO: [t('Overdue'), 'error'],
    APLICADA: [t('Fully applied'), 'ok'],
  },
  pago: { REGISTRADO: [t('Registered'), 'ok'], ANULADO: [t('Voided'), 'error'] },
  // Recepción en bodega de cada contenedor
  recepcion: { PENDIENTE: [t('Not received'), 'neutro'], EN_RECEPCION: [t('Being received'), 'aviso'], RECIBIDA: [t('Received'), 'ok'] },
}

// Cómo viene de fábrica
export const estadoFabrica = (codigo, tipo) => POR_TIPO[tipo]?.[codigo] || ESTADOS[codigo] || [codigo, 'neutro']

// Etiqueta y color que eligió la empresa (Configuración → Empresa → Estados)
const propio = (codigo, tipo) => (tipo && sesion.usuario?.organizacion?.estados?.[tipo]?.[codigo]) || null

export const estado = (codigo, tipo) => {
  const base = estadoFabrica(codigo, tipo)
  const p = propio(codigo, tipo)
  return p ? [p.etiqueta || base[0], p.tono || base[1]] : base
}

// Opciones para filtros, en el orden que eligió la empresa (o el de fábrica)
const opciones = (tipo, codigos) => codigos
  .map((c, i) => [c, estado(c, tipo)[0], propio(c, tipo)?.orden ?? i + 1])
  .sort((a, b) => a[2] - b[2]).map(([c, texto]) => [c, texto])
const CODIGOS = {
  oc: ['BORRADOR', 'EN_APROBACION', 'RECHAZADA', 'APROBADA', 'CERRADA', 'CANCELADA'],
  embarque: ['PLANIFICADO', 'EN_TRANSITO', 'ARRIBADO', 'ENTREGADO', 'RECIBIDO', 'CANCELADO'],
}
export const estadosOC = () => opciones('oc', CODIGOS.oc)
export const estadosEmbarque = () => opciones('embarque', CODIGOS.embarque)
// Los hitos del embarque siguen su orden natural (salida, arribo, entrega…)
export const pasosEmbarque = () => CODIGOS.embarque.map((c) => [c, estado(c, 'embarque')[0]])
export const avancesOC = () => opciones('avance', Object.keys(POR_TIPO.avance))
export const estadosDocumento = () => opciones('documento', Object.keys(POR_TIPO.documento))
export const estadosCobro = () => opciones('cobro', Object.keys(POR_TIPO.cobro))
