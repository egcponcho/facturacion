<script setup>
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icono from '@/componentes/Icono.vue'
import Avatar from '@/componentes/Avatar.vue'
import BusquedaGlobal from '@/componentes/BusquedaGlobal.vue'
import SelectorIdioma from '@/componentes/SelectorIdioma.vue'
import SelectorTema from '@/componentes/SelectorTema.vue'
import Toasts from '@/componentes/Toasts.vue'
import { carrito } from '@/stores/carrito'
import { cargarSesion, cerrarSesion, elegirProveedor, eligeProveedor, puede, sesion } from '@/stores/sesion'
import { errorApi, ui } from '@/stores/ui'
import { api } from '@/nucleo/api'
import { tituloSistema } from '@/nucleo/marca.js'

const route = useRoute()
const router = useRouter()
// Nombre y logo de la empresa (Configuración → Empresa)
const empresa = computed(() => sesion.usuario?.organizacion)
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
  if (puede('factura.ver')) items.push({ to: '/facturas', texto: t('Invoices'), icono: 'factura' })
  if (puede('transporte.gestionar')) items.push({ to: '/transporte', texto: t('Shipments'), icono: 'barco' })
  if (puede('producto.ver')) items.push({ to: '/productos', texto: t('Products'), icono: 'etiqueta' })
  if (puede('seguimiento.ver')) items.push({ to: '/seguimiento', texto: t('Tracking'), icono: 'ruta' })
  return items
})
// Configuración agrupada por tema; solo aparece lo que el rol puede abrir
const ajustes = computed(() => {
  const items = []
  if (sesion.usuario?.plataforma) items.push({ grupo: t('Platform'), to: '/plataforma', texto: t('Organizations'), detalle: t('Client companies of this installation'), icono: 'capas' })
  if (puede('admin')) items.push({ grupo: t('Organization'), to: '/empresa', texto: t('Company'), detalle: t('Name, logo, preferences and rules'), icono: 'base' })
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
// Barra lateral: compacta (solo íconos) o completa; se recuerda por navegador
const leer = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v === '1' } catch { return d } }
const guardar = (k, v) => { try { localStorage.setItem(k, v ? '1' : '0') } catch { /* sin almacenamiento */ } }
const compacta = ref(leer('lateral-compacta', false))
watch(compacta, (v) => guardar('lateral-compacta', v))
const ajustesAbierto = ref(leer('lateral-ajustes', false))
watch(ajustesAbierto, (v) => guardar('lateral-ajustes', v))
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
})
// Si se entra a una página de configuración, la sección queda abierta
watch(enAjustes, (v) => { if (v) ajustesAbierto.value = true }, { immediate: true })

// La descripción de cada página va en una línea; un clic la despliega
function desplegar(e) {
  const p = e.target.closest?.('.pagina-cabeza p')
  if (p) p.classList.toggle('expandida')
}
onMounted(() => document.addEventListener('click', desplegar))
onBeforeUnmount(() => document.removeEventListener('click', desplegar))

async function salir() {
  await cerrarSesion()
  router.push('/login')
}

// Soporte de la plataforma: volver a la organización propia
async function volverAMiOrganizacion() {
  try {
    await api.post('/plataforma/entrar', { organizacion_id: null })
    await cargarSesion(true)
    router.push('/plataforma')
  } catch (e) {
    errorApi(e)
  }
}

// Change own password: closes the other open sessions
</script>

<template>
  <div v-if="route.name !== 'login' && !route.meta.sinMarco && sesion.usuario" class="marco" :class="{ compacta }">
    <div class="progreso-ruta" :class="{ activo: ui.navegando }" aria-hidden="true"></div>
    <aside class="lateral" :class="{ abierta: menuAbierto }" :aria-label="t('Main')">
      <div class="lateral-cabeza">
        <router-link to="/" class="marca" :title="tx(empresa?.nombre || tituloSistema())">
          <img v-if="empresa?.logo" :src="empresa.logo" alt="" class="marca-logo marca-imagen" />
          <span v-else class="marca-logo"><Icono nombre="caja" :tam="18" /></span>
          <span class="marca-texto">{{ tx(empresa?.nombre || tituloSistema()) }}<span>{{ tituloSistema() }}</span></span>
        </router-link>
        <button type="button" class="btn-icono lateral-cerrar" :aria-label="t('Close')" @click="menuAbierto = false"><Icono nombre="cerrar" :tam="20" /></button>
      </div>
      <nav class="lateral-nav">
        <router-link v-for="i in navegacion" :key="i.to" :to="i.to" class="lateral-item" :class="{ activo: activo(i.to) }"
                     :aria-current="activo(i.to) ? 'page' : undefined" :title="compacta ? tx(i.texto) : undefined">
          <Icono :nombre="i.icono" :tam="18" /><span class="lateral-texto">{{ tx(i.texto) }}</span>
          <span v-if="i.cuenta" class="nav-cuenta">{{ tx(i.cuenta) }}</span>
        </router-link>
        <template v-if="ajustes.length">
          <button type="button" class="lateral-seccion" :aria-expanded="ajustesAbierto" :title="compacta ? t('Settings') : undefined" @click="ajustesAbierto = !ajustesAbierto">
            <Icono nombre="engrane" :tam="18" /><span class="lateral-texto">{{ t('Settings') }}</span>
            <Icono :nombre="ajustesAbierto ? 'arriba' : 'abajo'" :tam="14" class="lateral-flecha" />
          </button>
          <div v-show="ajustesAbierto" class="lateral-ajustes">
            <template v-for="g in gruposAjustes" :key="g.nombre">
              <div class="lateral-grupo">{{ tx(g.nombre) }}</div>
              <router-link v-for="i in g.items" :key="i.to" :to="i.to" class="lateral-item lateral-sub" :class="{ activo: route.path.startsWith(i.to) }"
                           :title="compacta ? tx(i.texto) : tx(i.detalle)">
                <Icono :nombre="i.icono" :tam="16" /><span class="lateral-texto">{{ tx(i.texto) }}</span>
              </router-link>
            </template>
          </div>
        </template>
      </nav>
      <div class="lateral-pie">
        <div class="lateral-preferencias"><SelectorIdioma /><SelectorTema /></div>
        <button type="button" class="lateral-item lateral-plegar" :title="compacta ? t('Expand menu') : t('Collapse menu')" @click="compacta = !compacta">
          <Icono :nombre="compacta ? 'derecha' : 'atras'" :tam="16" /><span class="lateral-texto">{{ t('Collapse menu') }}</span>
        </button>
      </div>
    </aside>
    <div v-if="menuAbierto" class="lateral-velo" @click="menuAbierto = false"></div>

    <div class="area">
      <header class="cabecera">
        <button type="button" class="btn-icono boton-menu" :aria-expanded="menuAbierto" :aria-label="t('Menu')" @click="menuAbierto = true">
          <Icono nombre="menu" :tam="22" />
        </button>
        <BusquedaGlobal class="cabecera-busqueda" />
        <div class="cabecera-derecha">
          <span class="indicador-guardado" :class="ui.guardado" aria-live="polite"><Icono v-if="ui.guardado === 'guardado'" nombre="check" :tam="14" />{{ tx(textoGuardado) }}</span>
          <router-link v-if="carrito.items.length" to="/ordenes?seleccion=1" class="chip-seleccion" :title="t('Order lines ready to invoice')">
            <Icono nombre="carrito" :tam="15" /><b>{{ tx(carrito.items.length) }}</b>
          </router-link>
          <div v-if="eligeProveedor()" class="selector-proveedor">
            <SelectBusqueda :model-value="sesion.proveedorId || ''" :opciones="opcionesProveedor" :vacio="t('All suppliers')" :busqueda="true"
                            :etiqueta="t('Supplier')" :prefijo="false" @update:model-value="elegirProveedor(Number($event) || null)" />
          </div>
          <div class="usuario">
            <router-link to="/perfil" class="usuario-enlace" :title="t('My profile')" :aria-label="t('My profile')">
              <Avatar :nombre="sesion.usuario.nombre" :foto="sesion.usuario.foto" :tam="32" />
              <div class="usuario-datos">
                <b>{{ tx(sesion.usuario.nombre) }}</b>
                <span>{{ tx(sesion.usuario.proveedor || sesion.usuario.rol_nombre || ROLES[sesion.usuario.rol]) }}</span>
              </div>
            </router-link>
            <button type="button" class="btn-icono" :aria-label="t('Sign out')" :title="t('Sign out')" @click="salir"><Icono nombre="salir" /></button>
          </div>
        </div>
      </header>
      <main class="contenido">
        <!-- Soporte de la plataforma: deja claro en qué organización se está trabajando -->
        <div v-if="empresa && empresa.propia === false" class="banda-soporte" role="status">
          <Icono nombre="alerta" :tam="16" />
          <span>{{ t('You are working in {0} as platform support. What you do is recorded in its activity log.', [empresa.nombre]) }}</span>
          <button type="button" class="btn btn-chico" @click="volverAMiOrganizacion">{{ t('Back to my organization') }}</button>
        </div>
        <!-- Cada página entra con un fundido corto (sin esperar a la anterior) -->
        <div :key="route.path" class="pagina-entra"><router-view /></div>
      </main>
    </div>
  </div>
  <router-view v-else-if="route.name === 'login' || route.meta.sinMarco" />
  <Toasts />
</template>

<style scoped>
.banda-soporte { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; padding: 10px 14px;
  border-radius: var(--radio); background: var(--aviso-fondo); color: var(--tinta); border: 1px solid var(--aviso-borde, var(--aviso)); }
.banda-soporte svg { color: var(--aviso); flex: none; }
.banda-soporte span { flex: 1; min-width: 200px; }
</style>
