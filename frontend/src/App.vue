<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icono from './components/Icono.vue'
import Modal from './components/Modal.vue'
import SelectorTema from './components/SelectorTema.vue'
import Toasts from './components/Toasts.vue'
import { carrito } from './stores/carrito'
import { cerrarSesion, elegirProveedor, esInterno, puede, sesion } from './stores/sesion'
import { api } from './api'
import { avisar, ui } from './stores/ui'

const route = useRoute()
const router = useRouter()
const menuAbierto = ref(false)

const ROLES = { admin: 'Administrator', interno: 'Imports', proveedor: 'Supplier' }

// Each role only sees the pages it has permission for (the router and the
// server check it again)
const navegacion = computed(() => {
  const items = [
    { to: '/', texto: 'Home', icono: 'tablero' },
    { to: '/ordenes', texto: 'Orders', icono: 'ordenes', cuenta: carrito.items.length || null },
    { to: '/facturas', texto: 'Invoices', icono: 'factura' },
    { to: '/seguimiento', texto: 'Tracking', icono: 'ruta' },
  ]
  if (puede('transporte.gestionar')) items.push({ to: '/transporte', texto: 'Shipments', icono: 'barco' })
  items.push({ to: '/plantillas', texto: 'Templates', icono: 'capas' })
  if (puede('catalogos.ver')) items.push({ to: '/mantenimiento', texto: 'Master data', icono: 'base' })
  if (puede('admin')) items.push({ to: '/admin', texto: 'Users', icono: 'usuarios' })
  return items
})

const activo = (to) => (to === '/' ? route.path === '/' : route.path.startsWith(to) ||
  (to === '/facturas' && route.path.startsWith('/packing-lists')) || (to === '/ordenes' && route.path.startsWith('/importar')))

const iniciales = computed(() => (sesion.usuario?.nombre || '?').split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase())

const textoGuardado = computed(() => ({
  guardando: 'Saving…',
  guardado: 'Saved',
  error: 'Not saved',
})[ui.guardado] || '')

watch(() => route.fullPath, () => (menuAbierto.value = false))

async function salir() {
  await cerrarSesion()
  router.push('/login')
}

// Change own password: closes the other open sessions
const clave = ref(null)
async function cambiarClave() {
  clave.value.error = ''
  if (clave.value.nueva !== clave.value.repetir) {
    clave.value.error = 'The new passwords do not match.'
    return
  }
  try {
    await api.post('/auth/password', { actual: clave.value.actual, nueva: clave.value.nueva })
    clave.value = null
    avisar('Password changed. Your other sessions were closed.')
  } catch (e) {
    clave.value.error = [e.message, ...(e.detalle || []).map((d) => d.mensaje)].join(' ')
  }
}
</script>

<template>
  <div v-if="route.name !== 'login' && sesion.usuario" class="marco">
    <header class="cabecera">
      <div class="cabecera-fila">
        <button type="button" class="btn-icono boton-menu" :aria-expanded="menuAbierto" aria-label="Menu" @click="menuAbierto = !menuAbierto">
          <Icono :nombre="menuAbierto ? 'cerrar' : 'menu'" :tam="22" />
        </button>
        <router-link to="/" class="marca">
          <span class="marca-logo"><Icono nombre="caja" :tam="19" /></span>
          <span class="marca-texto">Workspace<span>Suppliers</span></span>
        </router-link>
        <div class="cabecera-derecha">
          <span class="indicador-guardado" :class="ui.guardado" aria-live="polite"><Icono v-if="ui.guardado === 'guardado'" nombre="check" :tam="14" />{{ textoGuardado }}</span>
          <router-link v-if="carrito.items.length" to="/ordenes?seleccion=1" class="chip-seleccion" title="Order lines ready to invoice">
            <Icono nombre="carrito" :tam="15" /><b>{{ carrito.items.length }}</b>
          </router-link>
          <label v-if="esInterno()" class="selector-proveedor fila-flex" style="gap: 6px; flex-wrap: nowrap">
            <span class="ayuda">Supplier</span>
            <select class="entrada" :value="sesion.proveedorId || ''" @change="elegirProveedor(Number($event.target.value) || null)">
              <option value="">All</option>
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
            <button type="button" class="btn-icono" aria-label="Change password" title="Change password"
                    @click="clave = { actual: '', nueva: '', repetir: '', error: '' }"><Icono nombre="candado" /></button>
            <button type="button" class="btn-icono" aria-label="Sign out" title="Sign out" @click="salir"><Icono nombre="salir" /></button>
          </div>
        </div>
      </div>
      <div class="cabecera-nav">
        <nav class="nav-principal" aria-label="Main">
          <router-link v-for="i in navegacion" :key="i.to" :to="i.to" class="nav-link" :class="{ activo: activo(i.to) }"
                       :aria-current="activo(i.to) ? 'page' : undefined">
            <Icono :nombre="i.icono" :tam="16" />{{ i.texto }}
            <span v-if="i.cuenta" class="nav-cuenta" :aria-label="`${i.cuenta} in the selection`">{{ i.cuenta }}</span>
          </router-link>
        </nav>
      </div>
      <nav class="nav-movil" :class="{ abierta: menuAbierto }" aria-label="Main (mobile)">
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
  <Modal v-if="clave" titulo="Change password" ancho="440px" @cerrar="clave = null">
    <form id="form-clave" class="rejilla-campos" style="grid-template-columns: 1fr" @submit.prevent="cambiarClave">
      <label class="campo"><span class="req">Current password</span><input v-model="clave.actual" type="password" autocomplete="current-password" required /></label>
      <label class="campo"><span class="req">New password</span><input v-model="clave.nueva" type="password" autocomplete="new-password" minlength="10" required />
        <small class="ayuda">At least 10 characters, with letters and numbers.</small></label>
      <label class="campo"><span class="req">Repeat the new password</span><input v-model="clave.repetir" type="password" autocomplete="new-password" required /></label>
      <p v-if="clave.error" class="nota error" role="alert"><Icono nombre="alerta" />{{ clave.error }}</p>
    </form>
    <template #pie>
      <button class="btn" @click="clave = null">Cancel</button>
      <button class="btn btn-primario" type="submit" form="form-clave">Change password</button>
    </template>
  </Modal>
  <Toasts />
</template>
