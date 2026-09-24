import { createRouter, createWebHistory } from 'vue-router'
import { cargarSesion, esInterno, puede, sesion } from './stores/sesion'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { publica: true } },
  { path: '/', component: () => import('./views/InicioView.vue') },
  { path: '/ordenes', component: () => import('./views/OrdenesView.vue') },
  { path: '/facturas', component: () => import('./views/FacturasView.vue') },
  { path: '/facturas/:id', component: () => import('./views/FacturaView.vue'), props: true },
  { path: '/packing-lists/:id', component: () => import('./views/PackingListView.vue'), props: true },
  { path: '/plantillas', component: () => import('./views/PlantillasView.vue') },
  { path: '/transporte', component: () => import('./views/EmbarquesView.vue'), meta: { interno: true } },
  { path: '/transporte/embarques/:id', component: () => import('./views/EmbarqueView.vue'), props: true, meta: { interno: true } },
  { path: '/transporte/unidades/:id', component: () => import('./views/UnidadView.vue'), props: true, meta: { interno: true } },
  { path: '/importar', component: () => import('./views/ImportarView.vue'), meta: { interno: true } },
  { path: '/admin', component: () => import('./views/AdminView.vue'), meta: { admin: true } },
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
  if (!sesion.usuario) return { path: '/login', query: { volver: to.fullPath } }
  if (to.meta.interno && !esInterno()) return '/'
  if (to.meta.admin && !puede('admin')) return '/'
  return true
})
