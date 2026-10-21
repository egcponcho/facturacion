<script setup>
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { t, tx } from '@/i18n/index.js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icono from '@/componentes/Icono.vue'
import Avatar from '@/componentes/Avatar.vue'
import BarraModulo from '@/componentes/BarraModulo.vue'
import BusquedaGlobal from '@/componentes/BusquedaGlobal.vue'
import SelectorIdioma from '@/componentes/SelectorIdioma.vue'
import SelectorTema from '@/componentes/SelectorTema.vue'
import Toasts from '@/componentes/Toasts.vue'
import Confirmacion from '@/componentes/Confirmacion.vue'
import { carrito } from '@/stores/carrito'
import { cargarSesion, cerrarSesion, elegirProveedor, eligeProveedor, sesion } from '@/stores/sesion'
import { errorApi, ui } from '@/stores/ui'
import { api } from '@/nucleo/api'
import { tituloSistema } from '@/nucleo/marca.js'
import { modulosVisibles, ubicar } from '@/nucleo/modulos.js'

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

// Una entrada por módulo (nucleo/modulos.js): cada módulo lleva adentro sus
// apartados en la barra del módulo. Cada rol ve solo los módulos y apartados que
// puede abrir (el router y el servidor lo revisan de nuevo).
const modulos = computed(() => (sesion.usuario ? modulosVisibles() : []))
const ubicacion = computed(() => ubicar(modulos.value, route))
const cuenta = (m) => (m.clave === 'compras' && carrito.items.length) || null
// Barra lateral: compacta (solo íconos) o completa; se recuerda por navegador
const leer = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v === '1' } catch { return d } }
const guardar = (k, v) => { try { localStorage.setItem(k, v ? '1' : '0') } catch { /* sin almacenamiento */ } }
// En los editores de lienzo (diseño de etiquetas) se contrae sola, sin cambiar la preferencia guardada
const compacta = ref(leer('lateral-compacta', false))
watch(compacta, (v) => guardar('lateral-compacta', v))
const abiertaEnLienzo = ref(false)
watch(() => route.meta.lienzo, () => (abiertaEnLienzo.value = false))
const plegada = computed(() => (route.meta.lienzo ? !abiertaEnLienzo.value : compacta.value))
function plegar() {
  if (route.meta.lienzo) abiertaEnLienzo.value = !abiertaEnLienzo.value
  else compacta.value = !compacta.value
}
const activo = (m) => ubicacion.value.modulo?.clave === m.clave


const textoGuardado = computed(() => ({
  guardando: t('Saving…'),
  guardado: t('Saved'),
  error: t('Not saved'),
})[ui.guardado] || '')

watch(() => route.fullPath, () => {
  menuAbierto.value = false
})

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
  <div v-if="route.name !== 'login' && !route.meta.sinMarco && sesion.usuario" class="marco" :class="{ compacta: plegada, lienzo: route.meta.lienzo }">
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
        <template v-for="(m, i) in modulos" :key="m.clave">
          <div v-if="i === 1" class="lateral-grupo">{{ t('Modules') }}</div>
          <router-link :to="m.a" class="lateral-item" :class="{ activo: activo(m) }"
                       :aria-current="activo(m) ? 'location' : undefined" :title="plegada ? tx(m.texto) : undefined">
            <Icono :nombre="m.icono" :tam="18" /><span class="lateral-texto">{{ tx(m.texto) }}</span>
            <span v-if="cuenta(m)" class="nav-cuenta">{{ tx(cuenta(m)) }}</span>
          </router-link>
        </template>
      </nav>
      <div class="lateral-pie">
        <div class="lateral-preferencias"><SelectorIdioma /><SelectorTema /></div>
        <button type="button" class="lateral-item lateral-plegar" :title="plegada ? t('Expand menu') : t('Collapse menu')" @click="plegar">
          <Icono :nombre="plegada ? 'derecha' : 'atras'" :tam="16" /><span class="lateral-texto">{{ t('Collapse menu') }}</span>
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
        <BarraModulo v-if="ubicacion.modulo && !route.meta.lienzo" :modulo="ubicacion.modulo" />
        <div :key="route.meta.vista || route.path" class="pagina-entra"><router-view /></div>
      </main>
    </div>
  </div>
  <router-view v-else-if="route.name === 'login' || route.meta.sinMarco" />
  <Toasts />
  <Confirmacion />
</template>

<style scoped>
.banda-soporte { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; padding: 10px 14px;
  border-radius: var(--radio); background: var(--aviso-fondo); color: var(--tinta); border: 1px solid var(--aviso-borde, var(--aviso)); }
.banda-soporte svg { color: var(--aviso); flex: none; }
.banda-soporte span { flex: 1; min-width: 200px; }
</style>
