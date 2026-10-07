<script setup>
import SelectBusqueda from './components/SelectBusqueda.vue'
import { t, tx } from './i18n/index.js'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icono from './components/Icono.vue'
import Avatar from './components/Avatar.vue'
import BusquedaGlobal from './components/BusquedaGlobal.vue'
import SelectorIdioma from './components/SelectorIdioma.vue'
import SelectorTema from './components/SelectorTema.vue'
import Toasts from './components/Toasts.vue'
import { carrito } from './stores/carrito'
import { cerrarSesion, elegirProveedor, esInterno, puede, sesion } from './stores/sesion'
import { ui } from './stores/ui'

const route = useRoute()
const router = useRouter()
const menuAbierto = ref(false)
// Selector de proveedor (usuarios internos): busca por código, nombre, razón social, país o marcas
const opcionesProveedor = computed(() => sesion.proveedores.map((p) => ({
  valor: p.id, texto: p.nombre, sub: [p.codigo, p.pais, p.razon_social, ...(p.marcas || [])].filter(Boolean).join(' · '),
})))

const ROLES = { admin: t('Administrator'), interno: t('Imports'), proveedor: t('Supplier') }

// Each role only sees the pages it has permission for (the router and the
// server check it again). The daily work goes in the bar; setup pages go in
// the settings menu so the bar stays short.
const navegacion = computed(() => {
  const items = [{ to: '/', texto: t('Home'), icono: 'tablero' }]
  if (puede('oc.ver')) items.push({ to: '/ordenes', texto: t('Orders'), icono: 'ordenes', cuenta: carrito.items.length || null })
  if (puede('oc.ver')) items.push({ to: '/facturas', texto: t('Invoices'), icono: 'factura' })
  if (puede('transporte.gestionar')) items.push({ to: '/transporte', texto: t('Shipments'), icono: 'barco' })
  if (puede('producto.ver')) items.push({ to: '/productos', texto: t('Products'), icono: 'etiqueta' })
  if (puede('seguimiento.ver')) items.push({ to: '/seguimiento', texto: t('Tracking'), icono: 'ruta' })
  return items
})
// Configuración agrupada por tema; solo aparece lo que el rol puede abrir
const ajustes = computed(() => {
  const items = []
  if (puede('admin')) items.push({ grupo: t('Organization'), to: '/admin', texto: t('Users and access'), detalle: t('Roles, suppliers, sessions'), icono: 'usuarios' })
  if (puede('catalogos.ver')) items.push({ grupo: t('Master data'), to: '/mantenimiento', texto: t('Master data'), detalle: t('Items, brands, suppliers, plants'), icono: 'base' })
  if (puede('plantilla.editar')) items.push({ grupo: t('Master data'), to: '/plantillas', texto: t('Packing templates'), detalle: t('Reusable carton layouts'), icono: 'capas' })
  if (puede('catalogos.ver')) items.push({ grupo: t('Logistics'), to: '/leadtimes', texto: t('Lead times'), detalle: t('Steps, rules by region, country and port'), icono: 'reloj' })
  if (puede('clasificacion.ver')) items.push({ grupo: t('Trade and compliance'), to: '/familias', texto: t('Product families'), detalle: t('Questions and rules that classify each family'), icono: 'capas' })
  if (puede('aranceles.ver')) items.push({ grupo: t('Trade and compliance'), to: '/aranceles', texto: t('Tariff schedule'), detalle: t('Tariff schemes, countries and national codes'), icono: 'etiqueta' })
  if (puede('oc.importar')) items.push({ grupo: t('Data and system'), to: '/importar', texto: t('Load purchase orders'), detalle: t('File or form'), icono: 'importar' })
  return items
})
const gruposAjustes = computed(() => {
  const g = []
  for (const i of ajustes.value) {
    const ultimo = g[g.length - 1]
    if (ultimo?.nombre === i.grupo) ultimo.items.push(i)
    else g.push({ nombre: i.grupo, items: [i] })
  }
  return g
})
const ajustesAbierto = ref(false)
const enAjustes = computed(() => ajustes.value.some((i) => route.path.startsWith(i.to)))

const activo = (to) => (to === '/' ? route.path === '/' : route.path.startsWith(to) ||
  (to === '/facturas' && route.path.startsWith('/packing-lists')) || (to === '/productos' && (route.path.startsWith('/aranceles') || route.path.startsWith('/familias'))))


const textoGuardado = computed(() => ({
  guardando: t('Saving…'),
  guardado: t('Saved'),
  error: t('Not saved'),
})[ui.guardado] || '')

watch(() => route.fullPath, () => {
  menuAbierto.value = false
  ajustesAbierto.value = false
})

async function salir() {
  await cerrarSesion()
  router.push('/login')
}

// Change own password: closes the other open sessions
</script>

<template>
  <div v-if="route.name !== 'login' && !route.meta.sinMarco && sesion.usuario" class="marco">
    <header class="cabecera">
      <div class="cabecera-fila">
        <button type="button" class="btn-icono boton-menu" :aria-expanded="menuAbierto" :aria-label="t('Menu')" @click="menuAbierto = !menuAbierto">
          <Icono :nombre="menuAbierto ? 'cerrar' : 'menu'" :tam="22" />
        </button>
        <router-link to="/" class="marca">
          <span class="marca-logo"><Icono nombre="caja" :tam="19" /></span>
          <span class="marca-texto">{{ t('Workspace') }}<span>{{ t('Suppliers') }}</span></span>
        </router-link>
        <BusquedaGlobal class="cabecera-busqueda" />
        <div class="cabecera-derecha">
          <span class="indicador-guardado" :class="ui.guardado" aria-live="polite"><Icono v-if="ui.guardado === 'guardado'" nombre="check" :tam="14" />{{ tx(textoGuardado) }}</span>
          <router-link v-if="carrito.items.length" to="/ordenes?seleccion=1" class="chip-seleccion" :title="t('Order lines ready to invoice')">
            <Icono nombre="carrito" :tam="15" /><b>{{ tx(carrito.items.length) }}</b>
          </router-link>
          <div v-if="esInterno()" class="selector-proveedor fila-flex" style="gap: 6px; flex-wrap: nowrap">
            <span class="ayuda">{{ t('Supplier') }}</span>
            <SelectBusqueda :model-value="sesion.proveedorId || ''" :opciones="opcionesProveedor" :vacio="t('All suppliers')" :busqueda="true"
                            :etiqueta="t('Supplier')" :prefijo="false" @update:model-value="elegirProveedor(Number($event) || null)" />
          </div>
          <SelectorIdioma class="solo-escritorio" />
          <SelectorTema class="solo-escritorio" />
          <div class="usuario">
            <router-link to="/perfil" class="usuario-enlace" :title="t('My profile')" :aria-label="t('My profile')">
              <Avatar :nombre="sesion.usuario.nombre" :foto="sesion.usuario.foto" :tam="32" />
              <div class="usuario-datos">
                <b>{{ tx(sesion.usuario.nombre) }}</b>
                <span>{{ tx(sesion.usuario.proveedor || sesion.usuario.rol_nombre || ROLES[sesion.usuario.rol]) }}</span>
              </div>
            </router-link>
            <button type="button" class="btn-icono solo-escritorio" :aria-label="t('Sign out')" :title="t('Sign out')" @click="salir"><Icono nombre="salir" /></button>
          </div>
        </div>
      </div>
      <div class="cabecera-nav">
        <nav class="nav-principal" :aria-label="t('Main')">
          <router-link v-for="i in navegacion" :key="i.to" :to="i.to" class="nav-link" :class="{ activo: activo(i.to) }"
                       :aria-current="activo(i.to) ? 'page' : undefined">
            <Icono :nombre="i.icono" :tam="16" />{{ tx(i.texto) }}
            <span v-if="i.cuenta" class="nav-cuenta" :aria-label="t('{0} in the selection', [i.cuenta])">{{ tx(i.cuenta) }}</span>
          </router-link>
          <div class="nav-ajustes" @keydown.esc="ajustesAbierto = false">
            <button type="button" class="nav-link" :class="{ activo: enAjustes }" :aria-expanded="ajustesAbierto" aria-haspopup="true"
                    @click="ajustesAbierto = !ajustesAbierto"><Icono nombre="engrane" :tam="16" />{{ t('Settings') }}<Icono nombre="abajo" :tam="14" /></button>
            <div v-if="ajustesAbierto" class="menu-ajustes" role="menu">
              <template v-for="g in gruposAjustes" :key="g.nombre">
                <div class="menu-grupo" role="presentation">{{ tx(g.nombre) }}</div>
                <router-link v-for="i in g.items" :key="i.to" :to="i.to" class="menu-item" role="menuitem">
                  <span class="menu-icono"><Icono :nombre="i.icono" :tam="16" /></span>
                  <span><b>{{ tx(i.texto) }}</b><small>{{ tx(i.detalle) }}</small></span>
                </router-link>
              </template>
            </div>
            <div v-if="ajustesAbierto" class="menu-velo" @click="ajustesAbierto = false"></div>
          </div>
        </nav>
      </div>
      <nav class="nav-movil" :class="{ abierta: menuAbierto }" :aria-label="t('Main (mobile)')">
        <router-link v-for="i in [...navegacion, ...ajustes]" :key="i.to" :to="i.to" class="nav-link" :class="{ activo: activo(i.to) }">
          <Icono :nombre="i.icono" :tam="17" />{{ tx(i.texto) }}
          <span v-if="i.cuenta" class="nav-cuenta">{{ tx(i.cuenta) }}</span>
        </router-link>
        <!-- En celular, las preferencias y la cuenta viven en el menú para no saturar la cabecera -->
        <div class="nav-movil-extra">
          <SelectorIdioma />
          <SelectorTema />
          <router-link to="/perfil" class="nav-link" :class="{ activo: activo('/perfil') }"><Icono nombre="usuario" :tam="17" />{{ t('My profile') }}</router-link>
          <button type="button" class="nav-link" @click="salir"><Icono nombre="salir" :tam="17" />{{ t('Sign out') }}</button>
        </div>
      </nav>
    </header>
    <main class="contenido">
      <router-view :key="route.path" />
    </main>
  </div>
  <router-view v-else-if="route.name === 'login' || route.meta.sinMarco" />
  <Toasts />
</template>
