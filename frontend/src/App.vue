<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Toasts from './components/Toasts.vue'
import { carrito } from './stores/carrito'
import { cerrarSesion, elegirProveedor, esInterno, puede, sesion } from './stores/sesion'
import { ui } from './stores/ui'

const route = useRoute()
const router = useRouter()

const navegacion = computed(() => {
  const items = [
    { to: '/', texto: 'Pendientes' },
    { to: '/ordenes', texto: 'Órdenes de compra' },
    { to: '/facturas', texto: 'Facturas y packing lists' },
    { to: '/plantillas', texto: 'Plantillas de caja' },
  ]
  if (esInterno()) {
    items.push({ to: '/transporte', texto: 'Transporte' }, { to: '/importar', texto: 'Importar OCs' })
  }
  if (puede('admin')) items.push({ to: '/admin', texto: 'Usuarios y proveedores' })
  return items
})

const activo = (to) => (to === '/' ? route.path === '/' : route.path.startsWith(to) ||
  (to === '/facturas' && route.path.startsWith('/packing-lists')))

const textoGuardado = computed(() => ({
  guardando: 'Guardando…',
  guardado: 'Cambios guardados',
  error: 'El último cambio no se guardó',
})[ui.guardado] || '')

function salir() {
  cerrarSesion()
  router.push('/login')
}
</script>

<template>
  <div v-if="route.name !== 'login' && sesion.usuario" class="marco">
    <aside class="lateral">
      <div class="marca">Workspace<br /><span>de proveedor</span></div>
      <nav aria-label="Principal">
        <router-link v-for="i in navegacion" :key="i.to" :to="i.to" class="nav-link" :class="{ activo: activo(i.to) }">
          {{ i.texto }}
        </router-link>
      </nav>
      <div class="lateral-pie">
        {{ sesion.usuario.nombre }}<br />
        <button type="button" @click="salir">Cerrar sesión</button>
      </div>
    </aside>
    <div class="principal">
      <header class="barra-superior">
        <label v-if="esInterno()" class="selector-proveedor">
          Proveedor
          <select class="entrada" :value="sesion.proveedorId || ''" @change="elegirProveedor(Number($event.target.value) || null)">
            <option value="">Todos</option>
            <option v-for="p in sesion.proveedores" :key="p.id" :value="p.id">{{ p.nombre }}</option>
          </select>
        </label>
        <span v-else class="proveedor-fijo">{{ sesion.usuario.proveedor }}</span>
        <router-link v-if="carrito.items.length" to="/ordenes?seleccion=1" class="btn btn-chico">
          Selección para facturar ({{ carrito.items.length }})
        </router-link>
        <span class="indicador-guardado" :class="ui.guardado" aria-live="polite">{{ textoGuardado }}</span>
      </header>
      <main class="contenido">
        <router-view :key="route.path" />
      </main>
    </div>
  </div>
  <router-view v-else-if="route.name === 'login'" />
  <Toasts />
</template>
