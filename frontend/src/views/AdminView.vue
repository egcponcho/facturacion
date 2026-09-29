<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import Icono from '../components/Icono.vue'
import Modal from '../components/Modal.vue'
import { sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'

const proveedores = ref([])
const usuarios = ref([])
const nuevoProv = reactive({ codigo: '', nombre: '' })
const nuevoUsr = reactive({ nombre: '', email: '', rol: 'proveedor', proveedor_id: '', password: '' })
const modal = ref(null) // 'proveedor' | 'usuario' | { tipo: 'clave', usuario, clave }
const ROLES = { admin: 'Administrador', interno: 'Equipo interno', proveedor: 'Proveedor' }

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
    avisar(`Proveedor ${nuevoProv.nombre} creado.`)
    Object.assign(nuevoProv, { codigo: '', nombre: '' })
    modal.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

async function crearUsuario() {
  try {
    await api.post('/usuarios', { ...nuevoUsr, proveedor_id: nuevoUsr.rol === 'proveedor' ? Number(nuevoUsr.proveedor_id) || null : null })
    avisar(`Usuario ${nuevoUsr.email} creado.`)
    Object.assign(nuevoUsr, { nombre: '', email: '', password: '' })
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
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

function guardarClave() {
  const { usuario, clave } = modal.value
  actualizar(`/usuarios/${usuario.id}`, { password: clave }, 'Contraseña actualizada.')
  modal.value = null
}

onMounted(cargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>Usuarios y proveedores</h1>
      <p>Cada usuario proveedor solo ve las OCs, facturas y packing lists de su proveedor.</p>
    </div>
  </div>

  <section class="panel">
    <div class="panel-cabeza"><h2>Proveedores</h2><button class="btn btn-primario" @click="modal = 'proveedor'"><Icono nombre="mas" />Nuevo proveedor</button></div>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Código</th><th>Nombre</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in proveedores" :key="p.id">
            <td class="codigo">{{ p.codigo }}</td>
            <td>{{ p.nombre }}</td>
            <td><span class="etiqueta" :class="p.activo ? 'ok' : ''">{{ p.activo ? 'Activo' : 'Inactivo' }}</span></td>
            <td><button class="btn btn-chico" @click="actualizar(`/proveedores/${p.id}`, { activo: !p.activo }, 'Proveedor actualizado.')">{{ p.activo ? 'Desactivar' : 'Activar' }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel">
    <div class="panel-cabeza"><h2>Usuarios</h2><button class="btn btn-primario" @click="modal = 'usuario'"><Icono nombre="mas" />Nuevo usuario</button></div>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Proveedor</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="u in usuarios" :key="u.id">
            <td>{{ u.nombre }}</td>
            <td>{{ u.email }}</td>
            <td>{{ ROLES[u.rol] }}</td>
            <td>{{ u.proveedor || '—' }}</td>
            <td><span class="etiqueta" :class="u.activo ? 'ok' : ''">{{ u.activo ? 'Activo' : 'Inactivo' }}</span></td>
            <td class="fila-flex">
              <button class="btn btn-chico" @click="modal = { tipo: 'clave', usuario: u, clave: '' }">Cambiar contraseña</button>
              <button class="btn btn-chico" @click="actualizar(`/usuarios/${u.id}`, { activo: !u.activo }, 'Usuario actualizado.')">{{ u.activo ? 'Desactivar' : 'Activar' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>

  <Modal v-if="modal === 'proveedor'" titulo="Nuevo proveedor" @cerrar="modal = null">
    <form id="form-proveedor" class="rejilla-campos" @submit.prevent="crearProveedor">
      <label class="campo"><span class="req">Código (como en SAP)</span><input v-model="nuevoProv.codigo" required /></label>
      <label class="campo"><span class="req">Nombre</span><input v-model="nuevoProv.nombre" required /></label>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" type="submit" form="form-proveedor">Crear proveedor</button>
    </template>
  </Modal>
  <Modal v-if="modal === 'usuario'" titulo="Nuevo usuario" ancho="620px" @cerrar="modal = null">
    <form id="form-usuario" class="rejilla-campos" @submit.prevent="crearUsuario">
    <label class="campo"><span class="req">Nombre</span><input v-model="nuevoUsr.nombre" required /></label>
    <label class="campo"><span class="req">Correo</span><input v-model="nuevoUsr.email" type="email" required /></label>
    <label class="campo"><span class="req">Rol</span>
      <select v-model="nuevoUsr.rol"><option v-for="(t, r) in ROLES" :key="r" :value="r">{{ t }}</option></select>
    </label>
    <label v-if="nuevoUsr.rol === 'proveedor'" class="campo"><span class="req">Proveedor</span>
      <select v-model="nuevoUsr.proveedor_id" required>
        <option value="" disabled>Elige</option>
        <option v-for="p in proveedores" :key="p.id" :value="p.id">{{ p.nombre }}</option>
      </select>
    </label>
    <label class="campo"><span class="req">Contraseña inicial</span><input v-model="nuevoUsr.password" type="password" minlength="6" required /></label>
  </form>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" type="submit" form="form-usuario">Crear usuario</button>
    </template>
  </Modal>
  <Modal v-if="modal?.tipo === 'clave'" :titulo="`Contraseña de ${modal.usuario.email}`" @cerrar="modal = null">
    <form id="form-clave" @submit.prevent="guardarClave">
      <label class="campo"><span class="req">Nueva contraseña</span><input v-model="modal.clave" type="password" minlength="6" required autocomplete="new-password" /></label>
      <p class="ayuda">Mínimo 6 caracteres.</p>
    </form>
    <template #pie>
      <button class="btn" @click="modal = null">Cancelar</button>
      <button class="btn btn-primario" type="submit" form="form-clave">Guardar</button>
    </template>
  </Modal>
</template>
