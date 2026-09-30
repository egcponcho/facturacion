<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import Seleccion from '../components/Seleccion.vue'
import { api } from '../api'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import { sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { fmtFechaHora } from '../utils'

const proveedores = ref([])
const usuarios = ref([])
const nuevoProv = reactive({ codigo: '', nombre: '' })
const vacioUsr = () => ({ nombre: '', email: '', rol_id: '', proveedor_id: '', password: '', telefono: '', dos_pasos: true })
const nuevoUsr = reactive(vacioUsr())
// 'proveedor' | 'usuario' | { tipo: 'clave', usuario, clave } | { tipo: 'telefono', usuario, telefono, dos_pasos }
const modal = ref(null)
const ROLES = { admin: 'Administrator', interno: 'Internal team', proveedor: 'Supplier' }
const TIPOS = [['interno', 'Internal team', 'Sees every supplier'], ['proveedor', 'Supplier', 'Only its own supplier’s data'], ['admin', 'Administrator', 'Everything']]
const roles = ref([])
const catalogo = ref([])
const rolesActivos = computed(() => roles.value.filter((r) => r.activo))
const tipoDe = (id) => roles.value.find((r) => r.id === Number(id))?.tipo
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
    avisar(`Supplier ${nuevoProv.nombre} created.`)
    Object.assign(nuevoProv, { codigo: '', nombre: '' })
    modal.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

async function crearUsuario() {
  try {
    await api.post('/usuarios', {
      ...nuevoUsr, telefono: nuevoUsr.telefono || null,
      rol_id: Number(nuevoUsr.rol_id) || null,
      proveedor_id: tipoDe(nuevoUsr.rol_id) === 'proveedor' ? Number(nuevoUsr.proveedor_id) || null : null,
    })
    avisar(`User ${nuevoUsr.email} created.`)
    Object.assign(nuevoUsr, vacioUsr())
    modal.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
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
  modal.value = { tipo: 'rol', id: r?.id || null, sistema: !!r?.sistema, nombre: r?.nombre || '', descripcion: r?.descripcion || '',
    rolTipo: r?.tipo || 'interno', activo: r ? r.activo : true, permisos: new Set(r?.permisos || []) }
}
function permitido(p) {
  const t = modal.value.rolTipo
  return t === 'admin' || (p.clave !== 'admin' && (t !== 'proveedor' || p.proveedor))
}
function marcado(p) {
  return modal.value.rolTipo === 'admin' || (permitido(p) && modal.value.permisos.has(p.clave))
}
function alternarPermiso(p) {
  const s = modal.value.permisos
  s.has(p.clave) ? s.delete(p.clave) : s.add(p.clave)
}
function alternarModulo(m) {
  const ps = m.permisos.filter(permitido)
  const todos = ps.every((p) => modal.value.permisos.has(p.clave))
  ps.forEach((p) => (todos ? modal.value.permisos.delete(p.clave) : modal.value.permisos.add(p.clave)))
}
const nMarcados = computed(() => (modal.value?.tipo === 'rol' ? catalogo.value.flatMap((m) => m.permisos).filter(marcado).length : 0))
async function guardarRol() {
  const m = modal.value
  const cuerpo = { nombre: m.nombre, descripcion: m.descripcion || null, activo: m.activo, permisos: [...m.permisos].filter((k) => catalogo.value.some((x) => x.permisos.some((p) => p.clave === k && permitido(p)))) }
  if (!m.sistema) cuerpo.tipo = m.rolTipo
  try {
    if (m.id) await api.patch(`/roles/${m.id}`, cuerpo)
    else await api.post('/roles', cuerpo)
    avisar(`Role ${m.nombre} saved.`)
    modal.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
async function borrarRol(r) {
  try {
    await api.del(`/roles/${r.id}`)
    avisar(`Role ${r.nombre} deleted.`)
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
function abrirRolUsuario(u) {
  modal.value = { tipo: 'rol-usuario', usuario: u, rol_id: u.rol_id || roles.value.find((r) => r.sistema && r.tipo === u.rol)?.id || '', proveedor_id: u.proveedor_id || '' }
}
function guardarRolUsuario() {
  const m = modal.value
  const prov = tipoDe(m.rol_id) === 'proveedor'
  actualizar(`/usuarios/${m.usuario.id}`, { rol_id: Number(m.rol_id), proveedor_id: prov ? Number(m.proveedor_id) || null : null }, 'Role updated.')
}
onMounted(cargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>Users and access</h1>
      <p>Each supplier user only sees their own supplier's POs, invoices and packing lists. Every user signs in with two-step verification: a code sent by SMS to their registered mobile.</p>
    </div>
  </div>

  <section class="panel">
    <div class="panel-cabeza"><h2>Suppliers</h2><button class="btn btn-primario" @click="modal = 'proveedor'"><Icono nombre="mas" />New supplier</button></div>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Code</th><th>Name</th><th>Status</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in proveedores" :key="p.id">
            <td class="codigo">{{ p.codigo }}</td>
            <td>{{ p.nombre }}</td>
            <td><span class="etiqueta" :class="p.activo ? 'ok' : ''">{{ p.activo ? 'Active' : 'Inactive' }}</span></td>
            <td><button class="btn btn-chico" @click="actualizar(`/proveedores/${p.id}`, { activo: !p.activo }, 'Supplier updated.')">{{ p.activo ? 'Deactivate' : 'Activate' }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <div class="panel-cabeza">
      <div><h2>Roles and access</h2><p class="sub-panel">Each role says which modules and actions its users get. Supplier roles only ever see their own supplier’s data.</p></div>
      <button class="btn btn-primario" @click="abrirRol(null)"><Icono nombre="mas" />New role</button>
    </div>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Role</th><th>Type</th><th>Access</th><th>Users</th><th>Status</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in roles" :key="r.id">
            <td><strong>{{ r.nombre }}</strong><span v-if="r.sistema" class="etiqueta" style="margin-left: 6px">Built-in</span><span class="sub">{{ r.descripcion || '—' }}</span></td>
            <td>{{ ROLES[r.tipo] }}</td>
            <td>
              <span class="fuerte">{{ r.permisos.length }} of {{ totalPermisos }}</span>
              <span class="sub">{{ catalogo.filter((m) => m.permisos.some((p) => r.permisos.includes(p.clave))).map((m) => m.modulo).join(' · ') || 'No access' }}</span>
            </td>
            <td class="num">{{ r.usuarios }}</td>
            <td><span class="etiqueta" :class="r.activo ? 'ok' : ''" style="margin-left: 0">{{ r.activo ? 'Active' : 'Inactive' }}</span></td>
            <td class="fila-flex">
              <button class="btn btn-chico" @click="abrirRol(r)"><Icono nombre="editar" :tam="14" />{{ r.tipo === 'admin' ? 'See' : 'Edit access' }}</button>
              <button v-if="!r.sistema" class="btn-icono" style="color: var(--error)" :disabled="r.usuarios > 0" :title="r.usuarios ? 'Assign its users another role first' : 'Delete role'" :aria-label="`Delete role ${r.nombre}`" @click="borrarRol(r)"><Icono nombre="basura" :tam="15" /></button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <div class="panel-cabeza"><h2>Users</h2><button class="btn btn-primario" @click="modal = 'usuario'"><Icono nombre="mas" />New user</button></div>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Supplier</th><th>Registered mobile</th><th>Last sign-in</th><th>Status</th><th></th></tr></thead>
        <tbody>
          <tr v-for="u in usuarios" :key="u.id">
            <td>{{ u.nombre }}</td>
            <td>{{ u.email }}</td>
            <td>{{ u.rol_nombre || ROLES[u.rol] }}<span class="sub">{{ ROLES[u.rol] }}</span></td>
            <td>{{ u.proveedor || '—' }}</td>
            <td>
              <span v-if="u.telefono" class="codigo">{{ u.telefono }}</span>
              <span v-else class="etiqueta aviso" style="margin-left: 0">Not registered</span>
              <span class="sub">{{ u.dos_pasos ? 'Two-step verification on' : 'Password only' }}</span>
            </td>
            <td>{{ u.ultimo_acceso ? fmtFechaHora(u.ultimo_acceso) : 'Never' }}</td>
            <td>
              <span class="etiqueta" :class="u.activo ? 'ok' : ''" style="margin-left: 0">{{ u.activo ? 'Active' : 'Inactive' }}</span>
              <span v-if="u.bloqueado" class="etiqueta error" title="Too many failed attempts. Resetting the password unlocks it.">Locked</span>
            </td>
            <td class="fila-flex">
              <button class="btn btn-chico" @click="abrirRolUsuario(u)">Role</button>
              <button class="btn btn-chico" @click="modal = { tipo: 'telefono', usuario: u, telefono: u.telefono || '', dos_pasos: u.dos_pasos }">Mobile</button>
              <button class="btn btn-chico" @click="modal = { tipo: 'clave', usuario: u, clave: '' }">Reset password</button>
              <button class="btn btn-chico" @click="actualizar(`/usuarios/${u.id}`, { activo: !u.activo }, 'User updated.')">{{ u.activo ? 'Deactivate' : 'Activate' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <Modal v-if="modal === 'proveedor'" titulo="New supplier" @cerrar="modal = null">
    <form id="form-proveedor" class="rejilla-campos" @submit.prevent="crearProveedor">
      <label class="campo"><span class="req">Code (as in SAP)</span><input v-model="nuevoProv.codigo" required /></label>
      <label class="campo"><span class="req">Name</span><input v-model="nuevoProv.nombre" required /></label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" type="submit" form="form-proveedor">Create supplier</button>
    </template>
  </Modal>
  <Modal v-if="modal === 'usuario'" titulo="New user" ancho="620px" @cerrar="modal = null">
    <form id="form-usuario" class="rejilla-campos" @submit.prevent="crearUsuario">
      <label class="campo"><span class="req">Name</span><input v-model="nuevoUsr.nombre" required /></label>
      <label class="campo"><span class="req">Email</span><input v-model="nuevoUsr.email" type="email" required /></label>
      <label class="campo"><span class="req">Role</span>
        <Seleccion v-model="nuevoUsr.rol_id" required><option value="" disabled>Choose</option><option v-for="r in rolesActivos" :key="r.id" :value="r.id">{{ r.nombre }} · {{ ROLES[r.tipo] }}</option></Seleccion>
      </label>
      <label v-if="tipoDe(nuevoUsr.rol_id) === 'proveedor'" class="campo"><span class="req">Supplier</span>
        <Seleccion v-model="nuevoUsr.proveedor_id" required>
          <option value="" disabled>Choose</option>
          <option v-for="p in proveedores" :key="p.id" :value="p.id">{{ p.nombre }}</option>
        </Seleccion>
      </label>
      <label class="campo"><span :class="{ req: nuevoUsr.dos_pasos }">Mobile for two-step verification</span>
        <input v-model="nuevoUsr.telefono" type="tel" placeholder="+503 7000 1234" :required="nuevoUsr.dos_pasos" autocomplete="off" />
        <small class="ayuda">International format: + country code and number.</small>
      </label>
      <label class="campo"><span class="req">Initial password</span><input v-model="nuevoUsr.password" type="password" minlength="10" required autocomplete="new-password" />
        <small class="ayuda">At least 10 characters, with letters and numbers.</small></label>
      <label class="check"><input v-model="nuevoUsr.dos_pasos" type="checkbox" /> Require two-step verification (recommended)</label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" type="submit" form="form-usuario">Create user</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'rol'" :titulo="modal.id ? `Role: ${modal.nombre}` : 'New role'" ancho="860px" @cerrar="modal = null">
    <form id="form-rol" class="rol-form" @submit.prevent="guardarRol">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">Name</span><input v-model="modal.nombre" required maxlength="80" :disabled="modal.rolTipo === 'admin' && modal.sistema" /></label>
        <label class="campo"><span>Description</span><input v-model="modal.descripcion" maxlength="300" placeholder="What this role is for" /></label>
      </div>
      <div class="campo">
        <span class="req">Type</span>
        <div class="segs" role="radiogroup" aria-label="Type">
          <button v-for="[v, t, d] in TIPOS" :key="v" type="button" role="radio" :aria-checked="modal.rolTipo === v" :disabled="modal.sistema" :title="d" @click="modal.rolTipo = v">{{ t }}<small>{{ d }}</small></button>
        </div>
      </div>
      <div class="lbl-permisos"><span class="req">Access</span><span class="sub">{{ modal.rolTipo === 'admin' ? 'The administrator has every permission.' : `${nMarcados} of ${totalPermisos} permissions` }}</span></div>
      <div class="modulos">
        <fieldset v-for="m in catalogo" :key="m.modulo" class="modulo" :disabled="modal.rolTipo === 'admin'">
          <legend>
            <label class="check"><input type="checkbox" :checked="m.permisos.filter(permitido).length > 0 && m.permisos.filter(permitido).every(marcado)"
                   :indeterminate.prop="m.permisos.some(marcado) && !m.permisos.filter(permitido).every(marcado)" :disabled="!m.permisos.some(permitido)" @change="alternarModulo(m)" />{{ m.modulo }}</label>
          </legend>
          <label v-for="p in m.permisos" :key="p.clave" class="check permiso" :class="{ apagado: !permitido(p) }" :title="permitido(p) ? p.clave : 'Not available for supplier roles'">
            <input type="checkbox" :checked="marcado(p)" :disabled="!permitido(p)" @change="alternarPermiso(p)" />{{ p.etiqueta }}
          </label>
        </fieldset>
      </div>
      <label v-if="!(modal.sistema && modal.rolTipo === 'admin')" class="check mt-chico"><input v-model="modal.activo" type="checkbox" /> Active</label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button v-if="modal.rolTipo !== 'admin' || !modal.sistema" class="btn btn-primario" type="submit" form="form-rol">Save role</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'rol-usuario'" :titulo="`Role for ${modal.usuario.email}`" @cerrar="modal = null">
    <form id="form-rol-usuario" class="rejilla-campos" @submit.prevent="guardarRolUsuario">
      <label class="campo"><span class="req">Role</span>
        <Seleccion v-model="modal.rol_id" required><option v-for="r in rolesActivos" :key="r.id" :value="r.id">{{ r.nombre }} · {{ ROLES[r.tipo] }}</option></Seleccion>
      </label>
      <label v-if="tipoDe(modal.rol_id) === 'proveedor'" class="campo"><span class="req">Supplier</span>
        <Seleccion v-model="modal.proveedor_id" required>
          <option value="" disabled>Choose</option>
          <option v-for="p in proveedores" :key="p.id" :value="p.id">{{ p.nombre }}</option>
        </Seleccion>
      </label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" type="submit" form="form-rol-usuario">Save</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'clave'" :titulo="`Password for ${modal.usuario.email}`" @cerrar="modal = null">
    <form id="form-clave" @submit.prevent="actualizar(`/usuarios/${modal.usuario.id}`, { password: modal.clave }, 'Password reset. The user\'s sessions were closed.')">
      <label class="campo"><span class="req">New password</span><input v-model="modal.clave" type="password" minlength="10" required autocomplete="new-password" /></label>
      <p class="ayuda">At least 10 characters, with letters and numbers. Resetting it also unlocks the account and closes its open sessions.</p>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" type="submit" form="form-clave">Save</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'telefono'" :titulo="`Mobile for ${modal.usuario.email}`" @cerrar="modal = null">
    <form id="form-telefono" @submit.prevent="actualizar(`/usuarios/${modal.usuario.id}`, { telefono: modal.telefono || null, dos_pasos: modal.dos_pasos }, 'Mobile updated.')">
      <label class="campo"><span :class="{ req: modal.dos_pasos }">Registered mobile</span>
        <input v-model="modal.telefono" type="tel" placeholder="+503 7000 1234" :required="modal.dos_pasos" autocomplete="off" /></label>
      <label class="check mt-chico"><input v-model="modal.dos_pasos" type="checkbox" /> Require two-step verification</label>
      <p class="ayuda">Changing the mobile closes the user's open sessions.</p>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">Cancel</button>
      <button class="btn btn-primario" type="submit" form="form-telefono">Save</button>
    </template>
  </Modal>
</template>

<style scoped>
.sub-panel { margin: 2px 0 0; font-size: 0.84rem; color: var(--tinta-3); }
.rol-form { display: flex; flex-direction: column; gap: 12px; }
.segs { display: flex; flex-wrap: wrap; gap: 8px; }
.segs button { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 8px 12px; border: 1px solid var(--linea); border-radius: 8px; background: var(--superficie-2); color: var(--tinta); font: inherit; font-size: 0.88rem; font-weight: 620; cursor: pointer; }
.segs button small { font-weight: 400; font-size: 0.76rem; color: var(--tinta-3); }
.segs button[aria-checked='true'] { border-color: var(--acento); background: var(--acento-claro); color: var(--acento-texto); }
.segs button:disabled { cursor: not-allowed; opacity: 0.6; }
.segs button[aria-checked='true']:disabled { opacity: 1; }
.lbl-permisos { display: flex; justify-content: space-between; align-items: baseline; font-size: 0.86rem; font-weight: 620; }
.modulos { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; }
.modulo { margin: 0; padding: 8px 12px 10px; border: 1px solid var(--linea); border-radius: 8px; min-width: 0; }
.modulo legend { padding: 0 4px; font-weight: 650; font-size: 0.88rem; }
.permiso { display: flex; align-items: flex-start; gap: 6px; font-size: 0.84rem; padding: 3px 0; }
.permiso.apagado { color: var(--tinta-3); text-decoration: line-through; }
</style>
