import { reactive } from 'vue'
import { api, manejarNoAutorizado } from '../api'

export const sesion = reactive({
  usuario: null,
  cargada: false,
  proveedores: [],
  proveedorId: Number(localStorage.getItem('proveedorId')) || null,
})

export const puede = (permiso) => !!sesion.usuario?.permisos?.includes(permiso)
export const esInterno = () => ['admin', 'interno'].includes(sesion.usuario?.rol)

export async function iniciarSesion(email, password) {
  const r = await api.post('/auth/login', { email, password })
  localStorage.setItem('token', r.token)
  sesion.cargada = false
  await cargarSesion()
}

export async function cargarSesion() {
  if (!localStorage.getItem('token')) {
    sesion.cargada = true
    return false
  }
  try {
    sesion.usuario = await api.get('/auth/me')
    sesion.proveedores = await api.get('/proveedores')
    if (!esInterno()) sesion.proveedorId = sesion.usuario.proveedor_id
  } catch {
    cerrarSesion()
  }
  sesion.cargada = true
  return !!sesion.usuario
}

export function cerrarSesion() {
  localStorage.removeItem('token')
  sesion.usuario = null
}

export function elegirProveedor(id) {
  sesion.proveedorId = id || null
  if (id) localStorage.setItem('proveedorId', id)
  else localStorage.removeItem('proveedorId')
}

export function nombreProveedor(id) {
  return sesion.proveedores.find((p) => p.id === id)?.nombre || ''
}

manejarNoAutorizado(() => {
  cerrarSesion()
  if (!location.pathname.startsWith('/login')) location.href = '/login'
})
