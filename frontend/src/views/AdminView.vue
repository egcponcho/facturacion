<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import Seleccion from '../components/Seleccion.vue'
import { api } from '../api'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import Avatar from '../components/Avatar.vue'
import PanelFlujo from '../components/PanelFlujo.vue'
import { sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { fmtFechaHora } from '../utils'

const proveedores = ref([])
const usuarios = ref([])
const nuevoProv = reactive({ codigo: '', nombre: '' })
const vacioUsr = () => ({ nombre: '', email: '', rol_id: '', proveedor_id: '', password: '', telefono: '', dos_pasos: true, cargo: '', area: '', empresa: '' })
const nuevoUsr = reactive(vacioUsr())
// 'proveedor' | 'usuario' | { tipo: 'clave', usuario, clave } | { tipo: 'telefono', usuario, telefono, dos_pasos }
const modal = ref(null)
const ALCANCE = { admin: t('Administrator'), interno: t('Internal team'), proveedor: t('Supplier user') }
const roles = ref([])
const catalogo = ref([])
const rolesActivos = computed(() => roles.value.filter((r) => r.activo))
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
    sesion.proveedores = proveedores.value
  } catch (e) {
    errorApi(e)
  }
}

async function crearProveedor() {
  try {
    await api.post('/proveedores', nuevoProv)
    avisar(t('Supplier {0} created.', [nuevoProv.nombre]))
    Object.assign(nuevoProv, { codigo: '', nombre: '' })
    modal.value = null
    cargar()
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
    activo: r ? r.activo : true, permisos: new Set(r?.permisos || []) }
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
  const cuerpo = { nombre: m.nombre, descripcion: m.descripcion || null, activo: m.activo, permisos: [...m.permisos] }
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
function abrirRolUsuario(u) {
  modal.value = { tipo: 'rol-usuario', usuario: u, rol_id: u.rol_id || '', proveedor_id: u.proveedor_id || '' }
}
function guardarRolUsuario() {
  const m = modal.value
  actualizar(`/usuarios/${m.usuario.id}`, { rol_id: Number(m.rol_id), proveedor_id: Number(m.proveedor_id) || null }, t('Role updated.'))
}
onMounted(cargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Users and access') }}</h1>
      <p>{{ t('Each supplier user only sees their own supplier\'s POs, invoices and packing lists. Every user signs in with two-step verification: a code sent by SMS to their registered mobile.') }}</p>
    </div>
  </div>

  <section class="panel">
    <div class="panel-cabeza"><h2>{{ t('Suppliers') }}</h2><button class="btn btn-primario" @click="modal = 'proveedor'"><Icono nombre="mas" />{{ t('New supplier') }}</button></div>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Code') }}</th><th>{{ t('Name') }}</th><th>{{ t('Status') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in proveedores" :key="p.id">
            <td class="codigo">{{ tx(p.codigo) }}</td>
            <td>{{ tx(p.nombre) }}</td>
            <td><span class="etiqueta" :class="p.activo ? 'ok' : ''">{{ tx(p.activo ? t('Active') : t('Inactive')) }}</span></td>
            <td><button class="btn btn-chico" @click="actualizar(`/proveedores/${p.id}`, { activo: !p.activo }, t('Supplier updated.'))">{{ tx(p.activo ? t('Deactivate') : t('Activate')) }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <div class="panel-cabeza">
      <div><h2>{{ t('Roles and access') }}</h2><p class="sub-panel">{{ t('Create each role with a name, a description and the permissions you choose, then assign it to users. What data a user sees depends on the user: with a supplier assigned, only that supplier’s data.') }}</p></div>
      <button class="btn btn-primario" @click="abrirRol(null)"><Icono nombre="mas" />{{ t('New role') }}</button>
    </div>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Role') }}</th><th>{{ t('Access') }}</th><th>{{ t('Users') }}</th><th>{{ t('Status') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in roles" :key="r.id">
            <td><strong>{{ tx(r.nombre) }}</strong><span class="sub">{{ tx(r.descripcion || '—') }}</span></td>
            <td class="envolver">
              <span class="fuerte">{{ t('{0} of {1}', [r.permisos.length, totalPermisos]) }}</span>
              <span class="sub">{{ catalogo.filter((m) => m.permisos.some((p) => r.permisos.includes(p.clave))).map((m) => tx(m.modulo)).join(' · ') || t('No access') }}</span>
            </td>
            <td class="num">{{ tx(r.usuarios) }}</td>
            <td><span class="etiqueta" :class="r.activo ? 'ok' : ''" style="margin-inline-start: 0">{{ tx(r.activo ? t('Active') : t('Inactive')) }}</span></td>
            <td class="fila-flex">
              <button class="btn btn-chico" @click="abrirRol(r)"><Icono nombre="editar" :tam="14" />{{ t('Edit') }}</button>
              <button class="btn-icono" style="color: var(--error)" :disabled="r.usuarios > 0" :title="tx(r.usuarios ? t('Assign its users another role first') : t('Delete role'))" :aria-label="t('Delete role {0}', [r.nombre])" @click="borrarRol(r)"><Icono nombre="basura" :tam="15" /></button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <PanelFlujo />

  <section class="panel">
    <div class="panel-cabeza"><h2>{{ t('Users') }}</h2><button class="btn btn-primario" @click="modal = 'usuario'"><Icono nombre="mas" />{{ t('New user') }}</button></div>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Name') }}</th><th>{{ t('Email') }}</th><th>{{ t('Role') }}</th><th>{{ t('Supplier') }}</th><th>{{ t('Registered mobile') }}</th><th>{{ t('Last sign-in') }}</th><th>{{ t('Status') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-for="u in usuarios" :key="u.id">
            <td><span class="usuario-fila"><Avatar :nombre="u.nombre" :foto="u.foto" :tam="30" /><span>{{ tx(u.nombre) }}<span class="sub">{{ tx([u.cargo, u.area].filter(Boolean).join(' · ')) }}</span>
              <span v-if="u.clave_temporal" class="etiqueta aviso" style="margin-inline-start: 0">{{ t('Temporary password') }}</span></span></span></td>
            <td>{{ tx(u.email) }}</td>
            <td>{{ tx(u.rol_nombre || '—') }}<span v-if="tx(u.rol_nombre) !== tx(ALCANCE[u.rol])" class="sub">{{ tx(ALCANCE[u.rol]) }}</span></td>
            <td>{{ tx(u.proveedor || t('Internal')) }}</td>
            <td>
              <span v-if="u.telefono" class="codigo">{{ tx(u.telefono) }}</span>
              <span v-else class="etiqueta aviso" style="margin-inline-start: 0">{{ t('Not registered') }}</span>
              <span class="sub">{{ tx(u.dos_pasos ? t('Two-step verification on') : t('Password only')) }}</span>
            </td>
            <td>{{ tx(u.ultimo_acceso ? fmtFechaHora(u.ultimo_acceso) : t('Never')) }}</td>
            <td>
              <span class="etiqueta" :class="u.activo ? 'ok' : ''" style="margin-inline-start: 0">{{ tx(u.activo ? t('Active') : t('Inactive')) }}</span>
              <span v-if="u.bloqueado" class="etiqueta error" :title="t('Too many failed attempts. Resetting the password unlocks it.')">{{ t('Locked') }}</span>
            </td>
            <td class="fila-flex">
              <button class="btn btn-chico" @click="abrirRolUsuario(u)">{{ t('Role and supplier') }}</button>
              <button class="btn btn-chico" @click="modal = { tipo: 'telefono', usuario: u, telefono: u.telefono || '', dos_pasos: u.dos_pasos }">{{ t('Mobile') }}</button>
              <button class="btn btn-chico" @click="modal = { tipo: 'datos', usuario: u, nombre: u.nombre, email: u.email, cargo: u.cargo || '', area: u.area || '', empresa: u.empresa || '' }">{{ t('Edit data') }}</button>
              <button class="btn btn-chico" @click="modal = { tipo: 'clave', usuario: u, clave: '' }">{{ t('Reset password') }}</button>
              <button class="btn btn-chico" @click="actualizar(`/usuarios/${u.id}`, { activo: !u.activo }, t('User updated.'))">{{ tx(u.activo ? t('Deactivate') : t('Activate')) }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <Modal v-if="modal === 'proveedor'" :titulo="t('New supplier')" @cerrar="modal = null">
    <form id="form-proveedor" class="rejilla-campos" @submit.prevent="crearProveedor">
      <label class="campo"><span class="req">{{ t('Code (as in SAP)') }}</span><input v-model="nuevoProv.codigo" required /></label>
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="nuevoProv.nombre" required /></label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-proveedor">{{ t('Create supplier') }}</button>
    </template>
  </Modal>
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
  <Modal v-if="modal?.tipo === 'rol'" :titulo="tx(modal.id ? t('Role: {0}', [modal.nombre]) : t('New role'))" ancho="860px" @cerrar="modal = null">
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
      <label class="check mt-chico"><input v-model="modal.activo" type="checkbox" /> {{ t('Active') }}</label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-rol">{{ t('Save role') }}</button>
    </template>
  </Modal>
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
