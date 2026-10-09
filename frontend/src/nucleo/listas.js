import { reactive } from 'vue'
import { tx } from '@/i18n/index.js'
import { api } from './api'

// Listas de valores de la empresa (Datos maestros → Listas de valores):
// unidades de medida, monedas, incoterms, modos y modalidades de transporte,
// tipos de centro, almacén, contacto, impuesto y documento técnico.
// Se cargan al iniciar sesión; los nombres de fábrica se traducen con tx().
export const listas = reactive({})

export async function cargarListas() {
  try {
    Object.assign(listas, await api.get('/listas'))
  } catch {
    // Sin listas, los campos muestran los códigos tal cual
  }
}

export const valores = (lista) => listas[lista] || []
export const valor = (lista, codigo) => valores(lista).find((v) => v.codigo === codigo)
export const nombreValor = (lista, codigo) => {
  const v = valor(lista, codigo)
  return v ? tx(v.nombre) : codigo
}
// Opciones [código, nombre] para un <select>
export const opcionesLista = (lista) => valores(lista).map((v) => [v.codigo, tx(v.nombre)])
// «singular|plural» → [singular, plural] traducidos
export const singularPlural = (texto, defecto = '') => {
  const [s, p] = String(texto || defecto).split('|')
  return [tx(s || ''), tx(p || s || '')]
}
