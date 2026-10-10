<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Seleccion from '@/componentes/Seleccion.vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import FiltroMulti from '@/componentes/FiltroMulti.vue'
import Modal from '@/componentes/Modal.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import Avatar from '@/componentes/Avatar.vue'
import MenuAcciones from '@/componentes/MenuAcciones.vue'
import PanelFlujo from '@/modulos/acceso/componentes/PanelFlujo.vue'
import PanelBitacora from '@/modulos/acceso/componentes/PanelBitacora.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { buscador } from '@/nucleo/busqueda.js'
import { puede, sesion } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtFechaHora } from '@/nucleo/utils'

const route = useRoute()
const router = useRouter()
const proveedores = ref([])
const usuarios = ref([])
const vacioUsr = () => ({ nombre: '', email: '', rol_id: '', proveedor_id: '', password: '', telefono: '', dos_pasos: true, cargo: '', area: '', empresa: '' })
const nuevoUsr = reactive(vacioUsr())
// 'proveedor' | 'usuario' | { tipo: 'clave', usuario, clave } | { tipo: 'telefono', usuario, telefono, dos_pasos }
const modal = ref(null)
// Pestañas: una sección a la vez (antes, todo en una página larga)
const PESTANAS = [['usuarios', t('Users')], ['roles', t('Roles and access')], ['proveedores', t('Suppliers')], ['flujo', t('Classification workflow')], ['bitacora', t('Activity log')]]
const pestana = ref(PESTANAS.some(([k]) => k === route.query.tab) ? route.query.tab : 'usuarios')
function elegirPestana(k) {
  pestana.value = k
  q.value = ''
  router.replace({ query: { ...route.query, tab: k } })
}
const ALCANCE = { admin: t('Administrator'), interno: t('Internal team'), proveedor: t('Supplier user') }
const roles = ref([])
const catalogo = ref([])
// Grupos de datos que se pueden ocultar a un rol (precios, códigos internos…)
const gruposDatos = ref([])
const panelesInicio = ref([])
const rolesActivos = computed(() => roles.value.filter((r) => r.activo))

// Tablas con el aspecto de órdenes de compra (TablaDatos en modo local): el
// buscador de la pestaña filtra antes de pasar las filas
const q = ref('')
const filtrar = (lista, campos) => {
  const coincide = buscador(q.value)
  return lista.filter((x) => coincide(campos(x)))
}
const ESTADOS_ACTIVO = [[true, t('Active')], [false, t('Inactive')]]
const usuariosVista = computed(() => filtrar(usuarios.value, (u) => [u.nombre, u.email, u.cargo, u.area, u.rol_nombre, u.proveedor, u.telefono]))
const rolesVista = computed(() => filtrar(roles.value, (r) => [r.nombre, r.descripcion]))
const proveedoresVista = computed(() => filtrar(proveedores.value, (p) => [p.codigo, p.nombre]))
const colUsuarios = computed(() => [
  { clave: 'nombre', texto: t('Name'), fija: true, prioridad: 1, filtro: 'texto' },
  { clave: 'email', texto: t('Email'), prioridad: 2, filtro: 'texto' },
  { clave: 'rol', texto: t('Role'), prioridad: 2, filtro: 'opcion', valor: (u) => u.rol_nombre || '', opciones: roles.value.map((r) => [r.nombre, r.nombre]) },
  { clave: 'proveedor', texto: t('Supplier'), prioridad: 3, filtro: 'opcion', valor: (u) => u.proveedor || t('Internal'),
    opciones: [[t('Internal'), t('Internal')], ...proveedores.value.map((p) => [p.nombre, p.nombre])] },
  { clave: 'telefono', texto: t('Registered mobile'), prioridad: 3 },
  { clave: 'activo', texto: t('Status'), prioridad: 2, filtro: 'opcion', valor: (u) => u.activo, opciones: ESTADOS_ACTIVO },
])
const colRoles = [
  { clave: 'nombre', texto: t('Role'), fija: true, prioridad: 1, filtro: 'texto' },
  { clave: 'acceso', texto: t('Access'), prioridad: 2, valor: (r) => r.permisos.length },
  { clave: 'usuarios', texto: t('Users'), num: true, prioridad: 2 },
  { clave: 'activo', texto: t('Status'), prioridad: 2, filtro: 'opcion', opciones: ESTADOS_ACTIVO },
]
const colProveedores = [
  { clave: 'codigo', texto: t('Code'), fija: true, prioridad: 1 },
  { clave: 'nombre', texto: t('Name'), prioridad: 1, filtro: 'texto' },
  { clave: 'activo', texto: t('Status'), prioridad: 2, filtro: 'opcion', opciones: ESTADOS_ACTIVO },
  { clave: 'usuarios', texto: t('Users'), num: true, prioridad: 2, valor: (p) => usuarios.value.filter((u) => u.proveedor_id === p.id).length },
]
const AYUDA_PESTANA = {
  usuarios: t('Each supplier user only sees their own supplier\'s POs, invoices and packing lists. Every user signs in with two-step verification: a code sent by SMS to their registered mobile.'),
  roles: t('Create each role with a name, a description and the permissions you choose, then assign it to users. What data a user sees depends on the user: with a supplier assigned, only that supplier’s data.'),
  proveedores: t('Suppliers are maintained in one place, Master data → Suppliers, with their validation, owners and history. Here you see them to give users access.'),
  bitacora: t('Who changed what and when: documents, approvals, master data, users, roles and company settings.'),
}
const rolDe = (id) => roles.value.find((r) => r.id === Number(id))
// Permisos del rol que no aplican a un usuario de proveedor (datos globales o administración)
const noAplicanProveedor = (id) => {
  const r = rolDe(id)
  if (!r) return []
  return catalogo.value.flatMap((m) => m.permisos).filter((p) => r.permisos.includes(p.clave) && (!p.proveedor || p.clave === 'admin'))
}
const totalPermisos = computed(() => catalogo.value.reduce((n, m) => n + m.permisos.length, 0))

async function cargar() {
  try {
    let r
    ;[proveedores.value, usuarios.value, r] = await Promise.all([api.get('/proveedores'), api.get('/usuarios'), api.get('/roles')])
    roles.value = r.roles
    catalogo.value = r.catalogo
    gruposDatos.value = r.datos || []
    panelesInicio.value = r.paneles || []
    sesion.proveedores = proveedores.value
  } catch (e) {
    errorApi(e)
  }
}

async function crearUsuario() {
  try {
    const r = await api.post('/usuarios', {
      ...nuevoUsr, telefono: nuevoUsr.telefono || null, password: nuevoUsr.password || null,
      rol_id: Number(nuevoUsr.rol_id) || null,
      proveedor_id: Number(nuevoUsr.proveedor_id) || null,
    })
    avisar(t('User {0} created.', [nuevoUsr.email]))
    // La contraseña temporal se muestra una sola vez para entregarla al usuario
    modal.value = r.password_temporal ? { tipo: 'temporal', email: nuevoUsr.email, clave: r.password_temporal } : null
    Object.assign(nuevoUsr, vacioUsr())
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

async function claveTemporal(u) {
  try {
    const r = await api.patch(`/usuarios/${u.id}`, { generar_clave: true })
    modal.value = { tipo: 'temporal', email: u.email, clave: r.password_temporal }
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
function copiar(texto) {
  navigator.clipboard?.writeText(texto).then(() => avisar(t('Copied.'))).catch(() => {})
}

async function actualizar(ruta, datos, mensaje) {
  try {
    await api.patch(ruta, datos)
    avisar(mensaje)
    modal.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
// ---- Roles: qué módulos y acciones tiene cada uno ------------------------------
function abrirRol(r) {
  modal.value = { tipo: 'rol', id: r?.id || null, nombre: r?.nombre || '', descripcion: r?.descripcion || '',
    activo: r ? r.activo : true, permisos: new Set(r?.permisos || []), ocultos: new Set(r?.datos_ocultos || []), inicio: new Set(r?.inicio_oculto || []),
    esAdmin: (r?.permisos || []).includes('admin') }
}
const marcado = (p) => modal.value.permisos.has(p.clave)
function alternarPermiso(p) {
  const s = modal.value.permisos
  s.has(p.clave) ? s.delete(p.clave) : s.add(p.clave)
}
function alternarModulo(m) {
  const todos = m.permisos.every(marcado)
  m.permisos.forEach((p) => (todos ? modal.value.permisos.delete(p.clave) : modal.value.permisos.add(p.clave)))
}
const nMarcados = computed(() => (modal.value?.tipo === 'rol' ? catalogo.value.flatMap((m) => m.permisos).filter(marcado).length : 0))
async function guardarRol() {
  const m = modal.value
  const cuerpo = { nombre: m.nombre, descripcion: m.descripcion || null, activo: m.activo, permisos: [...m.permisos],
    datos_ocultos: m.permisos.has('admin') ? [] : [...m.ocultos], inicio_oculto: [...m.inicio] }
  try {
    if (m.id) await api.patch(`/roles/${m.id}`, cuerpo)
    else await api.post('/roles', cuerpo)
    avisar(t('Role {0} saved.', [m.nombre]))
    modal.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
async function borrarRol(r) {
  try {
    await api.del(`/roles/${r.id}`)
    avisar(t('Role {0} deleted.', [r.nombre]))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
// Alcance de los datos: proveedores que representa o atiende, sociedades y
// transportistas (agentes de carga). Vacío = sin límite.
const opcionesAlcance = ref({ sociedades: [], transportistas: [] })
async function abrirRolUsuario(u) {
  const a = u.alcance || {}
  modal.value = { tipo: 'rol-usuario', usuario: u, rol_id: u.rol_id || '', proveedor_id: u.proveedor_id || '',
                  proveedores: [...(a.proveedores || [])], sociedades: [...(a.sociedades || [])], transportistas: [...(a.transportistas || [])] }
  try {
    const [s, tr] = await Promise.all([api.get('/catalogos/sociedades/opciones'), api.get('/catalogos/transportistas/opciones')])
    opcionesAlcance.value = { sociedades: s.map((x) => ({ valor: x.codigo, texto: x.texto })), transportistas: tr.map((x) => ({ valor: x.id, texto: x.texto })) }
  } catch (e) {
    errorApi(e)
  }
}
function guardarRolUsuario() {
  const m = modal.value
  actualizar(`/usuarios/${m.usuario.id}`, { rol_id: Number(m.rol_id), proveedor_id: Number(m.proveedor_id) || null,
                                            alcance: { proveedores: m.proveedores.map(Number), sociedades: m.sociedades, transportistas: m.transportistas.map(Number) } },
             t('Role updated.'))
}
onMounted(cargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Users and access') }}</h1>
      <p>{{ tx(AYUDA_PESTANA[pestana] || AYUDA_PESTANA.usuarios) }}</p>
    </div>
    <div class="acciones">
      <button v-if="pestana === 'usuarios'" class="btn btn-primario" type="button" @click="modal = 'usuario'"><Icono nombre="mas" />{{ t('New user') }}</button>
      <button v-if="pestana === 'roles'" class="btn btn-primario" type="button" @click="abrirRol(null)"><Icono nombre="mas" />{{ t('New role') }}</button>
      <router-link v-if="pestana === 'proveedores' && puede('catalogos.ver')" to="/mantenimiento?catalogo=proveedores" class="btn"><Icono nombre="base" />{{ t('Open in master data') }}</router-link>
    </div>
  </div>
  <div class="pestanas-pildora" role="tablist">
    <button v-for="[k, txt] in PESTANAS" :key="k" type="button" class="pildora" role="tab" :aria-selected="pestana === k" @click="elegirPestana(k)">
      {{ txt }}<span v-if="k === 'usuarios'" class="cuenta">{{ usuarios.length }}</span><span v-else-if="k === 'roles'" class="cuenta">{{ roles.length }}</span>
      <span v-else-if="k === 'proveedores'" class="cuenta">{{ proveedores.length }}</span>
    </button>
  </div>

  <TablaDatos v-if="pestana === 'proveedores'" tabla="acceso_proveedores" :columnas="colProveedores" :filas="proveedoresVista" orden-inicial="nombre:asc" :etiqueta="t('Suppliers')">
    <template #barra>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search code or name')" :aria-label="t('Search')" /></label>
    </template>
    <template #celda-codigo="{ fila: p }"><strong class="codigo">{{ tx(p.codigo) }}</strong></template>
    <template #celda-activo="{ fila: p }"><span class="etiqueta ms-0" :class="p.activo ? 'ok' : ''">{{ tx(p.activo ? t('Active') : t('Inactive')) }}</span></template>
    <template #celda-usuarios="{ fila: p }">{{ tx(usuarios.filter((u) => u.proveedor_id === p.id).length) }}</template>
    <template #vacio>{{ q ? t('No records match these filters.') : t('No records yet.') }}</template>
  </TablaDatos>

  <TablaDatos v-if="pestana === 'roles'" tabla="acceso_roles" :columnas="colRoles" :filas="rolesVista" :etiqueta="t('Roles and access')">
    <template #barra>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search role')" :aria-label="t('Search')" /></label>
    </template>
    <template #celda-nombre="{ fila: r }"><strong>{{ tx(r.nombre) }}</strong><span class="sub">{{ tx(r.descripcion || '—') }}</span></template>
    <template #celda-acceso="{ fila: r }">
      <div class="envolver">
        <span class="fuerte">{{ t('{0} of {1}', [r.permisos.length, totalPermisos]) }}</span>
        <span class="sub">{{ catalogo.filter((m) => m.permisos.some((p) => r.permisos.includes(p.clave))).map((m) => tx(m.modulo)).join(' · ') || t('No access') }}</span>
        <span v-if="r.datos_ocultos?.length" class="sub aviso-texto"><Icono nombre="ojo" :tam="13" /> {{ t('Does not see: {0}', [gruposDatos.filter((g) => r.datos_ocultos.includes(g.clave)).map((g) => tx(g.etiqueta)).join(' · ')]) }}</span>
      </div>
    </template>
    <template #celda-activo="{ fila: r }"><span class="etiqueta ms-0" :class="r.activo ? 'ok' : ''">{{ tx(r.activo ? t('Active') : t('Inactive')) }}</span></template>
    <template #acciones="{ fila: r }">
      <div class="acciones-apiladas">
        <button class="btn btn-chico" type="button" @click="abrirRol(r)"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button>
        <button class="btn btn-chico btn-fantasma texto-error" type="button" :disabled="r.usuarios > 0" :title="tx(r.usuarios ? t('Assign its users another role first') : t('Delete role'))"
                :aria-label="t('Delete role {0}', [r.nombre])" @click="borrarRol(r)"><Icono nombre="basura" :tam="14" />{{ t('Delete') }}</button>
      </div>
    </template>
  </TablaDatos>

  <PanelFlujo v-if="pestana === 'flujo'" />
  <PanelBitacora v-if="pestana === 'bitacora'" />

  <TablaDatos v-if="pestana === 'usuarios'" tabla="acceso_usuarios" :columnas="colUsuarios" :filas="usuariosVista" orden-inicial="nombre:asc" :etiqueta="t('Users')">
    <template #barra>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search name, email or mobile')" :aria-label="t('Search')" /></label>
    </template>
    <template #celda-nombre="{ fila: u }">
      <span class="usuario-fila"><Avatar :nombre="u.nombre" :foto="u.foto" :tam="30" /><span><strong>{{ tx(u.nombre) }}</strong><span class="sub">{{ tx([u.cargo, u.area].filter(Boolean).join(' · ')) }}</span>
        <span v-if="u.clave_temporal" class="etiqueta aviso ms-0">{{ t('Temporary password') }}</span></span></span>
    </template>
    <template #celda-rol="{ fila: u }">{{ tx(u.rol_nombre || '—') }}<span v-if="tx(u.rol_nombre) !== tx(ALCANCE[u.rol])" class="sub">{{ tx(ALCANCE[u.rol]) }}</span></template>
    <template #celda-proveedor="{ fila: u }">{{ tx(u.proveedor || t('Internal')) }}</template>
    <template #celda-telefono="{ fila: u }">
      <span v-if="u.telefono" class="codigo">{{ tx(u.telefono) }}</span>
      <span v-else class="etiqueta aviso ms-0">{{ t('Not registered') }}</span>
      <span class="sub">{{ tx(u.dos_pasos ? t('With SMS code') : t('Password only')) }}</span>
    </template>
    <template #celda-activo="{ fila: u }">
      <span class="etiqueta ms-0" :class="u.activo ? 'ok' : ''">{{ tx(u.activo ? t('Active') : t('Inactive')) }}</span>
      <span class="sub" :title="t('Last sign-in')">{{ tx(u.ultimo_acceso ? fmtFechaHora(u.ultimo_acceso) : t('Never signed in')) }}</span>
      <span v-if="u.bloqueado" class="etiqueta error" :title="t('Too many failed attempts. Resetting the password unlocks it.')">{{ t('Locked') }}</span>
      <span v-if="u.plataforma" class="etiqueta info" :title="t('Creates organizations, enters any of them and maintains the shared reference data')">{{ t('Platform') }}</span>
    </template>
    <template #acciones="{ fila: u }">
      <MenuAcciones :etiqueta="t('Actions for {0}', [u.email])">
        <button type="button" role="menuitem" @click="abrirRolUsuario(u)">{{ t('Role and data scope') }}</button>
        <button type="button" role="menuitem" @click="modal = { tipo: 'telefono', usuario: u, telefono: u.telefono || '', dos_pasos: u.dos_pasos }">{{ t('Mobile') }}</button>
        <button type="button" role="menuitem" @click="modal = { tipo: 'datos', usuario: u, nombre: u.nombre, email: u.email, cargo: u.cargo || '', area: u.area || '', empresa: u.empresa || '' }">{{ t('Edit data') }}</button>
        <button type="button" role="menuitem" @click="modal = { tipo: 'clave', usuario: u, clave: '' }">{{ t('Reset password') }}</button>
        <button type="button" role="menuitem" @click="actualizar(`/usuarios/${u.id}`, { activo: !u.activo }, t('User updated.'))">{{ tx(u.activo ? t('Deactivate') : t('Activate')) }}</button>
        <button v-if="sesion.usuario?.plataforma && !u.proveedor_id" type="button" role="menuitem" @click="actualizar(`/usuarios/${u.id}`, { plataforma: !u.plataforma }, t('User updated.'))">{{ u.plataforma ? t('Remove platform administration') : t('Make platform administrator') }}</button>
      </MenuAcciones>
    </template>
    <template #vacio>{{ q ? t('No records match these filters.') : t('No records yet.') }}</template>
  </TablaDatos>

  <Modal v-if="modal === 'usuario'" :titulo="t('New user')" ancho="620px" @cerrar="modal = null">
    <form id="form-usuario" class="rejilla-campos" @submit.prevent="crearUsuario">
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="nuevoUsr.nombre" required /></label>
      <label class="campo"><span class="req">{{ t('Email') }}</span><input v-model="nuevoUsr.email" type="email" required /></label>
      <label class="campo"><span class="req">{{ t('Role') }}</span>
        <Seleccion v-model="nuevoUsr.rol_id" required><option value="" disabled>{{ t('Choose') }}</option><option v-for="r in rolesActivos" :key="r.id" :value="r.id">{{ tx(r.nombre) }}</option></Seleccion>
        <small v-if="rolDe(nuevoUsr.rol_id)?.descripcion" class="ayuda">{{ tx(rolDe(nuevoUsr.rol_id).descripcion) }}</small>
      </label>
      <label class="campo"><span>{{ t('Supplier') }}</span>
        <Seleccion v-model="nuevoUsr.proveedor_id">
          <option value="">{{ t('None (internal user)') }}</option>
          <option v-for="p in proveedores.filter((x) => x.activo)" :key="p.id" :value="p.id">{{ tx(p.nombre) }}</option>
        </Seleccion>
        <small class="ayuda">{{ t('A supplier user only sees that supplier’s data.') }}</small>
      </label>
      <p v-if="nuevoUsr.proveedor_id && noAplicanProveedor(nuevoUsr.rol_id).length" class="nota aviso bloque campo-ancho">{{ t('For a supplier user these permissions of the role do not apply: {0}.', [noAplicanProveedor(nuevoUsr.rol_id).map((p) => tx(p.etiqueta)).join(', ')]) }}</p>
      <label class="campo"><span :class="{ req: nuevoUsr.dos_pasos }">{{ t('Mobile for two-step verification') }}</span>
        <input v-model="nuevoUsr.telefono" type="tel" placeholder="+503 7000 1234" :required="nuevoUsr.dos_pasos" autocomplete="off" />
        <small class="ayuda">{{ t('International format: + country code and number.') }}</small>
      </label>
      <label class="campo"><span>{{ t('Job title') }}</span><input v-model="nuevoUsr.cargo" maxlength="120" /></label>
      <label class="campo"><span>{{ t('Area') }}</span><input v-model="nuevoUsr.area" maxlength="120" /></label>
      <label class="campo"><span>{{ t('Company') }}</span><input v-model="nuevoUsr.empresa" maxlength="200" /></label>
      <label class="campo"><span>{{ t('Initial password') }}</span><input v-model="nuevoUsr.password" type="password" autocomplete="new-password" :placeholder="t('Empty: a temporary one is generated')" />
        <small class="ayuda">{{ t('The user changes it the first time they sign in, in a short guided setup.') }}</small></label>
      <label class="check"><input v-model="nuevoUsr.dos_pasos" type="checkbox" /> {{ t('Require two-step verification (recommended)') }}</label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-usuario">{{ t('Create user') }}</button>
    </template>
  </Modal>
  <PanelLateral v-if="modal?.tipo === 'rol'" :titulo="tx(modal.id ? t('Role: {0}', [modal.nombre]) : t('New role'))" ancho="860px" @cerrar="modal = null">
    <form id="form-rol" class="rol-form" @submit.prevent="guardarRol">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="modal.nombre" required maxlength="80" /></label>
        <label class="campo"><span>{{ t('Description') }}</span><input v-model="modal.descripcion" maxlength="300" :placeholder="t('What this role is for')" /></label>
      </div>
      <div class="lbl-permisos"><span class="req">{{ t('Permissions') }}</span><span class="sub">{{ t('{0} of {1} permissions', [nMarcados, totalPermisos]) }}</span></div>
      <div class="modulos">
        <fieldset v-for="m in catalogo" :key="m.modulo" class="modulo">
          <legend>
            <label class="check"><input type="checkbox" :checked="m.permisos.every(marcado)"
                   :indeterminate.prop="m.permisos.some(marcado) && !m.permisos.every(marcado)" @change="alternarModulo(m)" />{{ tx(m.modulo) }}</label>
          </legend>
          <label v-for="p in m.permisos" :key="p.clave" class="check permiso">
            <input type="checkbox" :checked="marcado(p)" @change="alternarPermiso(p)" />
            <span>{{ tx(p.etiqueta) }}<small v-if="!p.proveedor || p.clave === 'admin'" class="sub">{{ t('Internal users only') }}</small></span>
          </label>
        </fieldset>
      </div>
      <div class="lbl-permisos"><span>{{ t('Data this role sees') }}</span>
        <span class="sub">{{ t('Hidden data never reaches the user: it is not in the tables, filters, exports or the API.') }}</span></div>
      <p v-if="modal.permisos.has('admin')" class="ayuda">{{ t('Administrators always see all data.') }}</p>
      <div v-else class="datos-rol">
        <label v-for="g in gruposDatos" :key="g.clave" class="check permiso">
          <input type="checkbox" :checked="!modal.ocultos.has(g.clave)" @change="modal.ocultos.has(g.clave) ? modal.ocultos.delete(g.clave) : modal.ocultos.add(g.clave)" />
          <span>{{ tx(g.etiqueta) }}<small class="sub">{{ tx(g.descripcion) }}</small></span>
        </label>
      </div>
      <div class="lbl-permisos"><span>{{ t('Home page') }}</span>
        <span class="sub">{{ t('Panels this role sees on its home page.') }}</span></div>
      <div class="datos-rol">
        <label v-for="p in panelesInicio" :key="p.clave" class="check permiso">
          <input type="checkbox" :checked="!modal.inicio.has(p.clave)" @change="modal.inicio.has(p.clave) ? modal.inicio.delete(p.clave) : modal.inicio.add(p.clave)" />
          <span>{{ tx(p.etiqueta) }}</span>
        </label>
      </div>
      <label class="check mt-chico"><input v-model="modal.activo" type="checkbox" /> {{ t('Active') }}</label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-rol">{{ t('Save role') }}</button>
    </template>
  </PanelLateral>
  <Modal v-if="modal?.tipo === 'rol-usuario'" :titulo="t('Role for {0}', [modal.usuario.email])" @cerrar="modal = null">
    <form id="form-rol-usuario" class="rejilla-campos" @submit.prevent="guardarRolUsuario">
      <label class="campo"><span class="req">{{ t('Role') }}</span>
        <Seleccion v-model="modal.rol_id" required><option v-for="r in rolesActivos" :key="r.id" :value="r.id">{{ tx(r.nombre) }}</option></Seleccion>
        <small v-if="rolDe(modal.rol_id)?.descripcion" class="ayuda">{{ tx(rolDe(modal.rol_id).descripcion) }}</small>
      </label>
      <label class="campo"><span>{{ t('Supplier') }}</span>
        <Seleccion v-model="modal.proveedor_id">
          <option value="">{{ t('None (internal user)') }}</option>
          <option v-for="p in proveedores.filter((x) => x.activo || x.id === modal.proveedor_id)" :key="p.id" :value="p.id">{{ tx(p.nombre) }}</option>
        </Seleccion>
        <small class="ayuda">{{ t('A supplier user only sees that supplier’s data.') }}</small>
      </label>
      <p v-if="modal.proveedor_id && noAplicanProveedor(modal.rol_id).length" class="nota aviso bloque campo-ancho">{{ t('For a supplier user these permissions of the role do not apply: {0}.', [noAplicanProveedor(modal.rol_id).map((p) => tx(p.etiqueta)).join(', ')]) }}</p>
      <div class="campo-ancho">
        <h3 class="subtitulo">{{ t('Data scope') }}</h3>
        <p class="ayuda">{{ t('Limit what this user sees. Empty = no limit (a supplier user always sees their own supplier).') }}</p>
      </div>
      <div class="campo"><span>{{ modal.proveedor_id ? t('Other suppliers they represent') : t('Suppliers') }}</span>
        <FiltroMulti v-model="modal.proveedores" :opciones="proveedores.filter((x) => x.id !== Number(modal.proveedor_id)).map((x) => ({ valor: x.id, texto: x.nombre }))" :etiqueta="t('Suppliers')" :vacio="modal.proveedor_id ? t('none') : t('all')" /></div>
      <div class="campo"><span>{{ t('Companies') }}</span>
        <FiltroMulti v-model="modal.sociedades" :opciones="opcionesAlcance.sociedades" :etiqueta="t('Companies')" /></div>
      <div class="campo"><span>{{ t('Carriers (freight agents)') }}</span>
        <FiltroMulti v-model="modal.transportistas" :opciones="opcionesAlcance.transportistas" :etiqueta="t('Carriers')" /></div>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-rol-usuario">{{ t('Save') }}</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'clave'" :titulo="t('Password for {0}', [modal.usuario.email])" @cerrar="modal = null">
    <p>{{ t('A temporary password is generated; the user replaces it with their own when signing in. Resetting it also unlocks the account and closes its open sessions.') }}</p>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" @click="claveTemporal(modal.usuario)"><Icono nombre="candado" :tam="15" />{{ t('Generate temporary password') }}</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'temporal'" :titulo="t('Temporary password')" @cerrar="modal = null">
    <p>{{ t('Give this password to {0}. It is shown only once; when signing in, the user will create their own.', [modal.email]) }}</p>
    <div class="clave-temporal"><code>{{ modal.clave }}</code><button class="btn btn-chico" @click="copiar(modal.clave)">{{ t('Copy') }}</button></div>
    <template #pie><button class="btn btn-primario" @click="modal = null">{{ t('Done') }}</button></template>
  </Modal>
  <Modal v-if="modal?.tipo === 'datos'" :titulo="t('Data of {0}', [modal.usuario.email])" @cerrar="modal = null">
    <form id="form-datos" class="rejilla-campos" @submit.prevent="actualizar(`/usuarios/${modal.usuario.id}`, { nombre: modal.nombre, email: modal.email, cargo: modal.cargo || null, area: modal.area || null, empresa: modal.empresa || null }, t('User updated.'))">
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="modal.nombre" required maxlength="200" /></label>
      <label class="campo"><span class="req">{{ t('Email') }}</span><input v-model="modal.email" type="email" required /></label>
      <label class="campo"><span>{{ t('Job title') }}</span><input v-model="modal.cargo" maxlength="120" /></label>
      <label class="campo"><span>{{ t('Area') }}</span><input v-model="modal.area" maxlength="120" /></label>
      <label class="campo"><span>{{ t('Company') }}</span><input v-model="modal.empresa" maxlength="200" /></label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-datos">{{ t('Save') }}</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'telefono'" :titulo="t('Mobile for {0}', [modal.usuario.email])" @cerrar="modal = null">
    <form id="form-telefono" @submit.prevent="actualizar(`/usuarios/${modal.usuario.id}`, { telefono: modal.telefono || null, dos_pasos: modal.dos_pasos }, t('Mobile updated.'))">
      <label class="campo"><span :class="{ req: modal.dos_pasos }">{{ t('Registered mobile') }}</span>
        <input v-model="modal.telefono" type="tel" placeholder="+503 7000 1234" :required="modal.dos_pasos" autocomplete="off" /></label>
      <label class="check mt-chico"><input v-model="modal.dos_pasos" type="checkbox" /> {{ t('Require two-step verification') }}</label>
      <p class="ayuda">{{ t('Changing the mobile closes the user\'s open sessions.') }}</p>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-telefono">{{ t('Save') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.sub-panel { margin: 2px 0 0; font-size: 0.84rem; color: var(--tinta-3); }
.rol-form { display: flex; flex-direction: column; gap: 12px; }
.datos-rol { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 4px 16px; }
.lbl-permisos { display: flex; justify-content: space-between; align-items: baseline; font-size: 0.86rem; font-weight: 620; }
.modulos { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; }
.modulo { margin: 0; padding: 8px 12px 10px; border: 1px solid var(--linea); border-radius: 8px; min-width: 0; }
.modulo legend { padding: 0 4px; font-weight: 650; font-size: 0.88rem; }
.permiso { display: flex; align-items: flex-start; gap: 6px; font-size: 0.84rem; padding: 3px 0; }
.permiso small { font-size: 0.74rem; }
.permiso.apagado { color: var(--tinta-3); text-decoration: line-through; }
.clave-temporal { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: var(--radio); background: var(--superficie-2); }
.clave-temporal code { font-size: 1.15rem; letter-spacing: 0.04em; flex: 1; overflow-wrap: anywhere; }
.usuario-fila { display: flex; align-items: center; gap: 8px; }
</style>
