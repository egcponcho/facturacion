import { createRouter, createWebHistory } from 'vue-router'
import { cargarSesion, puede, sesion } from './stores/sesion'
import { avisar } from './stores/ui'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { publica: true } },
  { path: '/', component: () => import('./views/DashboardView.vue') },
  { path: '/ordenes', component: () => import('./views/OrdenesView.vue') },
  { path: '/facturas', component: () => import('./views/FacturasView.vue') },
  { path: '/facturas/:id', component: () => import('./views/FacturaView.vue'), props: true },
  { path: '/packing-lists/:id', component: () => import('./views/PackingListView.vue'), props: true },
  { path: '/plantillas', component: () => import('./views/PlantillasView.vue') },
  // Rutas restringidas: cada una exige el permiso de su rol (el servidor
  // vuelve a comprobarlo en cada petición)
  { path: '/transporte', component: () => import('./views/EmbarquesView.vue'), meta: { permiso: 'transporte.gestionar' } },
  { path: '/transporte/embarques/:id', component: () => import('./views/EmbarqueView.vue'), props: true, meta: { permiso: 'transporte.gestionar' } },
  { path: '/importar', component: () => import('./views/ImportarView.vue'), meta: { permiso: 'oc.importar' } },
  { path: '/mantenimiento', component: () => import('./views/MantenimientoView.vue'), meta: { permiso: 'catalogos.ver' } },
  { path: '/seguimiento', component: () => import('./views/SeguimientoView.vue') },
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
