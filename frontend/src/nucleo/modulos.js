import { t } from '@/i18n/index.js'
import { esInterno, puede, sesion } from '@/stores/sesion'

// Módulos del sistema: una sola entrada por módulo en el menú lateral y, adentro,
// sus apartados en una barra de pestañas (BarraModulo) con la acción principal
// del módulo a la derecha. Es la única lista: el menú, la barra y los datos
// maestros (qué catálogos son de qué módulo) salen de aquí.
//
// Cada apartado dice a dónde lleva (a), quién lo ve (permiso: uno o varios, basta
// uno) y qué direcciones son suyas (prefijos de ruta, o catálogos de datos
// maestros que se abren en /mantenimiento?catalogo=…).

// Catálogos de datos maestros por módulo (los que no estén aquí van a Configuración)
export const CATALOGOS_DE = {
  productos: ['articulos', 'prepacks', 'marcas', 'atributos_variante', 'escalas', 'categorias', 'grupos', 'listas', 'dominios', 'acuerdos'],
  compras: ['proveedores', 'sociedades', 'contactos'],
  facturacion: ['tipos_empaque', 'series'],
  logistica: ['centros', 'almacenes', 'puertos', 'regiones', 'transportistas', 'tipos_unidad', 'liberaciones', 'pasos_lt', 'leadtimes'],
  configuracion: ['paises'],
}

const catalogo = (clave, texto, primero, permiso = 'catalogos.ver') => ({
  a: `/mantenimiento?catalogo=${primero}`, texto, permiso, catalogos: CATALOGOS_DE[clave],
})

export const MODULOS = () => [
  { clave: 'inicio', texto: t('Home'), icono: 'tablero', a: '/', exacto: true, apartados: [] },
  {
    clave: 'compras', texto: t('Purchasing'), icono: 'ordenes',
    apartados: [
      // Cada módulo abre en su resumen: los indicadores del módulo (seguimiento/indicadores.py)
      { a: '/compras/resumen', texto: t('Summary'), permiso: 'oc.ver', exacto: true },
      { a: '/ordenes', texto: t('Purchase orders'), permiso: 'oc.ver', prefijos: ['/ordenes'] },
      { a: '/importar', texto: t('Load purchase orders'), permiso: 'oc.importar', prefijos: ['/importar'] },
      catalogo('compras', t('Suppliers and companies'), 'proveedores'),
    ],
    accion: { a: '/ordenes/nueva', texto: t('New PO'), permiso: 'oc.editar' },
  },
  {
    clave: 'facturacion', texto: t('Invoicing'), icono: 'factura',
    apartados: [
      { a: '/facturacion/resumen', texto: t('Summary'), permiso: 'factura.ver', exacto: true },
      { a: '/facturas', texto: t('Invoices and packing lists'), permiso: 'factura.ver', prefijos: ['/facturas', '/packing-lists'] },
      { a: '/empaque/recetas', texto: t('Packing recipes'), permiso: 'catalogos.ver', prefijos: ['/empaque'] },
      { a: '/plantillas', texto: t('Packing templates'), permiso: 'plantilla.editar', prefijos: ['/plantillas'] },
      catalogo('facturacion', t('Packaging types and numbering'), 'tipos_empaque'),
    ],
  },
  {
    clave: 'logistica', texto: t('Logistics'), icono: 'barco',
    apartados: [
      { a: '/logistica/resumen', texto: t('Summary'), permiso: ['transporte.gestionar', 'seguimiento.ver'], exacto: true },
      { a: '/transporte', texto: t('Shipments'), permiso: 'transporte.gestionar', prefijos: ['/transporte'] },
      { a: '/inventario', texto: t('Stock'), permiso: ['inventario.ver', 'recepcion.registrar'], prefijos: ['/inventario'] },
      { a: '/seguimiento', texto: t('Tracking'), permiso: 'seguimiento.ver', prefijos: ['/seguimiento'] },
      { a: '/leadtimes', texto: t('Lead times'), permiso: 'catalogos.ver', prefijos: ['/leadtimes'] },
      catalogo('logistica', t('Places and carriers'), 'centros'),
    ],
  },
  {
    clave: 'productos', texto: t('Products'), icono: 'caja',
    apartados: [
      { a: '/productos', texto: t('Summary'), permiso: 'producto.ver', exacto: true },
      { a: '/productos/catalogo', texto: t('Catalog'), permiso: 'producto.ver', prefijos: ['/productos/catalogo', '/productos/nuevo'], patron: /^\/productos\/\d+/ },
      { a: '/familias', texto: t('Classification'), permiso: ['clasificacion.ver', 'aranceles.ver'], prefijos: ['/familias', '/aranceles'] },
      { a: '/productos/configuracion', texto: t('Setup'), permiso: 'catalogos.ver', prefijos: ['/productos/configuracion', '/grupos-producto'],
        catalogos: CATALOGOS_DE.productos },
    ],
    accion: { a: '/productos/nuevo', texto: t('New product'), permiso: 'catalogos.crear' },
  },
  {
    clave: 'etiquetas', texto: t('Labels'), icono: 'etiqueta',
    apartados: [
      { a: '/etiquetas', texto: t('Print'), permiso: 'etiquetas.ver', exacto: true, prefijos: ['/etiquetas/trabajos'] },
      { a: '/etiquetas/disenos', texto: t('Designs'), permiso: 'etiquetas.ver', prefijos: ['/etiquetas/disenos'] },
      { a: '/etiquetas/configuracion', texto: t('Setup'), permiso: 'etiquetas.ver', interno: true, prefijos: ['/etiquetas/configuracion'] },
    ],
  },
  {
    clave: 'analisis', texto: t('Analysis'), icono: 'grafica',
    apartados: [
      { a: '/tableros', texto: t('Indicators'), permiso: ['oc.ver', 'factura.ver', 'transporte.gestionar', 'producto.ver'], prefijos: ['/tableros'] },
      { a: '/reportes', texto: t('Reports'), permiso: ['oc.ver', 'factura.ver', 'transporte.gestionar', 'producto.ver'], prefijos: ['/reportes'] },
    ],
  },
  {
    clave: 'configuracion', texto: t('Settings'), icono: 'engrane',
    apartados: [
      { a: '/empresa', texto: t('Company'), permiso: 'admin', prefijos: ['/empresa'] },
      { a: '/admin', texto: t('Users and access'), permiso: 'admin', prefijos: ['/admin'] },
      { a: '/integraciones', texto: t('Integrations'), permiso: 'integraciones.ver', prefijos: ['/integraciones'] },
      catalogo('configuracion', t('Countries'), 'paises'),
      { a: '/plataforma', texto: t('Organizations'), plataforma: true, prefijos: ['/plataforma'] },
    ],
  },
]

const visible = (x) => {
  if (x.plataforma) return !!sesion.usuario?.plataforma
  if (x.interno && !esInterno()) return false
  return !x.permiso || puede(x.permiso)
}

// Los módulos que esta persona ve, cada uno con sus apartados visibles; el módulo
// se abre en su primer apartado visible
export function modulosVisibles() {
  return MODULOS()
    .map((m) => ({ ...m, apartados: m.apartados.filter(visible), accion: m.accion && visible(m.accion) ? m.accion : null }))
    .filter((m) => m.clave === 'inicio' || m.apartados.length)
    .map((m) => ({ ...m, a: m.a || m.apartados[0].a }))
}

// ¿La dirección es de este apartado?
export function esDe(x, ruta) {
  const path = ruta.path
  if (x.catalogos && path === '/mantenimiento') return x.catalogos.includes(ruta.query.catalogo || 'articulos')
  if (x.exacto && path === x.a) return true
  if (x.patron && x.patron.test(path)) return true
  return (x.prefijos || []).some((p) => path === p || path.startsWith(`${p}/`))
}

// El módulo y el apartado de la página abierta
export function ubicar(modulos, ruta) {
  for (const m of modulos) {
    if (m.clave === 'inicio') {
      if (ruta.path === '/') return { modulo: m, apartado: null }
      continue
    }
    const ap = m.apartados.find((x) => esDe(x, ruta))
    if (ap) return { modulo: m, apartado: ap }
  }
  return { modulo: null, apartado: null }
}

// Los catálogos de datos maestros que van juntos con este (los del mismo módulo)
export function catalogosHermanos(tipo) {
  return Object.values(CATALOGOS_DE).find((l) => l.includes(tipo)) || null
}
