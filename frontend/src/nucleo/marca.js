import { reactive } from 'vue'
import { t } from '@/i18n/index.js'
import { api } from './api'

// Marca de la empresa (Configuración → Empresa → Marca): nombre, logo, color
// de la interfaz, nombre del sistema y textos de la pantalla de ingreso. Un
// texto vacío usa el de fábrica. Antes de iniciar sesión se lee de la ruta
// pública; con sesión, de /auth/me.
export const marca = reactive({
  nombre: null, logo: null, color: '', titulo: '', ingreso_titulo: '', ingreso_texto: '', ingreso_ayuda: '', demo: null,
})

const VARIABLES = ['--acento', '--acento-hover', '--acento-claro', '--acento-medio', '--acento-texto']

// El color de la empresa reemplaza el acento en los dos temas (claro y oscuro);
// los tonos derivados se mezclan con el fondo de cada tema.
function aplicarColor(hex) {
  const raiz = document.documentElement.style
  if (!/^#[0-9a-f]{6}$/i.test(hex || '')) {
    VARIABLES.forEach((v) => raiz.removeProperty(v))
    return
  }
  raiz.setProperty('--acento', hex)
  raiz.setProperty('--acento-hover', `color-mix(in srgb, ${hex} 85%, black)`)
  raiz.setProperty('--acento-claro', `color-mix(in srgb, ${hex} 10%, transparent)`)
  raiz.setProperty('--acento-medio', `color-mix(in srgb, ${hex} 35%, transparent)`)
  raiz.setProperty('--acento-texto', `color-mix(in srgb, ${hex} 80%, var(--tinta))`)
}

export const tituloSistema = () => marca.titulo || t('Workspace')

export function usarMarca(empresa) {
  if (!empresa) return
  Object.assign(marca, { nombre: empresa.nombre, logo: empresa.logo, demo: empresa.demo ?? marca.demo }, empresa.marca || {})
  aplicarColor(marca.color)
  document.title = marca.nombre ? `${marca.nombre} · ${tituloSistema()}` : tituloSistema()
}

export async function cargarMarcaPublica() {
  try {
    usarMarca(await api.get('/publico/empresa'))
  } catch {
    // Sin conexión, la pantalla de ingreso usa los textos de fábrica
  }
}
