import { computed, ref, watch } from 'vue'
import { api } from '@/nucleo/api'

// Qué datos pide un producto (servidor: productos/perfil.py). El núcleo
// (código, nombre, unidad) siempre; lo demás es opcional salvo que la empresa
// lo vuelva obligatorio (Datos maestros → Artículos → datos obligatorios) o lo
// pida la familia del producto (sus campos obligatorios, los mismos que revisa
// el etiquetado).
//
// Cada dato del formulario con su nombre en el catálogo de artículos (empresa)
// y su clave en los campos de la familia. Los atributos (marca, modelo, talla,
// color…) los define cada empresa: se piden con exigeAtributo.
export const CAMPOS = {
  proveedor_id: { empresa: 'proveedor_id' },
  descripcion_comercial: { familia: ['producto.descripcion_comercial'] },
  pais_origen: { familia: ['producto.pais_origen'] },
  codigo_barras: { empresa: 'codigo_barras', familia: ['articulo.codigo_barras'] },
  peso: { empresa: 'peso_unitario', familia: ['articulo.peso_unitario'] },
  codigo_proveedor: { empresa: 'codigo_proveedor', familia: ['articulo.codigo_proveedor'] },
}
const CON_CAMPO = new Set(Object.values(CAMPOS).flatMap((c) => c.familia || []))

// grupoId: ref o getter con la familia elegida (vacío = sin familia)
export function usePerfil(grupoId) {
  const perfil = ref({ nucleo: [], empresa: [], familia: [], ejes: [], atributos: [] })
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
  // Un atributo de producto lo exige la empresa (atributo.X) o la familia (producto.dato.X)
  const exigeAtributo = (codigo) => perfil.value.empresa.some((x) => x.campo === `atributo.${codigo}`)
    || perfil.value.familia.some((x) => x.clave === `producto.dato.${codigo}`)
  // Los atributos del producto que define la empresa (marca, modelo, material…)
  const atributos = computed(() => perfil.value.atributos || [])
  // Lo que la familia pide y no se escribe aquí (campos propios, ficha técnica)
  const otros = computed(() => perfil.value.familia.filter((x) => !CON_CAMPO.has(x.clave)
    && !x.clave.startsWith('producto.dato.') && x.clave !== 'producto.marca'
    && !(x.clave.startsWith('articulo.atributo.') && perfil.value.ejes.includes(x.clave.slice(18)))))
  return { perfil, exige, exigeAtributo, atributos, otros }
}
