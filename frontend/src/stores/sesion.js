import { reactive } from 'vue'
import { api, manejarNoAutorizado } from '@/nucleo/api'
import { cargarListas } from '@/nucleo/listas.js'
import { usarMarca } from '@/nucleo/marca.js'
import { cambiarIdioma, idioma, sumarCatalogo, t } from '@/i18n/index.js'
import { aplicarPreferencias, pref } from './preferencias'
import { tema } from './tema'

export const sesion = reactive({
  usuario: null,
  cargada: false,
  proveedores: [],
  proveedorId: Number(localStorage.getItem('proveedorId')) || null,
  expirada: false,
})

export const puede = (permiso) => !!sesion.usuario?.permisos?.includes(permiso)
export const esInterno = () => ['admin', 'interno'].includes(sesion.usuario?.rol)
// Elige proveedor quien ve varios: el equipo interno o quien representa a varios proveedores
export const eligeProveedor = () => esInterno() || sesion.proveedores.length > 1
// Grupos de datos que el rol ve (Usuarios y accesos → Rol → Datos visibles).
// El servidor ya no los envía; la pantalla quita sus columnas y filtros.
export const ve = (grupo) => !(sesion.usuario?.datos_ocultos || []).includes(grupo)
// Paneles de la página de inicio que su rol muestra (Usuarios y accesos → Rol)
// y que pertenecen a un módulo encendido (Configuración → Empresa → Módulos)
const MODULO_DEL_PANEL = { envios: 'transporte', contenedores: 'transporte' }
// Campos propios de una entidad (Configuración → Empresa → Campos propios) y su valor en texto
export const camposPropios = (entidad) => sesion.usuario?.organizacion?.campos_propios?.[entidad] || []
export const valorPropio = (c, v) => (v === null || v === undefined || v === '' ? '—' : c.tipo === 'bool' ? (v ? t('Yes') : t('No')) : String(v))
export const vePanel = (panel) => !(sesion.usuario?.inicio_oculto || []).includes(panel)
  && sesion.usuario?.config?.modulos?.[MODULO_DEL_PANEL[panel]] !== false

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
    usarMarca(sesion.usuario.organizacion)
    await cargarListas()
    // El catálogo configurado (preguntas, opciones, categorías) en el idioma del usuario
    if (idioma !== 'en') sumarCatalogo(await api.get(`/i18n/catalogo/${idioma}`).catch(() => ({})))
    // Con contraseña temporal solo se usa el asistente inicial
    sesion.proveedores = sesion.usuario.clave_temporal ? [] : await api.get('/proveedores')
    if (!esInterno() && sesion.proveedores.length <= 1) sesion.proveedorId = sesion.usuario.proveedor_id
    sesion.expirada = false
    usarPreferencias(sesion.usuario.preferencias)
  } catch {
    sesion.usuario = null
  }
  sesion.cargada = true
  return !!sesion.usuario
}

// Las preferencias del perfil mandan: idioma, formatos, tema y filas por página
function usarPreferencias(p) {
  aplicarPreferencias(p)
  tema.value = pref.tema
  if (pref.idioma !== idioma) cambiarIdioma(pref.idioma)
}

export async function guardarPerfil(cambios) {
  const r = await api.patch('/perfil', cambios)
  sesion.usuario.nombre = r.nombre
  sesion.usuario.preferencias = r.preferencias
  usarPreferencias(r.preferencias)
  return r
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
