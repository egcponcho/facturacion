// Estados de los documentos en un solo lugar (el servidor los define en
// backend/app/core/estados.py). Cada estado: [texto, tono de la etiqueta].
// Un mismo código puede leerse distinto según el documento (p. ej. un embarque
// anulado frente a una factura cancelada): va en POR_TIPO.
import { t } from '@/i18n/index.js'

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
}

export const estado = (codigo, tipo) => POR_TIPO[tipo]?.[codigo] || ESTADOS[codigo] || [codigo, 'neutro']

// Opciones para filtros y pasos, en su orden
export const ESTADOS_OC = ['BORRADOR', 'EN_APROBACION', 'RECHAZADA', 'APROBADA', 'CERRADA', 'CANCELADA']
  .map((c) => [c, estado(c, 'oc')[0]])
export const ESTADOS_EMBARQUE = ['PLANIFICADO', 'EN_TRANSITO', 'ARRIBADO', 'ENTREGADO', 'RECIBIDO', 'CANCELADO']
  .map((c) => [c, estado(c, 'embarque')[0]])
export const AVANCES_OC = Object.keys(POR_TIPO.avance).map((c) => [c, estado(c, 'avance')[0]])
