<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t } from '@/i18n/index.js'
import { computed, onMounted, reactive } from 'vue'
import { api } from '@/nucleo/api'
import PortadaConfig from '@/componentes/PortadaConfig.vue'
import { visible } from '@/nucleo/modulos.js'
import { puede } from '@/stores/sesion'

// Portada de Configuración: todo lo que una empresa ajusta, en un solo lugar y
// en el orden en que conviene hacerlo al empezar. Lo de cada módulo se sigue
// editando en su módulo; aquí solo se llega a él. Cada tarjeta se ve con el
// mismo permiso que su pantalla.
const cuentas = reactive({})
async function cargar() {
  const pedidos = []
  if (puede('catalogos.ver')) {
    pedidos.push(api.get('/catalogos').then((meta) => { for (const c of meta) cuentas[c.tipo] = c.total }))
  }
  if (puede('admin')) pedidos.push(api.get('/usuarios').then((l) => { cuentas.usuarios = l.length }))
  if (puede('integraciones.ver')) pedidos.push(api.get('/integraciones').then((r) => { cuentas.integraciones = r.integraciones.length }))
  await Promise.allSettled(pedidos) // las cuentas son solo informativas
}
onMounted(cargar)
alCambiar(cargar, ['/catalogos', '/usuarios', '/integraciones'])

const cat = (tipo) => `/mantenimiento?catalogo=${tipo}`
const GRUPOS = computed(() => [
  { grupo: t('Your company'), items: [
    { a: '/empresa', permiso: 'admin', icono: 'base', nombre: t('Company'),
      texto: t('Name, brand, documents, modules in use, own fields, statuses, terminology, approvals and business rules.') },
    { a: '/admin', permiso: 'admin', clave: 'usuarios', icono: 'usuarios', nombre: t('Users and access'),
      texto: t('Who works in the system, their role, the data they see and two-step sign-in.') },
    { a: '/admin?tab=roles', permiso: 'admin', icono: 'candado', nombre: t('Roles and access'),
      texto: t('What each role may do in every module, the data it never sees and its home panels.') },
    { a: '/admin?tab=bitacora', permiso: 'admin', icono: 'historial', nombre: t('Activity log'),
      texto: t('Every change with who made it and when.') },
  ] },
  { grupo: t('References and connections'), items: [
    { a: cat('paises'), permiso: 'catalogos.ver', clave: 'paises', icono: 'globo', nombre: t('Countries'),
      texto: t('Countries with their tax ID name, customs nomenclature and tariff digits.') },
    { a: '/integraciones', permiso: 'integraciones.ver', clave: 'integraciones', icono: 'ruta', nombre: t('Integrations'),
      texto: t('ERP and other systems: file format, field mapping, exchanges and their log.') },
  ] },
  { grupo: t('Setup of each module'), items: [
    { a: '/productos/configuracion', permiso: 'catalogos.ver', icono: 'caja', nombre: t('Products setup'),
      texto: t('Families, variant attributes, scales, packs, brands and the rest of the product catalogs.') },
    { a: cat('proveedores'), permiso: 'catalogos.ver', clave: 'proveedores', icono: 'ordenes', nombre: t('Suppliers and companies'),
      texto: t('Suppliers, the companies that buy and their contacts.') },
    { a: cat('centros'), permiso: 'catalogos.ver', clave: 'centros', icono: 'barco', nombre: t('Places and carriers'),
      texto: t('Sites, warehouses, ports, regions, carriers, load unit types and release codes.') },
    { a: '/leadtimes', permiso: 'catalogos.ver', icono: 'reloj', nombre: t('Lead times'),
      texto: t('The chain of steps from order to store and how long each one takes.') },
    { a: cat('tipos_empaque'), permiso: 'catalogos.ver', clave: 'tipos_empaque', icono: 'factura', nombre: t('Packaging types and numbering'),
      texto: t('Packaging types of the packing list and the numbering series of the documents.') },
    { a: '/empaque/recetas', permiso: 'catalogos.ver', icono: 'capas', nombre: t('Packing recipes'),
      texto: t('How each product is packed and the rules that choose the recipe for each order.') },
    { a: '/etiquetas/configuracion', permiso: 'etiquetas.ver', interno: true, icono: 'etiqueta', nombre: t('Labels setup'),
      texto: t('Label types, where each one goes, data, formats and rules by family.') },
  ] },
  { grupo: t('Platform'), items: [
    { a: '/plataforma', plataforma: true, icono: 'cuadricula', nombre: t('Organizations'),
      texto: t('The companies that use this installation and their administrators.') },
  ] },
].map((g) => ({ ...g, items: g.items.filter(visible) })).filter((g) => g.items.length))
</script>

<template>
  <div>
    <header class="pagina-cabeza">
      <div>
        <h1>{{ t('Settings') }}</h1>
        <p>{{ t('Everything your company adjusts, in the order it is best done when starting. What belongs to a module is still edited in that module.') }}</p>
      </div>
    </header>
    <PortadaConfig :grupos="GRUPOS" :cuentas="cuentas" />
  </div>
</template>
