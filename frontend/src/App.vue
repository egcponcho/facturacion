<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icono from './components/Icono.vue'
import SelectorTema from './components/SelectorTema.vue'
import Toasts from './components/Toasts.vue'
import { carrito } from './stores/carrito'
import { cerrarSesion, elegirProveedor, esInterno, puede, sesion } from './stores/sesion'
import { ui } from './stores/ui'

const route = useRoute()
const router = useRouter()
const menuAbierto = ref(false)

const ROLES = { admin: 'Administrador', interno: 'Importaciones', proveedor: 'Proveedor' }

const navegacion = computed(() => {
  const items = [
    { to: '/', texto: 'Inicio', icono: 'tablero' },
    { to: '/ordenes', texto: 'Órdenes', icono: 'ordenes', cuenta: carrito.items.length || null },
    { to: '/facturas', texto: 'Facturas', icono: 'factura' },
    { to: '/plantillas', texto: 'Plantillas', icono: 'capas' },
  ]
  if (esInterno()) {
    items.push({ to: '/transporte', texto: 'Embarques', icono: 'barco' }, { to: '/importar', texto: 'Importar OCs', icono: 'importar' })
    if (puede('admin')) items.push({ to: '/admin', texto: 'Usuarios', icono: 'usuarios' })
  }
  return items
})

const activo = (to) => (to === '/' ? route.path === '/' : route.path.startsWith(to) ||
  (to === '/facturas' && route.path.startsWith('/packing-lists')))

const iniciales = computed(() => (sesion.usuario?.nombre || '?').split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase())

const textoGuardado = computed(() => ({
  guardando: 'Guardando…',
  guardado: 'Guardado',
  error: 'No se guardó',
})[ui.guardado] || '')

watch(() => route.fullPath, () => (menuAbierto.value = false))

function salir() {
  cerrarSesion()
  router.push('/login')
}
</script>

<template>
  <div v-if="route.name !== 'login' && sesion.usuario" class="marco">
    <header class="cabecera">
      <div class="cabecera-fila">
        <button type="button" class="btn-icono boton-menu" :aria-expanded="menuAbierto" aria-label="Menú" @click="menuAbierto = !menuAbierto">
          <Icono :nombre="menuAbierto ? 'cerrar' : 'menu'" :tam="22" />
        </button>
        <router-link to="/" class="marca">
          <span class="marca-logo"><Icono nombre="caja" :tam="19" /></span>
          <span class="marca-texto">Workspace<span>Proveedores</span></span>
        </router-link>
        <nav class="nav-principal" aria-label="Principal">
          <router-link v-for="i in navegacion" :key="i.to" :to="i.to" class="nav-link" :class="{ activo: activo(i.to) }"
                       :aria-current="activo(i.to) ? 'page' : undefined">
            <Icono :nombre="i.icono" :tam="16" />{{ i.texto }}
            <span v-if="i.cuenta" class="nav-cuenta" :aria-label="`${i.cuenta} en la selección`">{{ i.cuenta }}</span>
          </router-link>
        </nav>
        <div class="cabecera-derecha">
          <span class="indicador-guardado" :class="ui.guardado" aria-live="polite"><Icono v-if="ui.guardado === 'guardado'" nombre="check" :tam="14" />{{ textoGuardado }}</span>
          <router-link v-if="carrito.items.length" to="/ordenes?seleccion=1" class="chip-seleccion" title="Posiciones listas para facturar">
            <Icono nombre="carrito" :tam="15" /><b>{{ carrito.items.length }}</b>
          </router-link>
          <label v-if="esInterno()" class="selector-proveedor fila-flex" style="gap: 6px; flex-wrap: nowrap">
            <span class="ayuda">Proveedor</span>
            <select class="entrada" :value="sesion.proveedorId || ''" @change="elegirProveedor(Number($event.target.value) || null)">
              <option value="">Todos</option>
              <option v-for="p in sesion.proveedores" :key="p.id" :value="p.id">{{ p.nombre }}</option>
            </select>
          </label>
          <SelectorTema />
          <div class="usuario">
            <span class="avatar" aria-hidden="true">{{ iniciales }}</span>
            <div class="usuario-datos">
              <b>{{ sesion.usuario.nombre }}</b>
              <span>{{ sesion.usuario.proveedor || ROLES[sesion.usuario.rol] }}</span>
            </div>
            <button type="button" class="btn-icono" aria-label="Cerrar sesión" title="Cerrar sesión" @click="salir"><Icono nombre="salir" /></button>
          </div>
        </div>
      </div>
      <nav class="nav-movil" :class="{ abierta: menuAbierto }" aria-label="Principal (móvil)">
        <router-link v-for="i in navegacion" :key="i.to" :to="i.to" class="nav-link" :class="{ activo: activo(i.to) }">
          <Icono :nombre="i.icono" :tam="17" />{{ i.texto }}
          <span v-if="i.cuenta" class="nav-cuenta">{{ i.cuenta }}</span>
        </router-link>
      </nav>
    </header>
    <main class="contenido">
      <router-view :key="route.path" />
    </main>
  </div>
  <router-view v-else-if="route.name === 'login'" />
  <Toasts />
</template>
