import { reactive } from 'vue'
import { api, manejarNoAutorizado } from '../api'

export const sesion = reactive({
  usuario: null,
  cargada: false,
  proveedores: [],
  proveedorId: Number(localStorage.getItem('proveedorId')) || null,
  expirada: false,
})

export const puede = (permiso) => !!sesion.usuario?.permisos?.includes(permiso)
export const esInterno = () => ['admin', 'interno'].includes(sesion.usuario?.rol)

// Paso 1: correo y contraseña. Devuelve el desafío si hay verificación en dos pasos.
export async function iniciarSesion(email, password) {
  const r = await api.post('/auth/login', { email, password })
  if (r.dos_pasos) return r
  await cargarSesion(true)
  return null
}

// Paso 2: el código recibido por SMS en el celular registrado
export async function verificarCodigo(desafio, codigo) {
  await api.post('/auth/verificar', { desafio, codigo })
  await cargarSesion(true)
}

export const reenviarCodigo = (desafio) => api.post('/auth/reenviar', { desafio })

export async function cargarSesion(forzar = false) {
  if (sesion.cargada && !forzar) return !!sesion.usuario
  try {
    sesion.usuario = await api.get('/auth/me')
    sesion.proveedores = await api.get('/proveedores')
    if (!esInterno()) sesion.proveedorId = sesion.usuario.proveedor_id
    sesion.expirada = false
  } catch {
    sesion.usuario = null
  }
  sesion.cargada = true
  return !!sesion.usuario
}

export async function cerrarSesion() {
  try {
    await api.post('/auth/logout')
  } catch {
    // Aunque falle la red, la sesión local se limpia
  }
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

// Sesión vencida (inactividad o duración máxima) o revocada: de vuelta al inicio
manejarNoAutorizado(() => {
  const habia = !!sesion.usuario
  sesion.usuario = null
  if (!location.pathname.startsWith('/login')) {
    location.href = `/login${habia ? '?expirada=1' : ''}`
  }
})
