<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import { sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { fmtFechaHora } from '../utils'

const proveedores = ref([])
const usuarios = ref([])
const nuevoProv = reactive({ codigo: '', nombre: '' })
const vacioUsr = () => ({ nombre: '', email: '', rol: 'proveedor', proveedor_id: '', password: '', telefono: '', dos_pasos: true })
const nuevoUsr = reactive(vacioUsr())
// 'proveedor' | 'usuario' | { tipo: 'clave', usuario, clave } | { tipo: 'telefono', usuario, telefono, dos_pasos }
const modal = ref(null)
const ROLES = { admin: 'Administrator', interno: 'Internal team', proveedor: 'Supplier' }

async function cargar() {
  try {
    ;[proveedores.value, usuarios.value] = await Promise.all([api.get('/proveedores'), api.get('/usuarios')])
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
      proveedor_id: nuevoUsr.rol === 'proveedor' ? Number(nuevoUsr.proveedor_id) || null : null,
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
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>Users and suppliers</h1>
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
    <div class="panel-cabeza"><h2>Users</h2><button class="btn btn-primario" @click="modal = 'usuario'"><Icono nombre="mas" />New user</button></div>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Supplier</th><th>Registered mobile</th><th>Last sign-in</th><th>Status</th><th></th></tr></thead>
        <tbody>
          <tr v-for="u in usuarios" :key="u.id">
            <td>{{ u.nombre }}</td>
            <td>{{ u.email }}</td>
            <td>{{ ROLES[u.rol] }}</td>
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
        <select v-model="nuevoUsr.rol"><option v-for="(t, r) in ROLES" :key="r" :value="r">{{ t }}</option></select>
      </label>
      <label v-if="nuevoUsr.rol === 'proveedor'" class="campo"><span class="req">Supplier</span>
        <select v-model="nuevoUsr.proveedor_id" required>
          <option value="" disabled>Choose</option>
          <option v-for="p in proveedores" :key="p.id" :value="p.id">{{ p.nombre }}</option>
        </select>
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
