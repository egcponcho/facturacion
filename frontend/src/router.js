import { t } from '@/i18n/index.js'
import { createRouter, createWebHistory } from 'vue-router'
import { cargarSesion, puede, sesion } from '@/stores/sesion'
import { avisar, ui } from '@/stores/ui'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/modulos/acceso/vistas/LoginView.vue'), meta: { publica: true } },
  { path: '/', component: () => import('@/modulos/inicio/vistas/DashboardView.vue') },
  { path: '/ordenes', component: () => import('@/modulos/compras/vistas/OrdenesView.vue'), meta: { permiso: 'oc.ver' } },
  { path: '/facturas', component: () => import('@/modulos/facturacion/vistas/FacturasView.vue'), meta: { permiso: 'factura.ver' } },
  { path: '/facturas/:id', component: () => import('@/modulos/facturacion/vistas/FacturaView.vue'), props: true, meta: { permiso: 'factura.ver' } },
  { path: '/packing-lists/:id', component: () => import('@/modulos/empaque/vistas/PackingListView.vue'), props: true, meta: { permiso: ['factura.ver', 'recepcion.registrar'] } },
  { path: '/productos', component: () => import('@/modulos/productos/vistas/ProductosView.vue'), meta: { permiso: 'producto.ver' } },
  { path: '/aranceles', component: () => import('@/modulos/clasificacion/vistas/ArancelesView.vue'), meta: { permiso: 'aranceles.ver' } },
  { path: '/familias', component: () => import('@/modulos/clasificacion/vistas/FamiliasView.vue'), meta: { permiso: 'clasificacion.ver' } },
  { path: '/productos/:id', component: () => import('@/modulos/productos/vistas/ProductoView.vue'), props: true, meta: { permiso: 'producto.ver' } },
  { path: '/plantillas', component: () => import('@/modulos/empaque/vistas/PlantillasView.vue'), meta: { permiso: ['plantilla.editar', 'pl.editar'] } },
  // Rutas restringidas: cada una exige el permiso de su rol (el servidor
  // vuelve a comprobarlo en cada petición)
  { path: '/transporte', component: () => import('@/modulos/transporte/vistas/EmbarquesView.vue'), meta: { permiso: 'transporte.gestionar' } },
  { path: '/transporte/embarques/:id', component: () => import('@/modulos/transporte/vistas/EmbarqueView.vue'), props: true, meta: { permiso: 'transporte.gestionar' } },
  { path: '/importar', component: () => import('@/modulos/compras/vistas/ImportarView.vue'), meta: { permiso: 'oc.importar' } },
  { path: '/mantenimiento', component: () => import('@/modulos/maestros/vistas/MantenimientoView.vue'), meta: { permiso: 'catalogos.ver' } },
  { path: '/leadtimes', component: () => import('@/modulos/transporte/vistas/LeadTimeView.vue'), meta: { permiso: 'catalogos.ver' } },
  { path: '/seguimiento', component: () => import('@/modulos/seguimiento/vistas/SeguimientoView.vue'), meta: { permiso: 'seguimiento.ver' } },
  { path: '/perfil', component: () => import('@/modulos/acceso/vistas/PerfilView.vue') },
  { path: '/bienvenida', name: 'bienvenida', component: () => import('@/modulos/acceso/vistas/BienvenidaView.vue'), meta: { sinMarco: true } },
  { path: '/admin', component: () => import('@/modulos/acceso/vistas/AdminView.vue'), meta: { permiso: 'admin' } },
  { path: '/empresa', component: () => import('@/modulos/empresa/vistas/EmpresaView.vue'), meta: { permiso: 'admin' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

// Barra de progreso fina mientras carga la página siguiente
router.beforeEach(() => { ui.navegando = true })
let precargado = false
router.afterEach(() => {
  ui.navegando = false
  if (sesion.usuario && !precargado) {
    precargado = true
    precargarPaginas()
  }
})
router.onError(() => { ui.navegando = false })

// Precarga en segundo plano las pantallas a las que el usuario puede ir: el
// primer clic ya no espera a descargar su código
export function precargarPaginas() {
  const pedir = () => {
    for (const r of router.getRoutes()) {
      const c = r.components?.default
      if (typeof c === 'function' && (!r.meta.permiso || puede(r.meta.permiso))) c().catch(() => {})
    }
  }
  if ('requestIdleCallback' in window) window.requestIdleCallback(pedir, { timeout: 4000 })
  else setTimeout(pedir, 1500)
}

router.beforeEach(async (to) => {
  if (!sesion.cargada) await cargarSesion()
  if (to.meta.publica) return sesion.usuario ? '/' : true
  if (!sesion.usuario) return { path: '/login', query: to.fullPath === '/' ? {} : { volver: to.fullPath } }
  // Con la contraseña temporal de la administración, primero el asistente inicial
  if (sesion.usuario.clave_temporal && to.name !== 'bienvenida') return { name: 'bienvenida' }
  if (!sesion.usuario.clave_temporal && to.name === 'bienvenida') return '/'
  if (to.meta.permiso && !puede(to.meta.permiso)) {
    avisar(t('You do not have access to that page.'), 'error')
    return '/'
  }
  return true
})
