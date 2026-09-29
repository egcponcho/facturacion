<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'

const proveedores = ref([])
const usuarios = ref([])
const nuevoProv = reactive({ codigo: '', nombre: '' })
const nuevoUsr = reactive({ nombre: '', email: '', rol: 'proveedor', proveedor_id: '', password: '' })
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

function cambiarClave(u) {
  const clave = window.prompt(`Nueva contraseña para ${u.email} (mínimo 6 caracteres)`)
  if (clave) actualizar(`/usuarios/${u.id}`, { password: clave }, 'Contraseña actualizada.')
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
    <div class="panel-cabeza"><h2>Proveedores</h2></div>
    <form class="fila-flex" @submit.prevent="crearProveedor">
      <input v-model="nuevoProv.codigo" class="entrada" placeholder="Código (como en SAP) *" aria-label="Código" required />
      <input v-model="nuevoProv.nombre" class="entrada" placeholder="Nombre *" aria-label="Nombre" required />
      <button class="btn btn-primario" type="submit">Agregar proveedor</button>
    </form>
    <div class="tabla-marco mt">
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
    <div class="panel-cabeza"><h2>Usuarios</h2></div>
    <form class="rejilla-campos" @submit.prevent="crearUsuario">
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
      <div class="campo" style="justify-content: flex-end"><button class="btn btn-primario" type="submit">Crear usuario</button></div>
    </form>
    <div class="tabla-marco mt">
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
              <button class="btn btn-chico" @click="cambiarClave(u)">Cambiar contraseña</button>
              <button class="btn btn-chico" @click="actualizar(`/usuarios/${u.id}`, { activo: !u.activo }, 'Usuario actualizado.')">{{ u.activo ? 'Desactivar' : 'Activar' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
