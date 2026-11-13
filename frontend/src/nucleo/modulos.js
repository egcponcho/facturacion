import { t } from '@/i18n/index.js'
import { esInterno, puede, sesion } from '@/stores/sesion'

// Módulos del sistema: una sola entrada por módulo en el menú lateral y, adentro,
// sus apartados en una barra de pestañas (BarraModulo) con la acción principal
// del módulo a la derecha. Es la única lista: el menú, la barra y los datos
// maestros (qué catálogos son de qué módulo) salen de aquí.
//
// Cada apartado dice a dónde lleva (a), quién lo ve (permiso: uno o varios, basta
// uno) y qué direcciones son suyas (prefijos de ruta, o catálogos de datos
// maestros que se abren en /mantenimiento?catalogo=…). Con titulo, el encabezado
// de sus páginas no repite la pestaña (p. ej. «Configuración» → «Configuración de productos»).

// Grupos del menú lateral, en el orden de la cadena de abastecimiento: lo que se
// opera cada día, lo que se controla, los datos propios, los módulos que la
// empresa puede apagar y la configuración. Un módulo apagado (o sin permiso)
// desaparece del menú sin dejar el título de su grupo vacío.
export const GRUPOS = () => ({
  operacion: t('Operation'),
  control: t('Control'),
  datos: t('Data'),
  opcionales: t('Optional modules'),
  sistema: t('System'),
})

// Catálogos de datos maestros por módulo (los que no estén aquí van a Configuración)
export const CATALOGOS_DE = {
  productos: ['articulos', 'atributos', 'escalas', 'marcas', 'listas', 'dominios', 'acuerdos'],
  terceros: ['proveedores', 'sociedades', 'contactos', 'transportistas'],
  empaque: ['tipos_empaque', 'series'],
  transporte: ['centros', 'almacenes', 'puertos', 'regiones', 'tipos_unidad', 'liberaciones'],
  seguimiento: ['pasos_lt', 'leadtimes'],
  configuracion: ['paises'],
}

const catalogo = (clave, texto, primero, permiso = 'catalogos.ver') => ({
  a: `/mantenimiento?catalogo=${primero}`, texto, permiso, catalogos: CATALOGOS_DE[clave],
})

// Permisos de lectura de cada parte de la operación (también los usa Análisis)
const VE_ALGO = ['oc.ver', 'factura.ver', 'transporte.gestionar', 'producto.ver']

export const MODULOS = () => [
  { clave: 'inicio', texto: t('Home'), icono: 'inicio', a: '/', exacto: true, apartados: [] },

  // ---- Operación: compra → despacho → transporte → inventario ----
  {
    clave: 'compras', grupo: 'operacion', texto: t('Purchasing'), icono: 'ordenes',
    apartados: [
      // Cada módulo abre en su resumen: los indicadores del módulo (seguimiento/indicadores.py)
      { a: '/compras/resumen', texto: t('Summary'), permiso: 'oc.ver', exacto: true },
      { a: '/compras/solicitudes', texto: t('Requests'), permiso: 'solicitud.ver', prefijos: ['/compras/solicitudes'] },
      { a: '/ordenes', texto: t('Orders'), permiso: 'oc.ver', prefijos: ['/ordenes'] },
      { a: '/compras/pagos', texto: t('Invoices and payments'), permiso: 'pago.ver', prefijos: ['/compras/pagos'] },
      { a: '/importar', texto: t('Load orders'), permiso: 'oc.importar', prefijos: ['/importar'] },
    ],
    accion: { a: '/ordenes/nueva', texto: t('New PO'), permiso: 'oc.editar' },
  },
  {
    // La factura comercial del proveedor y sus listas de empaque forman un despacho
    clave: 'despacho', grupo: 'operacion', texto: t('Dispatch'), icono: 'factura',
    apartados: [
      { a: '/facturacion/resumen', texto: t('Summary'), permiso: 'factura.ver', exacto: true },
      { a: '/facturas', texto: t('Dispatches'), permiso: 'factura.ver', prefijos: ['/facturas', '/packing-lists'] },
    ],
  },
  {
    clave: 'transporte', grupo: 'operacion', texto: t('Transport'), icono: 'camion',
    apartados: [
      { a: '/logistica/resumen', texto: t('Summary'), permiso: ['transporte.gestionar', 'seguimiento.ver'], exacto: true },
      { a: '/transporte', texto: t('Shipments'), permiso: 'transporte.gestionar', prefijos: ['/transporte'] },
      catalogo('transporte', t('Places and units'), 'centros'),
    ],
  },
  {
    // Bodega: lo que llega y hay que contar, y lo ya recibido (diseño v3)
    clave: 'recepcion', grupo: 'operacion', texto: t('Receiving'), icono: 'bandeja',
    apartados: [
      { a: '/recepcion', texto: t('To receive'), permiso: ['recepcion.registrar', 'transporte.gestionar', 'inventario.ver'], prefijos: ['/recepcion'] },
    ],
  },
  {
    clave: 'inventario', grupo: 'operacion', texto: t('Inventory'), icono: 'caja',
    apartados: [
      { a: '/inventario', texto: t('Stock'), permiso: ['inventario.ver', 'recepcion.registrar'], prefijos: ['/inventario'] },
    ],
  },

  // ---- Control ----
  {
    clave: 'seguimiento', grupo: 'control', texto: t('Tracking'), icono: 'pulso',
    apartados: [
      { a: '/seguimiento', texto: t('By PO line'), permiso: 'seguimiento.ver', prefijos: ['/seguimiento'] },
      { a: '/leadtimes', texto: t('Lead times'), permiso: 'catalogos.ver', prefijos: ['/leadtimes'] },
      catalogo('seguimiento', t('Lead time steps'), 'pasos_lt'),
    ],
  },
  {
    clave: 'analisis', grupo: 'control', texto: t('Analysis'), icono: 'grafica',
    apartados: [
      { a: '/analisis/ejecutivo', texto: t('Executive dashboard'), permiso: ['oc.ver', 'factura.ver', 'transporte.gestionar'], prefijos: ['/analisis/ejecutivo'] },
      { a: '/tableros', texto: t('Indicators'), permiso: VE_ALGO, prefijos: ['/tableros'] },
      { a: '/reportes', texto: t('Reports'), permiso: VE_ALGO, prefijos: ['/reportes'] },
    ],
  },

  // ---- Datos propios de la empresa ----
  {
    clave: 'productos', grupo: 'datos', texto: t('Products'), icono: 'capas',
    apartados: [
      { a: '/productos', texto: t('Summary'), permiso: 'producto.ver', exacto: true },
      { a: '/productos/catalogo', texto: t('Catalog'), permiso: 'producto.ver', prefijos: ['/productos/catalogo', '/productos/nuevo'], patron: /^\/productos\/\d+/ },
      { a: '/productos/configuracion', texto: t('Families and attributes'), titulo: t('Products setup'), permiso: 'catalogos.ver',
        prefijos: ['/productos/configuracion', '/grupos-producto'], catalogos: CATALOGOS_DE.productos },
    ],
    accion: { a: '/productos/nuevo', texto: t('New product'), permiso: 'catalogos.crear' },
  },
  {
    // Proveedores, sociedades compradoras, contactos y transportistas: los terceros con que se trabaja
    clave: 'terceros', grupo: 'datos', texto: t('Third parties'), icono: 'usuarios',
    apartados: [
      { a: '/mantenimiento?catalogo=proveedores', texto: t('Suppliers'), permiso: 'catalogos.ver', catalogos: ['proveedores', 'contactos'] },
      { a: '/mantenimiento?catalogo=transportistas', texto: t('Carriers'), permiso: 'catalogos.ver', catalogos: ['transportistas'] },
      { a: '/mantenimiento?catalogo=sociedades', texto: t('Buying companies'), permiso: 'catalogos.ver', catalogos: ['sociedades'] },
    ],
  },
  {
    clave: 'empaque', grupo: 'datos', texto: t('Packing'), icono: 'archivador',
    apartados: [
      { a: '/empaque/recetas', texto: t('Recipes'), permiso: 'catalogos.ver', prefijos: ['/empaque'] },
      { a: '/plantillas', texto: t('Templates'), permiso: 'plantilla.editar', prefijos: ['/plantillas'] },
      catalogo('empaque', t('Packaging types and numbering'), 'tipos_empaque'),
    ],
  },

  // ---- Módulos que la empresa puede apagar (Configuración → Empresa → Módulos) ----
  {
    clave: 'etiquetas', grupo: 'opcionales', texto: t('Labels'), icono: 'etiqueta',
    apartados: [
      { a: '/etiquetas', texto: t('Print'), permiso: 'etiquetas.ver', exacto: true, prefijos: ['/etiquetas/trabajos'] },
      { a: '/etiquetas/disenos', texto: t('Designs'), permiso: 'etiquetas.ver', prefijos: ['/etiquetas/disenos'] },
      { a: '/etiquetas/configuracion', texto: t('Setup'), permiso: 'etiquetas.ver', interno: true, prefijos: ['/etiquetas/configuracion'] },
    ],
  },
  {
    // Comercio exterior (módulo «clasificacion»): sale de Productos para quien no importa
    clave: 'aduana', grupo: 'opcionales', texto: t('Customs'), icono: 'escudo',
    apartados: [
      { a: '/familias', texto: t('Classification'), permiso: 'clasificacion.ver', prefijos: ['/familias'] },
      { a: '/aranceles', texto: t('Tariff schedule'), permiso: 'aranceles.ver', prefijos: ['/aranceles'] },
    ],
  },

  // ---- Sistema ----
  {
    clave: 'configuracion', grupo: 'sistema', texto: t('Settings'), icono: 'engrane',
    apartados: [
      // Portada: todo lo que se configura, también lo de cada módulo, en un solo lugar
      { a: '/configuracion', texto: t('Overview'), permiso: ['admin', 'integraciones.ver', 'catalogos.ver'], exacto: true },
      { a: '/empresa', texto: t('Company'), permiso: 'admin', prefijos: ['/empresa'] },
      { a: '/admin', texto: t('Users and access'), permiso: 'admin', prefijos: ['/admin'] },
      { a: '/integraciones', texto: t('Integrations'), permiso: 'integraciones.ver', prefijos: ['/integraciones'] },
      catalogo('configuracion', t('Countries'), 'paises'),
      { a: '/plataforma', texto: t('Organizations'), plataforma: true, prefijos: ['/plataforma'] },
    ],
  },
]

// ¿Esta persona ve el apartado? (también lo usa la portada de Configuración)
export const visible = (x) => {
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
