import { computed, ref, watch } from 'vue'
import { api } from '@/nucleo/api'

// Qué datos pide un producto (servidor: productos/perfil.py). El núcleo
// (código, nombre, unidad) siempre; lo demás es opcional salvo que la empresa
// lo vuelva obligatorio (Datos maestros → Artículos → datos obligatorios) o lo
// pida la familia del producto (sus campos obligatorios, los mismos que revisa
// el etiquetado).
//
// Cada dato del formulario con su nombre en el catálogo de artículos (empresa)
// y su clave en los campos de la familia.
export const CAMPOS = {
  proveedor_id: { empresa: 'proveedor_id' },
  marca_id: { empresa: 'marca_id', familia: ['articulo.marca_codigo', 'articulo.marca'] },
  grupo_id: { empresa: 'grupo_id', familia: ['articulo.grupo_codigo', 'articulo.grupo'] },
  estilo: { empresa: 'estilo', familia: ['articulo.estilo'] },
  descripcion_comercial: { familia: ['producto.descripcion_comercial'] },
  pais_origen: { familia: ['producto.pais_origen'] },
  upc: { empresa: 'upc', familia: ['articulo.upc'] },
  peso: { empresa: 'peso_unitario', familia: ['articulo.peso_unitario'] },
  sku_proveedor: { empresa: 'sku_proveedor', familia: ['articulo.sku_proveedor'] },
}
const CON_CAMPO = new Set(Object.values(CAMPOS).flatMap((c) => c.familia || []))

// grupoId: ref o getter con la familia elegida (vacío = sin familia)
export function usePerfil(grupoId) {
  const perfil = ref({ nucleo: [], empresa: [], familia: [], ejes: [] })
  watch(grupoId, async (id) => {
    try {
      perfil.value = await api.get('/productos/perfil', id ? { grupo_id: id } : {})
    } catch {
      // Sin perfil se pide solo el núcleo; el servidor valida igual al guardar
    }
  }, { immediate: true })
  const exige = (campo) => {
    const c = CAMPOS[campo]
    return !!c && (perfil.value.empresa.some((x) => x.campo === c.empresa)
      || perfil.value.familia.some((x) => (c.familia || []).includes(x.clave)))
  }
  // Lo que la familia pide y no se escribe aquí (atributos que no son ejes, campos propios, ficha técnica)
  const otros = computed(() => perfil.value.familia.filter((x) => !CON_CAMPO.has(x.clave)
    && !(x.clave.startsWith('articulo.atributo.') && perfil.value.ejes.includes(x.clave.slice(18)))))
  return { perfil, exige, otros }
}
