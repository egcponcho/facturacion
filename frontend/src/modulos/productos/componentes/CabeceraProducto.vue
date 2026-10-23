<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import Icono from '@/componentes/Icono.vue'
import { etiquetaUnidad } from '@/nucleo/unidades.js'
import { fmtFecha } from '@/nucleo/utils'

// Cabecera de la página del producto: quién es (nombre, código, familia,
// proveedor, estado), sus datos según su familia (cada atributo de producto que
// lleva la familia, con su valor o «sin dato») y sus variantes por atributo
// (los valores de cada eje como fichas). Todo sale de los datos: ningún
// atributo está fijo aquí.
const props = defineProps({
  producto: { type: Object, required: true },
  origen: { type: String, default: '' },
  comex: { type: Boolean, default: false },
  editable: { type: Boolean, default: false },
})
const emit = defineEmits(['editar', 'variantes'])

const MAX_VALORES = 14
const p = computed(() => props.producto)
const atributos = computed(() => p.value.atributos_familia || [])
const vacios = computed(() => atributos.value.filter((a) => !a.valor && !a.fuera).length)
const ejes = computed(() => (p.value.ejes || []).filter((e) => e.valores.length || (p.value.skus || 0) === 0))
const familiaUrl = computed(() => (p.value.grupo_producto_id ? `/productos/catalogo?familia=${p.value.grupo_producto_id}` : null))
const valorTexto = (a) => (a.tipo === 'bool' ? (a.valor === 'true' ? t('Yes') : t('No')) : a.valor)
</script>

<template>
  <section class="pc" :aria-label="t('Product')">
    <div class="pc-fila">
      <span class="pc-foto">
        <img v-if="p.fotos?.length" :src="`/api/productos/fotos/${p.fotos[0].id}`" alt="" />
        <Icono v-else nombre="caja" :tam="26" />
      </span>
      <div class="pc-titulo">
        <div class="pc-ruta">
          <Icono nombre="capas" :tam="13" />
          <router-link v-if="familiaUrl" :to="familiaUrl">{{ tx(p.familia) }}</router-link>
          <span v-else class="pc-sin">{{ t('Without family') }}</span>
        </div>
        <h1>{{ tx(p.nombre || p.codigo_generico) }}</h1>
        <div class="pc-ident">
          <span v-if="p.codigo_generico" class="pc-codigo" :title="t('Product code')">{{ p.codigo_generico }}</span>
          <span v-if="p.proveedor"><Icono nombre="camion" :tam="13" />{{ tx(p.proveedor) }}</span>
          <slot name="estado" />
          <span v-if="p.revisado_por" class="pc-tenue">{{ t('Reviewed by {0} · {1}', [p.revisado_por, fmtFecha(p.revisado_en)]) }}</span>
        </div>
      </div>
      <div class="pc-acciones"><slot name="acciones" /></div>
    </div>

    <div class="pc-cuerpo">
      <div class="pc-bloque">
        <div class="pc-bloque-cabeza">
          <h2>{{ t('Product data') }}</h2>
          <span v-if="vacios" class="pc-pendiente">{{ t('{0} without data', [vacios]) }}</span>
          <button v-if="editable && atributos.length" type="button" class="enlace pc-editar" @click="emit('editar')">
            <Icono nombre="editar" :tam="13" />{{ vacios ? t('Complete') : t('Edit') }}</button>
        </div>
        <dl class="pc-datos">
          <div v-for="a in atributos" :key="a.codigo" class="pc-dato" :class="{ vacio: !a.valor, fuera: a.fuera }"
               :title="a.fuera ? t('Its family no longer uses this attribute') : ''">
            <dt>{{ tx(a.nombre) }}<Icono v-if="a.fuera" nombre="alerta" :tam="12" /></dt>
            <dd>{{ a.valor ? tx(valorTexto(a)) : t('No data') }}<small v-if="a.valor && a.unidad"> {{ a.unidad }}</small></dd>
          </div>
          <div class="pc-dato">
            <dt>{{ t('Unit') }}</dt><dd>{{ p.unidad ? tx(etiquetaUnidad(p.unidad)) : '—' }}</dd>
          </div>
          <div v-if="comex" class="pc-dato" :class="{ vacio: !origen }">
            <dt>{{ t('Origin') }}</dt><dd>{{ tx(origen || t('No data')) }}</dd>
          </div>
        </dl>
        <p v-if="!atributos.length" class="pc-tenue pc-nota">{{ p.familia ? t('Its family has no product attributes yet.') : t('Without family it only takes the attributes for all families.') }}</p>
      </div>

      <div class="pc-bloque pc-variantes">
        <div class="pc-bloque-cabeza">
          <h2>{{ t('Variants') }}</h2>
          <span class="pc-cuenta">{{ tx(p.skus || 0) }}</span>
          <span v-if="p.n_compuestos" class="pc-tenue">{{ t('+ {0} packs or kits', [p.n_compuestos]) }}</span>
          <button type="button" class="enlace pc-editar" @click="emit('variantes')">{{ t('See all') }}<Icono nombre="derecha" :tam="13" /></button>
        </div>
        <div v-for="e in ejes" :key="e.codigo" class="pc-eje">
          <span class="pc-eje-nombre">{{ tx(e.nombre) }}</span>
          <div class="pc-valores">
            <span v-for="v in e.valores.slice(0, MAX_VALORES)" :key="v" class="pc-valor">{{ tx(v) }}</span>
            <span v-if="e.valores.length > MAX_VALORES" class="pc-valor mas" :title="e.texto">+{{ e.valores.length - MAX_VALORES }}</span>
            <span v-if="!e.valores.length" class="pc-tenue">{{ t('No values yet') }}</span>
          </div>
        </div>
        <p v-if="!ejes.length" class="pc-tenue pc-nota">{{ p.skus ? t('Its variants are not told apart by attributes.') : t('No variants yet.') }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.pc { background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio-panel); box-shadow: var(--sombra); margin-bottom: 16px; overflow: hidden; }
.pc-fila { display: flex; align-items: center; gap: 16px; padding: 20px 24px; flex-wrap: wrap; }
.pc-foto { width: 64px; height: 64px; border-radius: 14px; display: grid; place-items: center; flex: none; overflow: hidden;
  background: var(--acento-claro); color: var(--acento-texto); border: 1px solid var(--acento-medio); }
.pc-foto img { width: 100%; height: 100%; object-fit: cover; }
.pc-titulo { flex: 1 1 320px; min-width: 0; }
.pc-titulo h1 { font-size: var(--t-2xl); line-height: 1.15; margin: 2px 0 6px; overflow-wrap: anywhere; }
.pc-ruta { display: inline-flex; align-items: center; gap: 6px; font-size: var(--t-sm); font-weight: 600; color: var(--acento-texto); }
.pc-ruta a { color: inherit; text-decoration: none; }
.pc-ruta a:hover { text-decoration: underline; }
.pc-sin { color: var(--tinta-3); }
.pc-ident { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; color: var(--tinta-2); font-size: var(--t-sm); }
.pc-ident > span { display: inline-flex; align-items: center; gap: 5px; }
.pc-codigo { font-family: var(--mono); font-weight: 650; color: var(--tinta); background: var(--superficie-2); border: 1px solid var(--linea); border-radius: 6px; padding: 1px 8px; }
.pc-tenue { color: var(--tinta-3); font-size: var(--t-sm); }
.pc-acciones { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-inline-start: auto; }
.pc-cuerpo { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); border-top: 1px solid var(--linea); background: var(--superficie-2); }
.pc-bloque { padding: 16px 24px 18px; min-width: 0; }
.pc-variantes { border-inline-start: 1px solid var(--linea); }
.pc-bloque-cabeza { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.pc-bloque-cabeza h2 { font-size: var(--t-xs); text-transform: uppercase; letter-spacing: 0.06em; color: var(--tinta-3); font-weight: 700; }
.pc-editar { margin-inline-start: auto; display: inline-flex; align-items: center; gap: 4px; font-size: var(--t-sm); }
.pc-pendiente { font-size: var(--t-2xs); font-weight: 650; color: var(--aviso); background: var(--aviso-fondo); border-radius: 10px; padding: 1px 8px; }
.pc-cuenta { font-size: var(--t-2xs); font-weight: 700; background: var(--acento-claro); color: var(--acento-texto); border-radius: 10px; padding: 1px 8px; }
.pc-datos { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin: 0; }
.pc-dato { background: var(--superficie); border: 1px solid var(--linea); border-radius: 10px; padding: 8px 12px; min-width: 0; }
.pc-dato dt { font-size: var(--t-xs); color: var(--tinta-3); font-weight: 600; display: flex; align-items: center; gap: 4px; }
.pc-dato dd { margin: 2px 0 0; font-weight: 650; color: var(--tinta); overflow-wrap: anywhere; }
.pc-dato dd small { color: var(--tinta-3); font-weight: 500; }
.pc-dato.vacio { border-style: dashed; background: transparent; }
.pc-dato.vacio dd { color: var(--tinta-3); font-weight: 500; font-style: italic; }
.pc-dato.fuera { border-color: var(--aviso-borde); background: var(--aviso-suave); }
.pc-dato.fuera dt { color: var(--aviso); }
.pc-nota { margin-top: 4px; }
.pc-eje { display: grid; grid-template-columns: minmax(70px, auto) 1fr; gap: 10px; align-items: start; padding: 6px 0; }
.pc-eje + .pc-eje { border-top: 1px dashed var(--linea); }
.pc-eje-nombre { font-size: var(--t-xs); color: var(--tinta-3); font-weight: 600; padding-top: 4px; }
.pc-valores { display: flex; flex-wrap: wrap; gap: 5px; }
.pc-valor { font-size: var(--t-sm); font-weight: 600; background: var(--superficie); border: 1px solid var(--linea); border-radius: 7px; padding: 2px 9px; color: var(--tinta); }
.pc-valor.mas { background: var(--acento-claro); color: var(--acento-texto); border-color: var(--acento-medio); }
@media (max-width: 900px) {
  .pc-cuerpo { grid-template-columns: 1fr; }
  .pc-variantes { border-inline-start: 0; border-top: 1px solid var(--linea); }
}
@media (max-width: 600px) {
  .pc-fila, .pc-bloque { padding-inline: 16px; }
  .pc-acciones { margin-inline-start: 0; width: 100%; }
}
</style>
