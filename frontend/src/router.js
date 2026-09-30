import { createRouter, createWebHistory } from 'vue-router'
import { cargarSesion, puede, sesion } from './stores/sesion'
import { avisar } from './stores/ui'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { publica: true } },
  { path: '/', component: () => import('./views/DashboardView.vue') },
  { path: '/ordenes', component: () => import('./views/OrdenesView.vue'), meta: { permiso: 'oc.ver' } },
  { path: '/facturas', component: () => import('./views/FacturasView.vue'), meta: { permiso: 'oc.ver' } },
  { path: '/facturas/:id', component: () => import('./views/FacturaView.vue'), props: true },
  { path: '/packing-lists/:id', component: () => import('./views/PackingListView.vue'), props: true },
  { path: '/productos', component: () => import('./views/ProductosView.vue'), meta: { permiso: 'producto.ver' } },
  { path: '/aranceles', component: () => import('./views/ArancelesView.vue'), meta: { permiso: 'aranceles.ver' } },
  { path: '/productos/:id', component: () => import('./views/ProductoView.vue'), props: true, meta: { permiso: 'producto.ver' } },
  { path: '/plantillas', component: () => import('./views/PlantillasView.vue'), meta: { permiso: 'plantilla.editar' } },
  // Rutas restringidas: cada una exige el permiso de su rol (el servidor
  // vuelve a comprobarlo en cada petición)
  { path: '/transporte', component: () => import('./views/EmbarquesView.vue'), meta: { permiso: 'transporte.gestionar' } },
  { path: '/transporte/embarques/:id', component: () => import('./views/EmbarqueView.vue'), props: true, meta: { permiso: 'transporte.gestionar' } },
  { path: '/importar', component: () => import('./views/ImportarView.vue'), meta: { permiso: 'oc.importar' } },
  { path: '/mantenimiento', component: () => import('./views/MantenimientoView.vue'), meta: { permiso: 'catalogos.ver' } },
  { path: '/seguimiento', component: () => import('./views/SeguimientoView.vue'), meta: { permiso: 'seguimiento.ver' } },
  { path: '/admin', component: () => import('./views/AdminView.vue'), meta: { permiso: 'admin' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  if (!sesion.cargada) await cargarSesion()
  if (to.meta.publica) return sesion.usuario ? '/' : true
  if (!sesion.usuario) return { path: '/login', query: to.fullPath === '/' ? {} : { volver: to.fullPath } }
  if (to.meta.permiso && !puede(to.meta.permiso)) {
    avisar('You do not have access to that page.', 'error')
    return '/'
  }
  return true
})
