// Idiomas de la interfaz. El texto en inglés es la clave; cada idioma tiene su
// diccionario (es.json, zh.json, hi.json, ar.json) con traducciones adaptadas,
// no literales, revisadas contra el glosario (glosario.json) por las pruebas.
// Las partes que cambian van como {0}, {1}… para que cada idioma ordene la
// frase a su manera. Al cambiar de idioma la página se vuelve a cargar, así
// las listas y etiquetas armadas al iniciar también salen en el idioma nuevo.

export const IDIOMAS = [
  // locale: fechas y números con dígitos latinos (los códigos y cantidades se leen igual en todos)
  { codigo: 'en', nombre: 'English', locale: 'en-GB', dir: 'ltr' },
  { codigo: 'es', nombre: 'Español', locale: 'es-419', dir: 'ltr' },
  { codigo: 'zh', nombre: '中文（简体）', locale: 'zh-CN', dir: 'ltr' },
  { codigo: 'hi', nombre: 'हिन्दी', locale: 'hi-IN-u-nu-latn', dir: 'ltr' },
  { codigo: 'ar', nombre: 'العربية', locale: 'ar-u-nu-latn', dir: 'rtl' },
]
const CLAVE = 'idioma'

function inicial() {
  let guardado = null
  try { guardado = localStorage.getItem(CLAVE) } catch { /* sin almacenamiento */ }
  // Por defecto, inglés para todos; cada usuario elige el suyo en su perfil
  return IDIOMAS.some((x) => x.codigo === guardado) ? guardado : 'en'
}

import SERVIDOR from './servidor.json' with { type: 'json' }

export const idioma = inicial()
export const actual = IDIOMAS.find((x) => x.codigo === idioma)
let dic = {}
let patrones = [] // claves con {0}… para traducir textos ya armados (mensajes del servidor)

// Vite reemplaza import.meta.glob al compilar; fuera de Vite (pruebas con Node) no existe import.meta.env
const ARCHIVOS = import.meta.env ? import.meta.glob(['./es.json', './zh.json', './hi.json', './ar.json']) : {}

export async function cargarIdioma() {
  if (idioma !== 'en') {
    const m = await ARCHIVOS[`./${idioma}.json`]()
    dic = m.default || m
  }
  // Plantillas de los mensajes del servidor (llegan ya armados): con texto
  // fijo suficiente para no confundirlas con datos
  patrones = SERVIDOR.filter((k) => dic[k] && /\{\d\}/.test(k) && k.replace(/\{\d\}/g, '').replace(/[^A-Za-z]/g, '').length >= 6).map((k) => {
    const partes = k.split(/(\{\d\})/)
    const orden = []
    const re = partes.map((p) => {
      const m = p.match(/^\{(\d)\}$/)
      if (m) { orden.push(Number(m[1])); return '(.+?)' }
      return p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    }).join('')
    return { re: new RegExp(`^${re}$`, 's'), orden, clave: k }
  }).sort((a, b) => b.clave.length - a.clave.length)
  if (typeof document !== 'undefined') {
    document.documentElement.lang = actual.locale
    document.documentElement.dir = actual.dir
  }
}

function rellenar(texto, args) {
  if (!args) return texto
  return texto.replace(/\{(\d)\}/g, (m, i) => (args[i] === undefined || args[i] === null ? '' : String(args[i])))
}

// Traduce un texto de la interfaz (la clave es el texto en inglés)
export function t(texto, args) {
  if (texto === null || texto === undefined) return texto
  const k = String(texto)
  return rellenar(dic[k] ?? k, args)
}

// Traduce un texto que llega ya armado (p. ej. un mensaje del servidor):
// busca la frase exacta o una plantilla con {0}… que le corresponda
const cache = new Map()
export function tx(texto) {
  if (idioma === 'en' || typeof texto !== 'string' || !texto) return texto
  if (dic[texto]) return dic[texto]
  if (!/[A-Za-z]{2}/.test(texto) || texto.length > 600) return texto
  if (cache.has(texto)) return cache.get(texto)
  let r = texto
  for (const p of patrones) {
    const m = texto.match(p.re)
    if (m) {
      const args = []
      p.orden.forEach((n, i) => { args[n] = tx(m[i + 1]) })
      r = rellenar(dic[p.clave], args)
      break
    }
  }
  if (cache.size > 5000) cache.clear()
  cache.set(texto, r)
  return r
}

export function cambiarIdioma(codigo) {
  if (codigo === idioma) return
  try { localStorage.setItem(CLAVE, codigo) } catch { /* sin almacenamiento */ }
  location.reload()
}
