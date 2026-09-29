<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icono from './components/Icono.vue'
import Toasts from './components/Toasts.vue'
import { carrito } from './stores/carrito'
import { cerrarSesion, elegirProveedor, esInterno, puede, sesion } from './stores/sesion'
import { ui } from './stores/ui'

const route = useRoute()
const router = useRouter()
const menuAbierto = ref(false)

const ROLES = { admin: 'Administrador', interno: 'Importaciones', proveedor: 'Proveedor' }

// Navegación agrupada por etapa del trabajo
const grupos = computed(() => {
  const res = [
    { titulo: 'General', items: [{ to: '/', texto: 'Inicio', icono: 'tablero' }] },
    {
      titulo: 'Facturación',
      items: [
        { to: '/ordenes', texto: 'Órdenes de compra', icono: 'ordenes', cuenta: carrito.items.length || null },
        { to: '/facturas', texto: 'Facturas y empaque', icono: 'factura' },
        { to: '/plantillas', texto: 'Plantillas de caja', icono: 'capas' },
      ],
    },
  ]
  if (esInterno()) {
    res.push({ titulo: 'Logística', items: [{ to: '/transporte', texto: 'Embarques', icono: 'barco' }] })
    const admin = [{ to: '/importar', texto: 'Importar OCs', icono: 'importar' }]
    if (puede('admin')) admin.push({ to: '/admin', texto: 'Usuarios y proveedores', icono: 'usuarios' })
    res.push({ titulo: 'Administración', items: admin })
  }
  return res
})

const activo = (to) => (to === '/' ? route.path === '/' : route.path.startsWith(to) ||
  (to === '/facturas' && route.path.startsWith('/packing-lists')))

const iniciales = computed(() => (sesion.usuario?.nombre || '?').split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase())

const textoGuardado = computed(() => ({
  guardando: 'Guardando…',
  guardado: 'Cambios guardados',
  error: 'El último cambio no se guardó',
})[ui.guardado] || '')

watch(() => route.fullPath, () => (menuAbierto.value = false))

function salir() {
  cerrarSesion()
  router.push('/login')
}
</script>

<template>
  <div v-if="route.name !== 'login' && sesion.usuario" class="marco">
    <div class="velo" :class="{ visible: menuAbierto }" @click="menuAbierto = false"></div>
    <aside class="lateral" :class="{ abierto: menuAbierto }">
      <router-link to="/" class="marca">
        <span class="marca-logo"><Icono nombre="caja" :tam="20" /></span>
        <span class="marca-texto">Workspace<span>Facturas, empaque y embarques</span></span>
      </router-link>
      <nav aria-label="Principal">
        <div v-for="g in grupos" :key="g.titulo" class="nav-grupo">
          <div class="nav-titulo">{{ g.titulo }}</div>
          <router-link v-for="i in g.items" :key="i.to" :to="i.to" class="nav-link" :class="{ activo: activo(i.to) }"
                       :aria-current="activo(i.to) ? 'page' : undefined">
            <Icono :nombre="i.icono" />
            {{ i.texto }}
            <span v-if="i.cuenta" class="nav-cuenta" :aria-label="`${i.cuenta} en la selección`">{{ i.cuenta }}</span>
          </router-link>
        </div>
      </nav>
      <div class="lateral-pie">
        <span class="avatar" aria-hidden="true">{{ iniciales }}</span>
        <div class="usuario-datos">
          <b>{{ sesion.usuario.nombre }}</b>
          <span>{{ sesion.usuario.proveedor || ROLES[sesion.usuario.rol] }}</span>
        </div>
        <button type="button" class="boton-lateral" aria-label="Cerrar sesión" title="Cerrar sesión" @click="salir">
          <Icono nombre="salir" />
        </button>
      </div>
    </aside>
    <div class="principal">
      <header class="barra-superior">
        <button type="button" class="btn-icono boton-menu" aria-label="Abrir menú" @click="menuAbierto = true">
          <Icono nombre="menu" :tam="22" />
        </button>
        <label v-if="esInterno()" class="selector-proveedor">
          <span>Proveedor</span>
          <select class="entrada" :value="sesion.proveedorId || ''" @change="elegirProveedor(Number($event.target.value) || null)">
            <option value="">Todos los proveedores</option>
            <option v-for="p in sesion.proveedores" :key="p.id" :value="p.id">{{ p.nombre }}</option>
          </select>
        </label>
        <span v-else class="proveedor-fijo"><Icono nombre="caja" /> {{ sesion.usuario.proveedor }}</span>
        <router-link v-if="carrito.items.length" to="/ordenes?seleccion=1" class="chip-seleccion">
          <Icono nombre="carrito" :tam="16" /> Por facturar <b>{{ carrito.items.length }}</b>
        </router-link>
        <span class="indicador-guardado" :class="ui.guardado" aria-live="polite">
          <Icono v-if="ui.guardado === 'guardado'" nombre="check" :tam="15" />{{ textoGuardado }}
        </span>
      </header>
      <main class="contenido">
        <router-view :key="route.path" />
      </main>
    </div>
  </div>
  <router-view v-else-if="route.name === 'login'" />
  <Toasts />
</template>
